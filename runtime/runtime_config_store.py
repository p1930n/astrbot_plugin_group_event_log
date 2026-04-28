from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    try:
        from ..storage.persistence import ConfigPersistence
        from ..runtime.plugin_runtime_state import PluginRuntimeState
    except ImportError:
        from storage.persistence import ConfigPersistence
        from runtime.plugin_runtime_state import PluginRuntimeState

try:
    from ..domain.models import PluginConfig
except ImportError:
    from domain.models import PluginConfig


def current_local_time() -> datetime:
    return datetime.now()


class RuntimeConfigStore:
    def __init__(
        self,
        persistence: "ConfigPersistence",
        runtime_state: "PluginRuntimeState",
        now_factory: Callable[[], datetime] = current_local_time,
    ) -> None:
        self._persistence = persistence
        self._runtime_state = runtime_state
        self._now_factory = now_factory
        self._save_lock = asyncio.Lock()

    @property
    def config(self) -> PluginConfig:
        return self._runtime_state.config

    async def load(self) -> PluginConfig:
        config_data = await self._persistence.load_config()
        self._runtime_state.config = PluginConfig.from_dict(config_data)
        return self._runtime_state.config

    async def save(self) -> None:
        async with self._save_lock:
            self._runtime_state.config.last_updated = self._now_factory().isoformat(
                timespec="seconds"
            )
            await self._persistence.save_config(self._runtime_state.config.to_dict())
