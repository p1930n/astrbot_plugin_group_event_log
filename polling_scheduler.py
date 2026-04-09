from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    try:
        from .bot_api_service import BotApiService
        from .group_runtime_service import GroupRuntimeService
        from .plugin_runtime_state import PluginRuntimeState
        from .runtime_session_service import RuntimeSessionService
    except ImportError:
        from bot_api_service import BotApiService
        from group_runtime_service import GroupRuntimeService
        from plugin_runtime_state import PluginRuntimeState
        from runtime_session_service import RuntimeSessionService


BOT_READY_RETRY_SECONDS = 5
DISABLED_RETRY_SECONDS = 10
NO_GROUPS_MAX_IDLE_SECONDS = 60
GROUP_CHECK_SPACING_SECONDS = 1
LOOP_ERROR_RETRY_SECONDS = 30


class PollingSchedulerService:
    def __init__(
        self,
        bot_api: "BotApiService",
        runtime_state: "PluginRuntimeState",
        runtime_session_service: "RuntimeSessionService",
        group_runtime_service: "GroupRuntimeService",
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._bot_api = bot_api
        self._runtime_state = runtime_state
        self._runtime_session_service = runtime_session_service
        self._group_runtime_service = group_runtime_service
        self._sleep = sleep_func

    async def avatar_poll_loop(self) -> None:
        while self._runtime_state.is_running:
            try:
                if not await self._runtime_session_service.is_active_runtime():
                    break

                config = self._runtime_state.config
                if not self._runtime_state.is_ready or not config.plugin_enabled:
                    await self._sleep(DISABLED_RETRY_SECONDS)
                    continue

                if not await self._bot_api.is_bot_ready():
                    await self._sleep(BOT_READY_RETRY_SECONDS)
                    continue

                monitored_group_ids = [
                    group_id
                    for group_id, group_config in config.monitored_groups.items()
                    if group_config.enabled
                    and group_config.event_switches.get("avatar_hash", True)
                ]

                if not monitored_group_ids:
                    await self._sleep(
                        min(config.avatar_poll_interval_seconds, NO_GROUPS_MAX_IDLE_SECONDS)
                    )
                    continue

                for group_id in monitored_group_ids:
                    await self._group_runtime_service.run_avatar_poll_check(group_id)
                    await self._sleep(GROUP_CHECK_SPACING_SECONDS)

                await self._sleep(config.avatar_poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[GroupEventLog] avatar poll loop failed: %s", exc, exc_info=True)
                await self._sleep(LOOP_ERROR_RETRY_SECONDS)

    async def member_profile_poll_loop(self) -> None:
        while self._runtime_state.is_running:
            try:
                if not await self._runtime_session_service.is_active_runtime():
                    break

                config = self._runtime_state.config
                if not self._runtime_state.is_ready or not config.plugin_enabled:
                    await self._sleep(DISABLED_RETRY_SECONDS)
                    continue

                if not await self._bot_api.is_bot_ready():
                    await self._sleep(BOT_READY_RETRY_SECONDS)
                    continue

                monitored_group_ids = [
                    group_id
                    for group_id, group_config in config.monitored_groups.items()
                    if group_config.enabled and group_config.member_profile_polling_enabled
                ]

                if not monitored_group_ids:
                    await self._sleep(
                        min(
                            config.member_profile_poll_interval_seconds,
                            NO_GROUPS_MAX_IDLE_SECONDS,
                        )
                    )
                    continue

                for group_id in monitored_group_ids:
                    await self._group_runtime_service.run_member_profile_poll_check(group_id)
                    await self._sleep(GROUP_CHECK_SPACING_SECONDS)

                await self._sleep(config.member_profile_poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "[GroupEventLog] member profile poll loop failed: %s",
                    exc,
                    exc_info=True,
                )
                await self._sleep(LOOP_ERROR_RETRY_SECONDS)
