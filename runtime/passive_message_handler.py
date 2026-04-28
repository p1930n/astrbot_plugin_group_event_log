from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from astrbot.api.event import AstrMessageEvent

    from ..commands.command_context import CommandContext
    from ..domain.member_profile import normalize_sender_profile
    from ..services.message_recall_service import MessageRecallService
    from ..domain.models import PluginConfig, SourceGroupConfig
except ImportError:
    AstrMessageEvent = Any

    from commands.command_context import CommandContext
    from domain.member_profile import normalize_sender_profile
    from services.message_recall_service import MessageRecallService
    from domain.models import SourceGroupConfig

if TYPE_CHECKING:
    try:
        from ..commands.group_context_service import GroupContextService
        from ..runtime.group_runtime_service import GroupRuntimeService
        from ..runtime.plugin_runtime_state import PluginRuntimeState
    except ImportError:
        from commands.group_context_service import GroupContextService
        from runtime.group_runtime_service import GroupRuntimeService
        from runtime.plugin_runtime_state import PluginRuntimeState


class PassiveMessageHandler:
    """封装群消息事件中的缓存与被动资料更新路由。"""

    def __init__(
        self,
        runtime_state: "PluginRuntimeState",
        group_context_service: "GroupContextService",
        message_recall_service: MessageRecallService,
        group_runtime_service: "GroupRuntimeService",
    ) -> None:
        self._runtime_state = runtime_state
        self._group_context_service = group_context_service
        self._message_recall_service = message_recall_service
        self._group_runtime_service = group_runtime_service

    async def handle_group_message(self, event: AstrMessageEvent) -> None:
        context = CommandContext.from_event(event)
        group_id = self._group_context_service.current_group_id(context)
        if not group_id:
            return

        config = self._runtime_state.config
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

        push_group_ids = self._group_runtime_service.resolve_enabled_push_targets(source_config)
        await self._group_runtime_service.handle_passive_member_profile(
            group_id,
            user_id,
            sender_profile.card,
            sender_profile.nickname,
            push_group_ids,
        )
