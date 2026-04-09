from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

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
        self._init_lock = asyncio.Lock()
        self._initialized = False

    @property
    def database_path(self) -> Path:
        return self._database_path

    async def load_config(self) -> dict[str, Any]:
        await self._ensure_initialized()
        return await self._load_named_payload(
            "plugin_config",
            "config_key",
            DEFAULT_CONFIG_KEY,
        )

    async def save_config(self, data: dict[str, Any]) -> None:
        await self._ensure_initialized()
        await self._save_named_payload(
            "plugin_config",
            "config_key",
            DEFAULT_CONFIG_KEY,
            data,
        )

    async def load_avatar_hash_state(self, group_id: str) -> dict[str, Any]:
        await self._ensure_initialized()
        return await self._load_group_payload("avatar_hash_states", group_id)

    async def save_avatar_hash_state(self, group_id: str, data: dict[str, Any]) -> str:
        await self._ensure_initialized()
        await self._save_group_payload("avatar_hash_states", group_id, data)
        return self._build_record_ref("avatar_hash_states", group_id)

    async def load_group_name_guard(self, group_id: str) -> dict[str, Any]:
        await self._ensure_initialized()
        return await self._load_group_payload("group_name_guard_states", group_id)

    async def save_group_name_guard(self, group_id: str, data: dict[str, Any]) -> str:
        await self._ensure_initialized()
        await self._save_group_payload("group_name_guard_states", group_id, data)
        return self._build_record_ref("group_name_guard_states", group_id)

    async def load_member_profile_state(self, group_id: str) -> dict[str, Any]:
        await self._ensure_initialized()
        return await self._load_group_payload("member_profile_states", group_id)

    async def save_member_profile_state(self, group_id: str, data: dict[str, Any]) -> str:
        await self._ensure_initialized()
        await self._save_group_payload("member_profile_states", group_id, data)
        return self._build_record_ref("member_profile_states", group_id)

    async def load_runtime_owner(self) -> str:
        await self._ensure_initialized()
        async with self._connect() as connection:
            row = await self._fetchone(
                connection,
                """
                SELECT token
                FROM runtime_owner
                WHERE owner_key = ?
                """,
                (DEFAULT_RUNTIME_OWNER_KEY,),
            )
        if not row:
            return ""
        return str(row["token"] or "").strip()

    async def save_runtime_owner(self, token: str) -> None:
        await self._ensure_initialized()
        async with self._connect() as connection:
            await self._execute_without_result(
                connection,
                """
                INSERT INTO runtime_owner (owner_key, token)
                VALUES (?, ?)
                ON CONFLICT(owner_key) DO UPDATE SET token = excluded.token
                """,
                (DEFAULT_RUNTIME_OWNER_KEY, str(token).strip()),
            )

    def _build_record_ref(self, table_name: str, record_key: str) -> str:
        return f"{self._database_path}#{table_name}/{record_key}"

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            await asyncio.to_thread(self._data_dir.mkdir, parents=True, exist_ok=True)
            async with self._connect() as connection:
                await self._create_schema(connection)
                await self._migrate_legacy_files(connection)
            self._initialized = True

    def _build_migration_source_dirs(self, legacy_data_dirs: tuple[Path, ...]) -> tuple[Path, ...]:
        source_dirs: list[Path] = [self._data_dir]
        for directory_path in legacy_data_dirs:
            resolved_path = directory_path.resolve()
            if any(existing.resolve() == resolved_path for existing in source_dirs):
                continue
            source_dirs.append(directory_path)
        return tuple(source_dirs)

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self._database_path, timeout=30.0)
        connection.row_factory = aiosqlite.Row
        await self._execute_without_result(connection, "PRAGMA busy_timeout = 30000")
        await self._execute_without_result(connection, "PRAGMA journal_mode = WAL")
        try:
            yield connection
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def _create_schema(self, connection: aiosqlite.Connection) -> None:
        cursor = await connection.executescript(
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
        await cursor.close()

    async def _migrate_legacy_files(self, connection: aiosqlite.Connection) -> None:
        migration_state = await self._load_meta(connection, LEGACY_MIGRATION_META_KEY)
        if migration_state == LEGACY_MIGRATION_DONE_VALUE:
            return

        for migration_source_dir in self._migration_source_dirs:
            await self._migrate_named_json_file(
                connection,
                migration_source_dir / "config.json",
                "plugin_config",
                "config_key",
                DEFAULT_CONFIG_KEY,
            )
            await self._migrate_group_state_directory(
                connection,
                migration_source_dir / "avatar_hash",
                "avatar_hash_states",
            )
            await self._migrate_group_state_directory(
                connection,
                migration_source_dir / "group_name_guard",
                "group_name_guard_states",
            )
            await self._migrate_group_state_directory(
                connection,
                migration_source_dir / "member_profile",
                "member_profile_states",
            )
            await self._migrate_runtime_owner_file(
                connection,
                migration_source_dir / "runtime_owner.txt",
            )
        await self._save_meta(
            connection,
            LEGACY_MIGRATION_META_KEY,
            LEGACY_MIGRATION_DONE_VALUE,
        )
        runtime_logger.info(
            "[GroupEventLog] migrated legacy state files into sqlite store path=%s sources=%s",
            self._database_path,
            ",".join(str(path) for path in self._migration_source_dirs),
        )

    async def _migrate_named_json_file(
        self,
        connection: aiosqlite.Connection,
        file_path: Path,
        table_name: str,
        key_column: str,
        record_key: str,
    ) -> None:
        if not file_path.exists():
            return
        if await self._has_named_row(connection, table_name, key_column, record_key):
            return

        payload = await asyncio.to_thread(self._load_json_file, file_path)
        if not payload:
            return

        await self._execute_without_result(
            connection,
            f"""
            INSERT INTO {table_name} ({key_column}, payload)
            VALUES (?, ?)
            """,
            (record_key, self._serialize_payload(payload)),
        )

    async def _migrate_group_state_directory(
        self,
        connection: aiosqlite.Connection,
        directory_path: Path,
        table_name: str,
    ) -> None:
        if not directory_path.exists():
            return

        for file_path in sorted(directory_path.glob("*.json")):
            group_id = file_path.stem.strip()
            if not group_id:
                continue
            if await self._has_named_row(connection, table_name, "group_id", group_id):
                continue

            payload = await asyncio.to_thread(self._load_json_file, file_path)
            if not payload:
                continue

            await self._execute_without_result(
                connection,
                f"""
                INSERT INTO {table_name} (group_id, payload)
                VALUES (?, ?)
                """,
                (group_id, self._serialize_payload(payload)),
            )

    async def _migrate_runtime_owner_file(
        self, connection: aiosqlite.Connection, file_path: Path
    ) -> None:
        if not file_path.exists():
            return
        if await self._has_named_row(
            connection,
            "runtime_owner",
            "owner_key",
            DEFAULT_RUNTIME_OWNER_KEY,
        ):
            return

        token = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        token = token.strip()
        if not token:
            return

        await self._execute_without_result(
            connection,
            """
            INSERT INTO runtime_owner (owner_key, token)
            VALUES (?, ?)
            """,
            (DEFAULT_RUNTIME_OWNER_KEY, token),
        )

    async def _load_group_payload(self, table_name: str, group_id: str) -> dict[str, Any]:
        return await self._load_named_payload(table_name, "group_id", group_id)

    async def _save_group_payload(
        self, table_name: str, group_id: str, data: dict[str, Any]
    ) -> None:
        await self._save_named_payload(table_name, "group_id", group_id, data)

    async def _load_named_payload(
        self, table_name: str, key_column: str, record_key: str
    ) -> dict[str, Any]:
        async with self._connect() as connection:
            row = await self._fetchone(
                connection,
                f"""
                SELECT payload
                FROM {table_name}
                WHERE {key_column} = ?
                """,
                (record_key,),
            )
        if not row:
            return {}
        return self._deserialize_payload(row["payload"])

    async def _save_named_payload(
        self,
        table_name: str,
        key_column: str,
        record_key: str,
        data: dict[str, Any],
    ) -> None:
        async with self._connect() as connection:
            await self._execute_without_result(
                connection,
                f"""
                INSERT INTO {table_name} ({key_column}, payload)
                VALUES (?, ?)
                ON CONFLICT({key_column}) DO UPDATE SET payload = excluded.payload
                """,
                (record_key, self._serialize_payload(data)),
            )

    async def _load_meta(self, connection: aiosqlite.Connection, key: str) -> str:
        row = await self._fetchone(
            connection,
            """
            SELECT meta_value
            FROM repository_meta
            WHERE meta_key = ?
            """,
            (key,),
        )
        if not row:
            return ""
        return str(row["meta_value"] or "").strip()

    async def _save_meta(
        self, connection: aiosqlite.Connection, key: str, value: str
    ) -> None:
        await self._execute_without_result(
            connection,
            """
            INSERT INTO repository_meta (meta_key, meta_value)
            VALUES (?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
            """,
            (key, value),
        )

    async def _has_named_row(
        self,
        connection: aiosqlite.Connection,
        table_name: str,
        key_column: str,
        record_key: str,
    ) -> bool:
        row = await self._fetchone(
            connection,
            f"""
            SELECT 1
            FROM {table_name}
            WHERE {key_column} = ?
            LIMIT 1
            """,
            (record_key,),
        )
        return row is not None

    async def _fetchone(
        self,
        connection: aiosqlite.Connection,
        query: str,
        parameters: tuple[Any, ...],
    ) -> aiosqlite.Row | None:
        cursor = await connection.execute(query, parameters)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    async def _execute_without_result(
        self,
        connection: aiosqlite.Connection,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> None:
        cursor = await connection.execute(query, parameters)
        await cursor.close()

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
