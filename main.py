from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Set

import astrbot.api.event.filter as filter
import astrbot.api.star as star
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from .services.avatar_guard_service import AvatarGuardService
from .services.bot_api_service import BotApiService
from .commands.glog_command_handler import GlogCommandHandler
from .commands.glog_config_service import GlogConfigService
from .commands.glog_group_service import GlogGroupService
from .commands.group_context_service import GroupContextService
from .services.group_name_guard_service import GroupNameGuardService
from .runtime.group_runtime_service import GroupRuntimeService
from .runtime.group_task_coordinator import GroupTaskCoordinator
from .services.log_dispatch_service import LogDispatchService
from .services.message_recall_service import MessageRecallService
from .services.member_profile_service import MemberProfileService
from .runtime.notice_event_handler import NoticeEventHandler
from .runtime.passive_message_handler import PassiveMessageHandler
from .platforms.permissions import PermissionService
from .runtime.plugin_runtime_state import PluginRuntimeState
from .runtime.polling_scheduler import PollingSchedulerService
from .storage.persistence import ConfigPersistence
from .runtime.runtime_config_store import RuntimeConfigStore
from .runtime.runtime_session_service import RuntimeSessionService


@star.register(
    "astrbot_plugin_group_event_log",
    "p1930n",
    "Group event log plugin for NapCat or OneBot notice routing.",
    "0.8.0",
    "",
)
class GroupEventLogPlugin(star.Star):
    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self._persistence = ConfigPersistence(
            plugin_dir=Path(__file__).parent,
            runtime_root=Path.cwd(),
        )
        self._runtime_state = PluginRuntimeState()
        self._runtime_config_store = RuntimeConfigStore(
            self._persistence,
            self._runtime_state,
        )
        self._runtime_session_service = RuntimeSessionService(
            self._persistence,
            self._runtime_state,
            runtime_token=uuid.uuid4().hex,
        )
        self._permissions = PermissionService(context)
        self._group_context_service = GroupContextService(self._permissions)
        self._bot_api = BotApiService(self._permissions)
        self._log_dispatcher = LogDispatchService(self._bot_api)
        self._message_recall_service = MessageRecallService(self._log_dispatcher)
        self._avatar_guard = AvatarGuardService(
            self._persistence,
            self._bot_api,
            self._log_dispatcher,
        )
        self._member_profile_service = MemberProfileService(
            self._persistence,
            self._bot_api,
            self._log_dispatcher,
        )
        self._group_name_guard = GroupNameGuardService(
            self._persistence,
            self._bot_api,
            self._log_dispatcher,
        )
        self._group_runtime_service = GroupRuntimeService(
            self._runtime_config_store,
            self._persistence,
            self._bot_api,
            self._avatar_guard,
            self._group_name_guard,
            self._member_profile_service,
            GroupTaskCoordinator(),
        )
        self._polling_scheduler = PollingSchedulerService(
            self._bot_api,
            self._runtime_state,
            self._runtime_session_service,
            self._group_runtime_service,
        )
        self._passive_message_handler = PassiveMessageHandler(
            self._runtime_state,
            self._group_context_service,
            self._message_recall_service,
            self._group_runtime_service,
        )
        self._notice_event_handler = NoticeEventHandler(
            self._runtime_state,
            self._log_dispatcher,
            self._message_recall_service,
            self._group_runtime_service,
        )
        self._glog_config_service = GlogConfigService(
            self._permissions,
            self._runtime_state,
            self._runtime_config_store,
            self._group_context_service,
            self._message_recall_service,
        )
        self._glog_group_service = GlogGroupService(
            self._runtime_state,
            self._group_context_service,
            self._group_runtime_service,
        )
        self._command_handler = GlogCommandHandler(
            self._glog_config_service,
            self._glog_group_service,
        )
        self._background_tasks: Set[asyncio.Task] = set()
        asyncio.create_task(self._initialize())

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
        except Exception as exc:
            logger.error("[GroupEventLog] init failed: %s", exc, exc_info=True)

    def _register_task(self, task: asyncio.Task) -> asyncio.Task:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

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
