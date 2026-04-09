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
        from .models import PluginConfig
    except ImportError:
        from bot_api_service import BotApiService
        from models import PluginConfig


BOT_READY_RETRY_SECONDS = 5
DISABLED_RETRY_SECONDS = 10
NO_GROUPS_MAX_IDLE_SECONDS = 60
GROUP_CHECK_SPACING_SECONDS = 1
LOOP_ERROR_RETRY_SECONDS = 30


class PollingSchedulerService:
    def __init__(
        self,
        bot_api: "BotApiService",
        is_active_runtime: Callable[[], Awaitable[bool]],
        is_plugin_ready: Callable[[], bool],
        is_running: Callable[[], bool],
        get_config: Callable[[], "PluginConfig"],
        run_avatar_check: Callable[[str], Awaitable[None]],
        run_member_profile_check: Callable[[str], Awaitable[None]],
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._bot_api = bot_api
        self._is_active_runtime = is_active_runtime
        self._is_plugin_ready = is_plugin_ready
        self._is_running = is_running
        self._get_config = get_config
        self._run_avatar_check = run_avatar_check
        self._run_member_profile_check = run_member_profile_check
        self._sleep = sleep_func

    async def avatar_poll_loop(self) -> None:
        while self._is_running():
            try:
                if not await self._is_active_runtime():
                    break

                config = self._get_config()
                if not self._is_plugin_ready() or not config.plugin_enabled:
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
                    await self._run_avatar_check(group_id)
                    await self._sleep(GROUP_CHECK_SPACING_SECONDS)

                await self._sleep(config.avatar_poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[GroupEventLog] avatar poll loop failed: %s", exc, exc_info=True)
                await self._sleep(LOOP_ERROR_RETRY_SECONDS)

    async def member_profile_poll_loop(self) -> None:
        while self._is_running():
            try:
                if not await self._is_active_runtime():
                    break

                config = self._get_config()
                if not self._is_plugin_ready() or not config.plugin_enabled:
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
                    await self._run_member_profile_check(group_id)
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
