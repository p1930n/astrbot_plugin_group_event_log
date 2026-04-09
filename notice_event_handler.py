from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent

    from .log_dispatch_service import LogDispatchService
    from .message_recall_service import MessageRecallService
    from .models import PluginConfig, SourceGroupConfig
    from .notice_adapter import GroupNoticeEvent, parse_group_notice
except ImportError:
    logger = logging.getLogger(__name__)
    AstrMessageEvent = Any

    from log_dispatch_service import LogDispatchService
    from message_recall_service import MessageRecallService
    from models import PluginConfig, SourceGroupConfig
    from notice_adapter import GroupNoticeEvent, parse_group_notice

if TYPE_CHECKING:
    GroupNameRollbackHandler = Callable[
        [GroupNoticeEvent, list[str]],
        Awaitable[None],
    ]
    PushTargetResolver = Callable[[SourceGroupConfig], list[str]]
    ConfigProvider = Callable[[], PluginConfig]


class NoticeEventHandler:
    """封装 notice 事件的解析、配置校验和分发。"""

    def __init__(
        self,
        config_provider: "ConfigProvider",
        push_target_resolver: "PushTargetResolver",
        log_dispatcher: LogDispatchService,
        message_recall_service: MessageRecallService,
        group_name_rollback_handler: "GroupNameRollbackHandler",
    ) -> None:
        self._config_provider = config_provider
        self._push_target_resolver = push_target_resolver
        self._log_dispatcher = log_dispatcher
        self._message_recall_service = message_recall_service
        self._group_name_rollback_handler = group_name_rollback_handler

    async def handle_raw_notice(
        self,
        event: AstrMessageEvent,
        payload: dict[str, Any],
    ) -> None:
        config = self._config_provider()
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

        push_group_ids = self._push_target_resolver(source_config)
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
            await self._group_name_rollback_handler(notice, push_group_ids)
