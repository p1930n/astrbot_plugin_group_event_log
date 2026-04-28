from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent

    from ..services.log_dispatch_service import LogDispatchService
    from ..services.message_recall_service import MessageRecallService
    from ..domain.models import SourceGroupConfig
    from ..domain.notice_adapter import GroupNoticeEvent, parse_group_notice
except ImportError:
    logger = logging.getLogger(__name__)
    AstrMessageEvent = Any

    from services.log_dispatch_service import LogDispatchService
    from services.message_recall_service import MessageRecallService
    from domain.models import SourceGroupConfig
    from domain.notice_adapter import GroupNoticeEvent, parse_group_notice

if TYPE_CHECKING:
    try:
        from ..runtime.group_runtime_service import GroupRuntimeService
        from ..runtime.plugin_runtime_state import PluginRuntimeState
    except ImportError:
        from runtime.group_runtime_service import GroupRuntimeService
        from runtime.plugin_runtime_state import PluginRuntimeState


class NoticeEventHandler:
    """封装 notice 事件的解析、配置校验和分发。"""

    def __init__(
        self,
        runtime_state: "PluginRuntimeState",
        log_dispatcher: LogDispatchService,
        message_recall_service: MessageRecallService,
        group_runtime_service: "GroupRuntimeService",
    ) -> None:
        self._runtime_state = runtime_state
        self._log_dispatcher = log_dispatcher
        self._message_recall_service = message_recall_service
        self._group_runtime_service = group_runtime_service

    async def handle_raw_notice(
        self,
        event: AstrMessageEvent,
        payload: dict[str, Any],
    ) -> None:
        config = self._runtime_state.config
        if config.debug_raw_notice and payload.get("post_type") == "notice":
            logger.info("[GroupEventLog] raw notice payload: %s", payload)

        notice = parse_group_notice(payload)
        if not notice:
            return

        source_config = config.monitored_groups.get(notice.group_id)
        if not source_config or not source_config.enabled:
            return
        if not source_config.event_switches.get(notice.event_key, False):
            return
        if not self._self_operation_notice_enabled(source_config, notice):
            return

        push_group_ids = self._group_runtime_service.resolve_enabled_push_targets(source_config)
        if notice.event_key == "group_recall":
            await self._message_recall_service.handle_group_recall(
                event,
                notice,
                push_group_ids,
                source_config.recall_message_enabled,
            )
            return

        if push_group_ids:
            await self._log_dispatcher.dispatch_notice_logs(event, notice, push_group_ids)
        if notice.event_key == "notify.group_name" and source_config.group_name_rollback_enabled:
            await self._group_runtime_service.handle_group_name_rollback(notice, push_group_ids)

    def _self_operation_notice_enabled(
        self,
        source_config: SourceGroupConfig,
        notice: GroupNoticeEvent,
    ) -> bool:
        switch_key = self._self_operation_switch_key(notice)
        if not switch_key:
            return True
        return source_config.event_switches.get(switch_key, True)

    def _self_operation_switch_key(self, notice: GroupNoticeEvent) -> str:
        self_id = notice.self_id.strip()
        if not self_id or notice.operator_id != self_id:
            return ""

        if notice.event_key == "group_decrease" and notice.sub_type == "kick":
            return "bot_kick_member"
        if notice.event_key == "group_ban":
            return "bot_ban_member"
        if notice.event_key == "group_recall":
            if notice.user_id == self_id:
                return "bot_recall_own_message"
            if notice.user_id:
                return "bot_recall_other_message"
        return ""
