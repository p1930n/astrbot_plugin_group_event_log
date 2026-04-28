from __future__ import annotations

import logging
from typing import TYPE_CHECKING

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    try:
        from ..storage.persistence import ConfigPersistence
        from ..runtime.plugin_runtime_state import PluginRuntimeState
    except ImportError:
        from storage.persistence import ConfigPersistence
        from runtime.plugin_runtime_state import PluginRuntimeState


class RuntimeSessionService:
    def __init__(
        self,
        persistence: "ConfigPersistence",
        runtime_state: "PluginRuntimeState",
        runtime_token: str,
    ) -> None:
        self._persistence = persistence
        self._runtime_state = runtime_state
        self._runtime_token = runtime_token
        self._inactive_logged = False

    async def register_current_runtime(self) -> None:
        await self._persistence.save_runtime_owner(self._runtime_token)

    async def is_active_runtime(self) -> bool:
        owner = await self._persistence.load_runtime_owner()
        active = owner == self._runtime_token
        if active:
            return True

        self._runtime_state.is_running = False
        if not self._inactive_logged:
            logger.info("[GroupEventLog] stale instance detected, stopping old runtime")
            self._inactive_logged = True
        return False
