from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

try:
    from ..domain.member_profile import (
        MemberProfileChange,
        apply_passive_member_profile,
        apply_polled_member_profiles,
        normalize_member_list_payload,
    )
except ImportError:
    from domain.member_profile import (
        MemberProfileChange,
        apply_passive_member_profile,
        apply_polled_member_profiles,
        normalize_member_list_payload,
    )

if TYPE_CHECKING:
    try:
        from ..services.bot_api_service import BotApiService
        from ..services.log_dispatch_service import LogDispatchService
    except ImportError:
        from services.bot_api_service import BotApiService
        from services.log_dispatch_service import LogDispatchService


class MemberProfileService:
    def __init__(
        self,
        persistence: Any,
        bot_api: "BotApiService",
        log_dispatcher: "LogDispatchService",
    ) -> None:
        self._persistence = persistence
        self._bot_api = bot_api
        self._log_dispatcher = log_dispatcher

    async def handle_passive_member_profile(
        self,
        group_id: str,
        user_id: str,
        card: str | None,
        nickname: str | None,
        push_group_ids: list[str],
    ) -> None:
        state = await self._persistence.load_member_profile_state(group_id)
        had_member_profile = _has_member_profile_entry(state, user_id)
        state, change = apply_passive_member_profile(
            state,
            group_id,
            user_id,
            card,
            nickname,
            "passive_message",
        )
        if change or not had_member_profile:
            await self._persistence.save_member_profile_state(group_id, state)

        if change and push_group_ids:
            await self._log_dispatcher.dispatch_member_profile_logs(
                group_id,
                push_group_ids,
                [change],
            )

    async def check_group_member_profiles(
        self,
        group_id: str,
        detection_mode: str,
        emit_logs: bool,
        push_group_ids: list[str],
    ) -> tuple[dict[str, object], list[MemberProfileChange], list[str]]:
        state = await self._persistence.load_member_profile_state(group_id)
        result = await self._bot_api.call_group_member_list_api(group_id)
        if not result.get("ok"):
            state = dict(state or {})
            state["group_id"] = group_id
            state["last_scan_at"] = datetime.now().isoformat(timespec="seconds")
            state["last_update_mode"] = detection_mode
            state["last_error"] = str(result.get("error", "unknown error"))
            await self._persistence.save_member_profile_state(group_id, state)
            return state, [], []

        payload = normalize_member_list_payload(result.get("data"))
        state, changes = apply_polled_member_profiles(state, group_id, payload)
        state["last_update_mode"] = detection_mode
        await self._persistence.save_member_profile_state(group_id, state)

        sent_push_groups: list[str] = []
        if changes and emit_logs and push_group_ids:
            sent_push_groups = await self._log_dispatcher.dispatch_member_profile_logs(
                group_id,
                push_group_ids,
                changes,
            )
        return state, changes, sent_push_groups


def _has_member_profile_entry(state: dict[str, object], user_id: str) -> bool:
    members = state.get("members")
    if not isinstance(members, dict):
        return False
    return isinstance(members.get(user_id), dict)
