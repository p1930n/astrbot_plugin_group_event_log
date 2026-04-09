from __future__ import annotations

from typing import Any

try:
    from astrbot.api.event import AstrMessageEvent

    from .log_dispatch_service import LogDispatchService
    from .message_cache import GroupMessageCache, build_cached_group_message
    from .notice_adapter import GroupNoticeEvent
except ImportError:
    AstrMessageEvent = Any

    from log_dispatch_service import LogDispatchService
    from message_cache import GroupMessageCache, build_cached_group_message
    from notice_adapter import GroupNoticeEvent


class MessageRecallService:
    """封装消息缓存与撤回日志链路。"""

    def __init__(
        self,
        log_dispatcher: LogDispatchService,
        message_cache: GroupMessageCache | None = None,
    ) -> None:
        self._log_dispatcher = log_dispatcher
        self._message_cache = message_cache or GroupMessageCache()

    def clear_group_cache(self, group_id: str) -> None:
        self._message_cache.clear_group(group_id)

    def cache_message(
        self,
        payload: dict[str, Any] | None,
        recall_message_enabled: bool,
        fallback_message_str: str = "",
        fallback_message_id: str = "",
    ) -> None:
        cached_message = build_cached_group_message(
            payload,
            fallback_message_str=fallback_message_str,
            fallback_message_id=fallback_message_id,
        )
        if cached_message and recall_message_enabled:
            self._message_cache.store(cached_message)

    async def handle_group_recall(
        self,
        event: AstrMessageEvent,
        notice: GroupNoticeEvent,
        push_group_ids: list[str],
        show_message_content: bool,
    ) -> None:
        cached_message = self._message_cache.pop(
            notice.group_id,
            str(notice.details.get("message_id", "")).strip(),
        )
        await self._log_dispatcher.dispatch_group_recall_logs(
            event,
            notice,
            push_group_ids,
            cached_message,
            show_message_content,
        )
