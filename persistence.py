from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

try:
    from .sqlite_repository import SQLiteStateRepository
except ImportError:
    from sqlite_repository import SQLiteStateRepository


class ConfigPersistence:
    def __init__(self, plugin_dir: Path) -> None:
        self._data_dir = plugin_dir / "data"
        self._avatar_probe_dir = self._data_dir / "avatar_probe"
        self._avatar_baseline_dir = self._data_dir / "avatar_baseline"
        self._repository = SQLiteStateRepository(self._data_dir)

    @property
    def database_path(self) -> str:
        return str(self._repository.database_path)

    async def load_config(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._repository.load_config)

    async def save_config(self, data: dict[str, Any]) -> None:
        await asyncio.to_thread(self._repository.save_config, data)

    async def load_avatar_probe(self, group_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._load_json_sync,
            self._avatar_probe_dir / f"{group_id}.json",
        )

    async def save_avatar_probe(self, group_id: str, data: dict[str, Any]) -> str:
        return await asyncio.to_thread(self._save_avatar_probe_sync, group_id, data)

    async def load_avatar_hash_state(self, group_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._repository.load_avatar_hash_state, group_id)

    async def save_avatar_hash_state(self, group_id: str, data: dict[str, Any]) -> str:
        return await asyncio.to_thread(
            self._repository.save_avatar_hash_state,
            group_id,
            data,
        )

    async def load_group_name_guard(self, group_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._repository.load_group_name_guard, group_id)

    async def save_group_name_guard(self, group_id: str, data: dict[str, Any]) -> str:
        return await asyncio.to_thread(
            self._repository.save_group_name_guard,
            group_id,
            data,
        )

    async def load_member_profile_state(self, group_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._repository.load_member_profile_state,
            group_id,
        )

    async def save_member_profile_state(self, group_id: str, data: dict[str, Any]) -> str:
        return await asyncio.to_thread(
            self._repository.save_member_profile_state,
            group_id,
            data,
        )

    async def load_runtime_owner(self) -> str:
        return await asyncio.to_thread(self._repository.load_runtime_owner)

    async def save_runtime_owner(self, token: str) -> None:
        await asyncio.to_thread(self._repository.save_runtime_owner, token)

    async def save_avatar_baseline_image(
        self, group_id: str, image_bytes: bytes, suffix: str
    ) -> str:
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
