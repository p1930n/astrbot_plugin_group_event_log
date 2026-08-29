from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import astrbot.api.event.filter as filter
import astrbot.api.star as star
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from .runtime.plugin_runtime_factory import build_plugin_runtime


@star.register(
    "astrbot_plugin_group_event_log",
    "p1930n",
    "Group event log plugin for NapCat or OneBot notice routing.",
    "0.8.0",
    "",
)
class GroupEventLogPlugin(star.Star):
    def __init__(self, context: star.Context, config: Any | None = None) -> None:
        super().__init__(context)
        runtime = build_plugin_runtime(
            context,
            config,
            plugin_dir=Path(__file__).parent,
            runtime_root=Path.cwd(),
        )
        self._runtime_state = runtime.runtime_state
        self._runtime_config_store = runtime.runtime_config_store
        self._runtime_session_service = runtime.runtime_session_service
        self._polling_scheduler = runtime.polling_scheduler
        self._passive_message_handler = runtime.passive_message_handler
        self._notice_event_handler = runtime.notice_event_handler
        self._command_handler = runtime.command_handler
        self._background_tasks: set[asyncio.Task] = set()
        self._register_task(asyncio.create_task(self._initialize()))

    async def _initialize(self) -> None:
        try:
            await self._runtime_config_store.load()
            await self._runtime_session_service.register_current_runtime()
            self._runtime_state.is_ready = True
            self._register_task(asyncio.create_task(self._polling_scheduler.avatar_poll_loop()))
            self._register_task(
                asyncio.create_task(self._polling_scheduler.member_profile_poll_loop())
            )
            logger.info(
                "[GroupEventLog] ready monitored=%s push=%s",
                len(self._runtime_state.config.monitored_groups),
                len(self._runtime_state.config.push_groups),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[GroupEventLog] init failed: %s", exc, exc_info=True)

    def _register_task(self, task: asyncio.Task) -> asyncio.Task:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def terminate(self) -> None:
        self._runtime_state.is_running = False
        pending_tasks = [
            task
            for task in tuple(self._background_tasks)
            if not task.done()
        ]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            results = await asyncio.gather(*pending_tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException) and not isinstance(
                    result,
                    asyncio.CancelledError,
                ):
                    logger.error(
                        "[GroupEventLog] background task shutdown failed: %s",
                        result,
                        exc_info=result,
                    )
        self._background_tasks.clear()

    @filter.command("glog")
    async def glog(self, event: AstrMessageEvent):
        """Manage the group event log plugin."""
        if not await self._runtime_session_service.is_active_runtime():
            return MessageEventResult()
        if not self._runtime_state.is_ready:
            return MessageEventResult().message("plugin is still loading")
        return await self._command_handler.handle_glog(event)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """Passively detect member card or nickname changes when the user speaks."""
        if not await self._runtime_session_service.is_active_runtime():
            return MessageEventResult()
        if not self._runtime_state.is_ready or not self._runtime_state.config.plugin_enabled:
            return MessageEventResult()
        await self._passive_message_handler.handle_group_message(event)
        return MessageEventResult()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_raw_notice(self, event: AstrMessageEvent):
        """Silently listen for NapCat or OneBot group notice events."""
        if not await self._runtime_session_service.is_active_runtime():
            return MessageEventResult()
        if not self._runtime_state.is_ready or not self._runtime_state.config.plugin_enabled:
            return MessageEventResult()

        raw = getattr(event, "message_obj", None)
        if not raw or not hasattr(raw, "raw_message"):
            return MessageEventResult()
        if not isinstance(raw.raw_message, dict):
            return MessageEventResult()

        await self._notice_event_handler.handle_raw_notice(event, raw.raw_message)
        return MessageEventResult()
