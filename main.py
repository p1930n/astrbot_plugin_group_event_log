from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Set

import astrbot.api.event.filter as filter
import astrbot.api.star as star
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from .avatar_guard_models import AvatarHashStatus
from .avatar_hash import (
    AvatarHashTransition,
    summarize_avatar_hash_state,
    summarize_avatar_hash_transition,
)
from .avatar_guard_service import AvatarGuardService
from .avatar_probe import build_avatar_probe_record, summarize_avatar_probe
from .bot_api_service import BotApiService
from .glog_command_handler import GlogCommandHandler
from .glog_config_service import GlogConfigService
from .glog_group_service import GlogGroupService
from .group_context_service import GroupContextService
from .group_name_guard import summarize_group_name_guard
from .group_name_guard_service import GroupNameGuardService
from .group_task_coordinator import GroupTaskCoordinator
from .log_dispatch_service import LogDispatchService
from .message_recall_service import MessageRecallService
from .member_profile import (
    MemberProfileChange,
    summarize_member_profile_state,
)
from .member_profile_service import MemberProfileService
from .models import PluginConfig, SourceGroupConfig
from .notice_adapter import GroupNoticeEvent
from .notice_event_handler import NoticeEventHandler
from .passive_message_handler import PassiveMessageHandler
from .permissions import PermissionService
from .polling_scheduler import PollingSchedulerService
from .persistence import ConfigPersistence


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
        self._permissions = PermissionService(context)
        self._group_context_service = GroupContextService(self._permissions)
        self._bot_api = BotApiService(self._permissions)
        self._log_dispatcher = LogDispatchService(self._bot_api)
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
        self._polling_scheduler = PollingSchedulerService(
            self._bot_api,
            self._is_active_runtime,
            lambda: self._is_ready,
            lambda: self._is_running,
            lambda: self._config,
            self._run_avatar_poll_check,
            self._run_member_profile_poll_check,
        )
        self._config = PluginConfig()
        self._message_recall_service = MessageRecallService(self._log_dispatcher)
        self._passive_message_handler = PassiveMessageHandler(
            lambda: self._config,
            self._group_context_service.current_group_id,
            self._get_enabled_push_targets,
            self._message_recall_service,
            self._handle_passive_member_profile,
        )
        self._notice_event_handler = NoticeEventHandler(
            lambda: self._config,
            self._get_enabled_push_targets,
            self._log_dispatcher,
            self._message_recall_service,
            self._handle_group_name_rollback,
        )
        self._glog_config_service = GlogConfigService(
            self._permissions,
            lambda: self._config,
            self._save_config,
            self._group_context_service.current_group_id,
            self._group_context_service.can_manage_source_group,
            self._group_context_service.resolve_bind_args,
            self._message_recall_service.clear_group_cache,
        )
        self._glog_group_service = GlogGroupService(
            lambda: self._config,
            self._group_context_service.current_group_id,
            self._group_context_service.can_manage_source_group,
            self._group_context_service.can_query_group_metadata,
            self._cmd_avatar_probe,
            self._cmd_avatar_check,
            self._cmd_avatar_status,
            self._cmd_member_check,
            self._cmd_member_status,
            self._cmd_rollback_avatar,
            self._cmd_rollback_group_name,
        )
        self._command_handler = GlogCommandHandler(
            self._glog_config_service,
            self._glog_group_service,
        )
        self._runtime_token = uuid.uuid4().hex
        self._group_task_coordinator = GroupTaskCoordinator()
        self._background_tasks: Set[asyncio.Task] = set()
        self._is_ready = False
        self._is_running = True
        self._inactive_logged = False
        self._save_lock = asyncio.Lock()
        asyncio.create_task(self._initialize())

    async def _initialize(self) -> None:
        try:
            config_data = await self._persistence.load_config()
            self._config = PluginConfig.from_dict(config_data)
            await self._persistence.save_runtime_owner(self._runtime_token)
            self._is_ready = True
            self._register_task(asyncio.create_task(self._polling_scheduler.avatar_poll_loop()))
            self._register_task(
                asyncio.create_task(self._polling_scheduler.member_profile_poll_loop())
            )
            logger.info(
                "[GroupEventLog] ready monitored=%s push=%s",
                len(self._config.monitored_groups),
                len(self._config.push_groups),
            )
        except Exception as exc:
            logger.error("[GroupEventLog] init failed: %s", exc, exc_info=True)

    async def _save_config(self) -> None:
        async with self._save_lock:
            self._config.last_updated = datetime.now().isoformat(timespec="seconds")
            await self._persistence.save_config(self._config.to_dict())

    def _register_task(self, task: asyncio.Task) -> asyncio.Task:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    @filter.command("glog")
    async def glog(self, event: AstrMessageEvent):
        """Manage the group event log plugin."""
        if not await self._is_active_runtime():
            return MessageEventResult()
        if not self._is_ready:
            return MessageEventResult().message("plugin is still loading")
        return await self._command_handler.handle_glog(event)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """Passively detect member card or nickname changes when the user speaks."""
        if not await self._is_active_runtime():
            return MessageEventResult()
        if not self._is_ready or not self._config.plugin_enabled:
            return MessageEventResult()
        await self._passive_message_handler.handle_group_message(event)
        return MessageEventResult()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_raw_notice(self, event: AstrMessageEvent):
        """Silently listen for NapCat or OneBot group notice events."""
        if not await self._is_active_runtime():
            return MessageEventResult()
        if not self._is_ready or not self._config.plugin_enabled:
            return MessageEventResult()

        raw = getattr(event, "message_obj", None)
        if not raw or not hasattr(raw, "raw_message"):
            return MessageEventResult()
        if not isinstance(raw.raw_message, dict):
            return MessageEventResult()

        await self._notice_event_handler.handle_raw_notice(event, raw.raw_message)
        return MessageEventResult()

    async def _cmd_rollback_avatar(
        self,
        group_id: str,
        source_config: SourceGroupConfig,
        enabled: bool,
    ) -> MessageEventResult:
        if enabled:
            transition, _ = await self._check_group_avatar(
                group_id,
                trigger="rollback_baseline_refresh",
                emit_logs=False,
                force_adopt_baseline=True,
            )
            if transition.status == AvatarHashStatus.FETCH_FAILED:
                return MessageEventResult().message(
                    f"avatar rollback baseline refresh failed: {transition.error}"
                )

        source_config.avatar_rollback_enabled = enabled
        await self._save_config()
        return MessageEventResult().message(
            f"avatar rollback for {group_id} set to {'on' if enabled else 'off'}"
        )

    async def _cmd_rollback_group_name(
        self,
        group_id: str,
        source_config: SourceGroupConfig,
        enabled: bool,
    ) -> MessageEventResult:
        if enabled:
            success, baseline_name, error = await self._group_name_guard.refresh_baseline(
                group_id
            )
            if not success:
                return MessageEventResult().message(
                    f"group name rollback baseline refresh failed: {error}"
                )
        else:
            baseline_name = ""

        source_config.group_name_rollback_enabled = enabled
        await self._save_config()
        suffix = f"\nbaseline_name: {baseline_name}" if baseline_name else ""
        return MessageEventResult().message(
            f"group name rollback for {group_id} set to {'on' if enabled else 'off'}{suffix}"
        )

    async def _cmd_avatar_probe(
        self, event: AstrMessageEvent, group_id: str
    ) -> MessageEventResult:
        bot = await self._bot_api.get_bot(event)
        if not bot or not hasattr(bot, "api"):
            return MessageEventResult().message("no bot api available")

        group_info = await self._bot_api.call_group_metadata_api_with_bot(
            bot,
            "get_group_info",
            group_id,
        )
        group_info_ex = await self._bot_api.call_group_metadata_api_with_bot(
            bot,
            "get_group_info_ex",
            group_id,
        )
        record = build_avatar_probe_record(group_id, group_info, group_info_ex)
        saved_path = await self._persistence.save_avatar_probe(group_id, record)

        lines = summarize_avatar_probe(record)
        lines.append(f"saved_to: {saved_path}")
        return MessageEventResult().message("\n".join(lines))

    async def _cmd_avatar_check(self, group_id: str) -> MessageEventResult:
        transition, sent_push_groups = await self._check_group_avatar(
            group_id, trigger="manual", emit_logs=True
        )
        lines = summarize_avatar_hash_transition(transition, sent_push_groups)
        lines.append(f"state_db_path: {self._persistence.database_path}")
        lines.append(f"state_record_key: avatar_hash_states/{group_id}")
        return MessageEventResult().message("\n".join(lines))

    async def _cmd_avatar_status(self, group_id: str) -> MessageEventResult:
        state = await self._persistence.load_avatar_hash_state(group_id)
        record = await self._persistence.load_avatar_probe(group_id)
        group_name_state = await self._persistence.load_group_name_guard(group_id)
        if not state and not record:
            if not group_name_state:
                return MessageEventResult().message(
                    f"no avatar or group-name data found for group {group_id}"
                )

        lines: list[str] = []
        if state:
            lines.extend(summarize_avatar_hash_state(state))
            lines.append(f"hash_state_db_path: {self._persistence.database_path}")
            lines.append(f"hash_state_record_key: avatar_hash_states/{group_id}")
        if group_name_state:
            if lines:
                lines.append("----")
            lines.extend(summarize_group_name_guard(group_name_state))
            lines.append(f"group_name_state_db_path: {self._persistence.database_path}")
            lines.append(
                f"group_name_state_record_key: group_name_guard_states/{group_id}"
            )
        if record:
            if lines:
                lines.append("----")
            lines.extend(summarize_avatar_probe(record))
            lines.append(f"probe_snapshot_path: {self._persistence.avatar_probe_path(group_id)}")
        return MessageEventResult().message("\n".join(lines))

    async def _cmd_member_check(self, group_id: str) -> MessageEventResult:
        state, changes, push_group_ids = await self._check_group_member_profiles(
            group_id,
            detection_mode="manual_snapshot",
            emit_logs=True,
        )
        lines = summarize_member_profile_state(state)
        lines.append(f"detected_changes: {len(changes)}")
        lines.append("logs_sent_to: " + (", ".join(push_group_ids) if push_group_ids else "-"))
        lines.append(f"member_profile_state_db_path: {self._persistence.database_path}")
        lines.append(f"member_profile_state_record_key: member_profile_states/{group_id}")
        return MessageEventResult().message("\n".join(lines))

    async def _cmd_member_status(self, group_id: str) -> MessageEventResult:
        state = await self._persistence.load_member_profile_state(group_id)
        if not state:
            return MessageEventResult().message(
                f"no member profile snapshot found for group {group_id}"
            )

        lines = summarize_member_profile_state(state)
        lines.append(f"member_profile_state_db_path: {self._persistence.database_path}")
        lines.append(f"member_profile_state_record_key: member_profile_states/{group_id}")
        return MessageEventResult().message("\n".join(lines))

    def _get_enabled_push_targets(self, source_config: SourceGroupConfig) -> list[str]:
        result: list[str] = []
        for push_group_id in source_config.push_group_ids:
            push_group = self._config.push_groups.get(push_group_id)
            if push_group and push_group.enabled:
                result.append(push_group_id)
        return result

    async def _run_avatar_poll_check(self, group_id: str) -> None:
        await self._check_group_avatar(group_id, trigger="poll", emit_logs=True)

    async def _run_member_profile_poll_check(self, group_id: str) -> None:
        await self._check_group_member_profiles(
            group_id,
            detection_mode="polling_snapshot",
            emit_logs=True,
        )

    async def _check_group_avatar(
        self,
        group_id: str,
        trigger: str,
        emit_logs: bool,
        force_adopt_baseline: bool = False,
    ) -> tuple[AvatarHashTransition, list[str]]:
        async with self._group_task_coordinator.avatar_lock(group_id):
            source_config = self._config.monitored_groups.get(group_id)
            push_group_ids = self._get_enabled_push_targets(source_config) if source_config else []
            return await self._avatar_guard.check_group_avatar(
                group_id,
                source_config,
                push_group_ids,
                trigger,
                emit_logs,
                force_adopt_baseline=force_adopt_baseline,
            )

    async def _handle_passive_member_profile(
        self,
        group_id: str,
        user_id: str,
        card: str | None,
        nickname: str | None,
        push_group_ids: list[str],
    ) -> None:
        async with self._group_task_coordinator.member_profile_lock(group_id):
            await self._member_profile_service.handle_passive_member_profile(
                group_id,
                user_id,
                card,
                nickname,
                push_group_ids,
            )

    async def _check_group_member_profiles(
        self,
        group_id: str,
        detection_mode: str,
        emit_logs: bool,
    ) -> tuple[dict[str, object], list[MemberProfileChange], list[str]]:
        async with self._group_task_coordinator.member_profile_lock(group_id):
            source_config = self._config.monitored_groups.get(group_id)
            push_group_ids = (
                self._get_enabled_push_targets(source_config)
                if source_config and source_config.enabled
                else []
            )
            return await self._member_profile_service.check_group_member_profiles(
                group_id,
                detection_mode,
                emit_logs,
                push_group_ids,
            )

    async def _handle_group_name_rollback(
        self,
        notice: GroupNoticeEvent,
        push_group_ids: list[str],
    ) -> None:
        async with self._group_task_coordinator.group_name_lock(notice.group_id):
            await self._group_name_guard.handle_rollback(notice, push_group_ids)

    async def _is_active_runtime(self) -> bool:
        owner = await self._persistence.load_runtime_owner()
        active = owner == self._runtime_token
        if not active:
            self._is_running = False
            if not self._inactive_logged:
                logger.info("[GroupEventLog] stale instance detected, stopping old runtime")
                self._inactive_logged = True
        return active
