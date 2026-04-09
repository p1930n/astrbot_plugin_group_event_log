from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    from astrbot.api import logger as runtime_logger
except Exception:
    runtime_logger = logging.getLogger(__name__)


LEGACY_MIGRATION_META_KEY = "legacy_migration_v1"
LEGACY_MIGRATION_DONE_VALUE = "done"
DEFAULT_CONFIG_KEY = "default"
DEFAULT_RUNTIME_OWNER_KEY = "active"


class SQLiteStateRepository:
    def __init__(
        self,
        data_dir: Path,
        legacy_data_dirs: tuple[Path, ...] = (),
    ) -> None:
        self._data_dir = data_dir
        self._database_path = self._data_dir / "state.sqlite3"
        self._migration_source_dirs = self._build_migration_source_dirs(legacy_data_dirs)
        self._init_lock = threading.Lock()
        self._initialized = False

    @property
    def database_path(self) -> Path:
        return self._database_path

    def load_config(self) -> dict[str, Any]:
        self._ensure_initialized()
        return self._load_named_payload("plugin_config", "config_key", DEFAULT_CONFIG_KEY)

    def save_config(self, data: dict[str, Any]) -> None:
        self._ensure_initialized()
        self._save_named_payload(
            "plugin_config",
            "config_key",
            DEFAULT_CONFIG_KEY,
            data,
        )

    def load_avatar_hash_state(self, group_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        return self._load_group_payload("avatar_hash_states", group_id)

    def save_avatar_hash_state(self, group_id: str, data: dict[str, Any]) -> str:
        self._ensure_initialized()
        self._save_group_payload("avatar_hash_states", group_id, data)
        return self.build_record_ref("avatar_hash_states", group_id)

    def load_group_name_guard(self, group_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        return self._load_group_payload("group_name_guard_states", group_id)

    def save_group_name_guard(self, group_id: str, data: dict[str, Any]) -> str:
        self._ensure_initialized()
        self._save_group_payload("group_name_guard_states", group_id, data)
        return self.build_record_ref("group_name_guard_states", group_id)

    def load_member_profile_state(self, group_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        return self._load_group_payload("member_profile_states", group_id)

    def save_member_profile_state(self, group_id: str, data: dict[str, Any]) -> str:
        self._ensure_initialized()
        self._save_group_payload("member_profile_states", group_id, data)
        return self.build_record_ref("member_profile_states", group_id)

    def load_runtime_owner(self) -> str:
        self._ensure_initialized()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT token
                FROM runtime_owner
                WHERE owner_key = ?
                """,
                (DEFAULT_RUNTIME_OWNER_KEY,),
            ).fetchone()
        if not row:
            return ""
        return str(row["token"] or "").strip()

    def save_runtime_owner(self, token: str) -> None:
        self._ensure_initialized()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_owner (owner_key, token)
                VALUES (?, ?)
                ON CONFLICT(owner_key) DO UPDATE SET token = excluded.token
                """,
                (DEFAULT_RUNTIME_OWNER_KEY, str(token).strip()),
            )

    def build_record_ref(self, table_name: str, record_key: str) -> str:
        return f"{self._database_path}#{table_name}/{record_key}"

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        with self._init_lock:
            if self._initialized:
                return

            self._data_dir.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                self._create_schema(connection)
                self._migrate_legacy_files(connection)
            self._initialized = True

    def _build_migration_source_dirs(self, legacy_data_dirs: tuple[Path, ...]) -> tuple[Path, ...]:
        source_dirs: list[Path] = [self._data_dir]
        for directory_path in legacy_data_dirs:
            resolved_path = directory_path.resolve()
            if any(existing.resolve() == resolved_path for existing in source_dirs):
                continue
            source_dirs.append(directory_path)
        return tuple(source_dirs)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS repository_meta (
                meta_key TEXT PRIMARY KEY,
                meta_value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plugin_config (
                config_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS avatar_hash_states (
                group_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_name_guard_states (
                group_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS member_profile_states (
                group_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runtime_owner (
                owner_key TEXT PRIMARY KEY,
                token TEXT NOT NULL
            );
            """
        )

    def _migrate_legacy_files(self, connection: sqlite3.Connection) -> None:
        migration_state = self._load_meta(connection, LEGACY_MIGRATION_META_KEY)
        if migration_state == LEGACY_MIGRATION_DONE_VALUE:
            return

        for migration_source_dir in self._migration_source_dirs:
            self._migrate_named_json_file(
                connection,
                migration_source_dir / "config.json",
                "plugin_config",
                "config_key",
                DEFAULT_CONFIG_KEY,
            )
            self._migrate_group_state_directory(
                connection,
                migration_source_dir / "avatar_hash",
                "avatar_hash_states",
            )
            self._migrate_group_state_directory(
                connection,
                migration_source_dir / "group_name_guard",
                "group_name_guard_states",
            )
            self._migrate_group_state_directory(
                connection,
                migration_source_dir / "member_profile",
                "member_profile_states",
            )
            self._migrate_runtime_owner_file(
                connection,
                migration_source_dir / "runtime_owner.txt",
            )
        self._save_meta(
            connection,
            LEGACY_MIGRATION_META_KEY,
            LEGACY_MIGRATION_DONE_VALUE,
        )
        runtime_logger.info(
            "[GroupEventLog] migrated legacy state files into sqlite store path=%s sources=%s",
            self._database_path,
            ",".join(str(path) for path in self._migration_source_dirs),
        )

    def _migrate_named_json_file(
        self,
        connection: sqlite3.Connection,
        file_path: Path,
        table_name: str,
        key_column: str,
        record_key: str,
    ) -> None:
        if not file_path.exists():
            return
        if self._has_named_row(connection, table_name, key_column, record_key):
            return

        payload = self._load_json_file(file_path)
        if not payload:
            return

        connection.execute(
            f"""
            INSERT INTO {table_name} ({key_column}, payload)
            VALUES (?, ?)
            """,
            (record_key, self._serialize_payload(payload)),
        )

    def _migrate_group_state_directory(
        self,
        connection: sqlite3.Connection,
        directory_path: Path,
        table_name: str,
    ) -> None:
        if not directory_path.exists():
            return

        for file_path in sorted(directory_path.glob("*.json")):
            group_id = file_path.stem.strip()
            if not group_id:
                continue
            if self._has_named_row(connection, table_name, "group_id", group_id):
                continue

            payload = self._load_json_file(file_path)
            if not payload:
                continue

            connection.execute(
                f"""
                INSERT INTO {table_name} (group_id, payload)
                VALUES (?, ?)
                """,
                (group_id, self._serialize_payload(payload)),
            )

    def _migrate_runtime_owner_file(
        self, connection: sqlite3.Connection, file_path: Path
    ) -> None:
        if not file_path.exists():
            return
        if self._has_named_row(
            connection,
            "runtime_owner",
            "owner_key",
            DEFAULT_RUNTIME_OWNER_KEY,
        ):
            return

        token = file_path.read_text(encoding="utf-8").strip()
        if not token:
            return

        connection.execute(
            """
            INSERT INTO runtime_owner (owner_key, token)
            VALUES (?, ?)
            """,
            (DEFAULT_RUNTIME_OWNER_KEY, token),
        )

    def _load_group_payload(self, table_name: str, group_id: str) -> dict[str, Any]:
        return self._load_named_payload(table_name, "group_id", group_id)

    def _save_group_payload(
        self, table_name: str, group_id: str, data: dict[str, Any]
    ) -> None:
        self._save_named_payload(table_name, "group_id", group_id, data)

    def _load_named_payload(
        self, table_name: str, key_column: str, record_key: str
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT payload
                FROM {table_name}
                WHERE {key_column} = ?
                """,
                (record_key,),
            ).fetchone()
        if not row:
            return {}
        return self._deserialize_payload(row["payload"])

    def _save_named_payload(
        self,
        table_name: str,
        key_column: str,
        record_key: str,
        data: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {table_name} ({key_column}, payload)
                VALUES (?, ?)
                ON CONFLICT({key_column}) DO UPDATE SET payload = excluded.payload
                """,
                (record_key, self._serialize_payload(data)),
            )

    def _load_meta(self, connection: sqlite3.Connection, key: str) -> str:
        row = connection.execute(
            """
            SELECT meta_value
            FROM repository_meta
            WHERE meta_key = ?
            """,
            (key,),
        ).fetchone()
        if not row:
            return ""
        return str(row["meta_value"] or "").strip()

    def _save_meta(
        self, connection: sqlite3.Connection, key: str, value: str
    ) -> None:
        connection.execute(
            """
            INSERT INTO repository_meta (meta_key, meta_value)
            VALUES (?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
            """,
            (key, value),
        )

    def _has_named_row(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        key_column: str,
        record_key: str,
    ) -> bool:
        row = connection.execute(
            f"""
            SELECT 1
            FROM {table_name}
            WHERE {key_column} = ?
            LIMIT 1
            """,
            (record_key,),
        ).fetchone()
        return row is not None

    def _load_json_file(self, file_path: Path) -> dict[str, Any]:
        try:
            return self._deserialize_payload(file_path.read_text(encoding="utf-8"))
        except OSError as exc:
            runtime_logger.error(
                "[GroupEventLog] load legacy json failed path=%s err=%s",
                file_path,
                exc,
            )
            return {}

    def _serialize_payload(self, data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, sort_keys=True)

    def _deserialize_payload(self, payload: str) -> dict[str, Any]:
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            runtime_logger.error(
                "[GroupEventLog] decode sqlite payload failed err=%s",
                exc,
            )
            return {}
        if not isinstance(decoded, dict):
            return {}
        return decoded
