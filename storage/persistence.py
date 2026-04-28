from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

try:
    from .sqlite_repository import SQLiteStateRepository
except ImportError:
    from storage.sqlite_repository import SQLiteStateRepository

try:
    from astrbot.api import logger as runtime_logger
except Exception:
    runtime_logger = logging.getLogger(__name__)


PLUGIN_DATA_DIR_NAME = "astrbot_plugin_group_event_log"

class ConfigPersistence:
    def __init__(self, plugin_dir: Path, runtime_root: Path | None = None) -> None:
        self._plugin_dir = plugin_dir
        self._runtime_root = runtime_root or Path.cwd()
        self._data_dir = self._runtime_root / "data" / PLUGIN_DATA_DIR_NAME
        self._legacy_data_dir = self._plugin_dir / "data"
        self._avatar_probe_dir = self._data_dir / "avatar_probe"
        self._avatar_baseline_dir = self._data_dir / "avatar_baseline"
        self._repository = SQLiteStateRepository(
            self._data_dir,
            legacy_data_dirs=(self._legacy_data_dir,),
        )
        self._prepare_lock = asyncio.Lock()
        self._storage_prepared = False

    @property
    def database_path(self) -> str:
        return str(self._repository.database_path)

    def avatar_probe_path(self, group_id: str) -> str:
        return str(self._avatar_probe_dir / f"{group_id}.json")

    async def load_config(self) -> dict[str, Any]:
        await self._ensure_storage_prepared()
        return await self._repository.load_config()

    async def save_config(self, data: dict[str, Any]) -> None:
        await self._ensure_storage_prepared()
        await self._repository.save_config(data)

    async def load_avatar_probe(self, group_id: str) -> dict[str, Any]:
        await self._ensure_storage_prepared()
        return await asyncio.to_thread(
            self._load_json_sync,
            self._avatar_probe_dir / f"{group_id}.json",
        )

    async def save_avatar_probe(self, group_id: str, data: dict[str, Any]) -> str:
        await self._ensure_storage_prepared()
        return await asyncio.to_thread(
            self._save_avatar_probe_sync,
            group_id,
            data,
        )

    async def load_avatar_hash_state(self, group_id: str) -> dict[str, Any]:
        await self._ensure_storage_prepared()
        state = await self._repository.load_avatar_hash_state(group_id)
        return self._normalize_avatar_hash_state(state)

    async def save_avatar_hash_state(self, group_id: str, data: dict[str, Any]) -> str:
        await self._ensure_storage_prepared()
        normalized_data = self._normalize_avatar_hash_state(data)
        return await self._repository.save_avatar_hash_state(group_id, normalized_data)

    async def load_group_name_guard(self, group_id: str) -> dict[str, Any]:
        await self._ensure_storage_prepared()
        return await self._repository.load_group_name_guard(group_id)

    async def save_group_name_guard(self, group_id: str, data: dict[str, Any]) -> str:
        await self._ensure_storage_prepared()
        return await self._repository.save_group_name_guard(group_id, data)

    async def load_member_profile_state(self, group_id: str) -> dict[str, Any]:
        await self._ensure_storage_prepared()
        return await self._repository.load_member_profile_state(group_id)

    async def save_member_profile_state(self, group_id: str, data: dict[str, Any]) -> str:
        await self._ensure_storage_prepared()
        return await self._repository.save_member_profile_state(group_id, data)

    async def load_runtime_owner(self) -> str:
        await self._ensure_storage_prepared()
        return await self._repository.load_runtime_owner()

    async def save_runtime_owner(self, token: str) -> None:
        await self._ensure_storage_prepared()
        await self._repository.save_runtime_owner(token)

    async def save_avatar_baseline_image(
        self, group_id: str, image_bytes: bytes, suffix: str
    ) -> str:
        await self._ensure_storage_prepared()
        return await asyncio.to_thread(
            self._save_avatar_baseline_image_sync,
            group_id,
            image_bytes,
            suffix,
        )

    def _save_avatar_probe_sync(self, group_id: str, data: dict[str, Any]) -> str:
        path = self._avatar_probe_dir / f"{group_id}.json"
        self._save_json_sync(path, data)
        return str(path)

    def _save_avatar_baseline_image_sync(
        self, group_id: str, image_bytes: bytes, suffix: str
    ) -> str:
        group_dir = self._avatar_baseline_dir / group_id
        group_dir.mkdir(parents=True, exist_ok=True)

        for item in group_dir.iterdir():
            if item.is_file():
                item.unlink()

        safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        path = group_dir / f"baseline{safe_suffix}"
        path.write_bytes(image_bytes)
        return str(path)

    async def _ensure_storage_prepared(self) -> None:
        if self._storage_prepared:
            return

        async with self._prepare_lock:
            if self._storage_prepared:
                return

            await asyncio.to_thread(self._prepare_storage_sync)
            self._storage_prepared = True

    def _prepare_storage_sync(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_storage()

    def _migrate_legacy_storage(self) -> None:
        if not self._legacy_data_dir.exists():
            return
        if self._same_path(self._legacy_data_dir, self._data_dir):
            return

        self._copy_legacy_database_files()
        self._copy_tree_if_missing(
            self._legacy_data_dir / "avatar_probe",
            self._avatar_probe_dir,
        )
        self._copy_tree_if_missing(
            self._legacy_data_dir / "avatar_baseline",
            self._avatar_baseline_dir,
        )

    def _copy_legacy_database_files(self) -> None:
        target_database_path = self._data_dir / "state.sqlite3"
        if target_database_path.exists():
            return

        copied_any = False
        for suffix in ("", "-shm", "-wal"):
            source_path = self._legacy_data_dir / f"state.sqlite3{suffix}"
            if not source_path.exists():
                continue

            destination_path = self._data_dir / source_path.name
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source_path, destination_path)
                copied_any = True
            except OSError as exc:
                runtime_logger.error(
                    "[GroupEventLog] copy legacy sqlite file failed src=%s dst=%s err=%s",
                    source_path,
                    destination_path,
                    exc,
                )
                raise

        if copied_any:
            runtime_logger.info(
                "[GroupEventLog] copied legacy sqlite store into runtime data dir dst=%s",
                target_database_path,
            )

    def _copy_tree_if_missing(self, source_dir: Path, target_dir: Path) -> None:
        if not source_dir.exists():
            return
        if self._same_path(source_dir, target_dir):
            return

        copied_count = 0
        for source_path in sorted(source_dir.rglob("*")):
            if source_path.is_dir():
                continue

            relative_path = source_path.relative_to(source_dir)
            target_path = target_dir / relative_path
            if target_path.exists():
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source_path, target_path)
                copied_count += 1
            except OSError as exc:
                runtime_logger.error(
                    "[GroupEventLog] copy legacy data file failed src=%s dst=%s err=%s",
                    source_path,
                    target_path,
                    exc,
                )
                raise

        if copied_count:
            runtime_logger.info(
                "[GroupEventLog] copied legacy data files src=%s dst=%s count=%s",
                source_dir,
                target_dir,
                copied_count,
            )

    def _normalize_avatar_hash_state(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            return {}

        normalized = dict(data)
        baseline_image_path = str(normalized.get("baseline_image_path", "")).strip()
        if baseline_image_path:
            normalized["baseline_image_path"] = self._rewrite_legacy_path(baseline_image_path)
        return normalized

    def _rewrite_legacy_path(self, file_path: str) -> str:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            return file_path

        legacy_root = self._legacy_data_dir.resolve()
        candidate_path = candidate.resolve()
        try:
            relative_path = candidate_path.relative_to(legacy_root)
        except ValueError:
            return file_path
        return str(self._data_dir / relative_path)

    def _same_path(self, left: Path, right: Path) -> bool:
        return left.resolve() == right.resolve()

    def _load_json_sync(self, path: Path) -> dict[str, Any]:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return {}

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_json_sync(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
