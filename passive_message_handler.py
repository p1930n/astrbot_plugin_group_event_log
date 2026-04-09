from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

try:
    from astrbot.api.event import AstrMessageEvent

    from .member_profile import normalize_sender_profile
    from .message_recall_service import MessageRecallService
    from .models import PluginConfig, SourceGroupConfig
except ImportError:
    AstrMessageEvent = Any

    from member_profile import normalize_sender_profile
    from message_recall_service import MessageRecallService
    from models import PluginConfig, SourceGroupConfig

if TYPE_CHECKING:
    ConfigProvider = Callable[[], PluginConfig]
    CurrentGroupResolver = Callable[[AstrMessageEvent], str]
    PushTargetResolver = Callable[[SourceGroupConfig], list[str]]
    PassiveMemberProfileHandler = Callable[
        [str, str, str | None, str | None, list[str]],
        Awaitable[None],
    ]


class PassiveMessageHandler:
    """封装群消息事件中的缓存与被动资料更新路由。"""

    def __init__(
        self,
        config_provider: "ConfigProvider",
        current_group_resolver: "CurrentGroupResolver",
        push_target_resolver: "PushTargetResolver",
        message_recall_service: MessageRecallService,
        passive_member_profile_handler: "PassiveMemberProfileHandler",
    ) -> None:
        self._config_provider = config_provider
        self._current_group_resolver = current_group_resolver
        self._push_target_resolver = push_target_resolver
        self._message_recall_service = message_recall_service
        self._passive_member_profile_handler = passive_member_profile_handler

    async def handle_group_message(self, event: AstrMessageEvent) -> None:
        group_id = self._current_group_resolver(event)
        if not group_id:
            return

        config = self._config_provider()
        source_config = config.monitored_groups.get(group_id)
        if not source_config or not source_config.enabled:
            return

        raw = getattr(event, "message_obj", None)
        payload = raw.raw_message if raw and hasattr(raw, "raw_message") else None
        if not isinstance(payload, dict):
            return

        fallback_message_str = str(getattr(raw, "message_str", "") or "").strip()
        fallback_message_id = str(getattr(raw, "message_id", "") or "").strip()
        self._message_recall_service.cache_message(
            payload,
            source_config.recall_message_enabled,
            fallback_message_str=fallback_message_str,
            fallback_message_id=fallback_message_id,
        )

        sender = payload.get("sender", {})
        sender_profile = normalize_sender_profile(sender if isinstance(sender, dict) else {})
        user_id = sender_profile.user_id or str(event.get_sender_id() or "").strip()
        if not user_id:
            return

        push_group_ids = self._push_target_resolver(source_config)
        await self._passive_member_profile_handler(
            group_id,
            user_id,
            sender_profile.card,
            sender_profile.nickname,
            push_group_ids,
        )
