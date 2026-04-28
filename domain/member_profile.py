from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class MemberProfileChange:
    group_id: str
    user_id: str
    detection_mode: str
    observed_at: str
    old_card: str = ""
    new_card: str = ""
    old_nickname: str = ""
    new_nickname: str = ""

    @property
    def changed_fields(self) -> list[str]:
        fields: list[str] = []
        if self.old_card != self.new_card:
            fields.append("card")
        if self.old_nickname != self.new_nickname:
            fields.append("nickname")
        return fields


@dataclass(slots=True)
class SenderProfileObservation:
    user_id: str
    card: str | None
    nickname: str | None


def build_member_profile_entry(
    user_id: str,
    card: str,
    nickname: str,
    observed_at: str,
) -> dict[str, str]:
    return {
        "user_id": user_id,
        "card": card,
        "nickname": nickname,
        "last_seen_at": observed_at,
    }


def build_member_profile_state(group_id: str) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "last_scan_at": "",
        "last_update_mode": "",
        "member_count": 0,
        "change_count": 0,
        "last_error": "",
        "members": {},
    }


def apply_passive_member_profile(
    state: dict[str, Any] | None,
    group_id: str,
    user_id: str,
    card: str | None,
    nickname: str | None,
    detection_mode: str,
) -> tuple[dict[str, Any], MemberProfileChange | None]:
    observed_at = _now()
    state = _normalize_state(group_id, state)
    members = state["members"]
    previous = members.get(user_id)
    current_entry = _build_passive_entry(
        previous,
        user_id,
        card,
        nickname,
        observed_at,
    )

    if not previous:
        members[user_id] = current_entry
        state["member_count"] = len(members)
        state["last_scan_at"] = observed_at
        state["last_update_mode"] = detection_mode
        state["last_error"] = ""
        return state, None

    change = _build_change(group_id, user_id, previous, current_entry, detection_mode, observed_at)
    members[user_id] = current_entry
    state["member_count"] = len(members)
    state["last_scan_at"] = observed_at
    state["last_update_mode"] = detection_mode
    state["last_error"] = ""
    if change:
        state["change_count"] = int(state.get("change_count", 0) or 0) + 1
    return state, change


def apply_polled_member_profiles(
    state: dict[str, Any] | None,
    group_id: str,
    current_members: list[dict[str, str]],
) -> tuple[dict[str, Any], list[MemberProfileChange]]:
    observed_at = _now()
    state = _normalize_state(group_id, state)
    previous_members = state["members"]

    next_members: dict[str, dict[str, str]] = {}
    changes: list[MemberProfileChange] = []

    for member in current_members:
        user_id = member["user_id"]
        previous = previous_members.get(user_id)
        next_entry = build_member_profile_entry(
            user_id,
            member.get("card", ""),
            _normalize_observed_nickname(
                user_id,
                member.get("nickname", ""),
                member.get("card", ""),
                _profile_text(previous, "card"),
                _profile_text(previous, "nickname"),
            ),
            observed_at,
        )
        change = _build_change(
            group_id,
            user_id,
            previous,
            next_entry,
            "polling_snapshot",
            observed_at,
        )
        if change:
            changes.append(change)
        next_members[user_id] = next_entry

    state["members"] = next_members
    state["member_count"] = len(next_members)
    state["last_scan_at"] = observed_at
    state["last_update_mode"] = "polling_snapshot"
    state["last_error"] = ""
    if changes:
        state["change_count"] = int(state.get("change_count", 0) or 0) + len(changes)
    return state, changes


def summarize_member_profile_state(state: dict[str, Any]) -> list[str]:
    return [
        "member profile state",
        f"group_id: {state.get('group_id', '-')}",
        f"member_count: {state.get('member_count', 0)}",
        f"change_count: {state.get('change_count', 0)}",
        f"last_scan_at: {state.get('last_scan_at', '-')}",
        f"last_update_mode: {state.get('last_update_mode', '-')}",
        f"last_error: {state.get('last_error', '-')}",
    ]


def normalize_sender_profile(sender: dict[str, Any] | None) -> SenderProfileObservation:
    sender = sender or {}
    return SenderProfileObservation(
        user_id=str(sender.get("user_id", "")).strip(),
        card=_optional_sender_text(sender, "card"),
        nickname=_optional_sender_text(sender, "nickname"),
    )


def normalize_member_list_payload(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, list):
        return []

    results: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        user_id = str(item.get("user_id", "")).strip()
        if not user_id:
            continue
        results.append(
            {
                "user_id": user_id,
                "card": str(item.get("card", "") or "").strip(),
                "nickname": str(item.get("nickname", "") or "").strip(),
            }
        )
    return results


def _normalize_state(group_id: str, state: dict[str, Any] | None) -> dict[str, Any]:
    state = dict(state or {})
    state.setdefault("group_id", group_id)
    state.setdefault("last_scan_at", "")
    state.setdefault("last_update_mode", "")
    state.setdefault("member_count", 0)
    state.setdefault("change_count", 0)
    state.setdefault("last_error", "")
    state.setdefault("members", {})
    return state


def _build_change(
    group_id: str,
    user_id: str,
    previous: dict[str, Any] | None,
    current: dict[str, str],
    detection_mode: str,
    observed_at: str,
) -> MemberProfileChange | None:
    if not previous:
        return None

    old_card = str(previous.get("card", "") or "").strip()
    old_nickname = str(previous.get("nickname", "") or "").strip()
    new_card = current.get("card", "")
    new_nickname = current.get("nickname", "")

    if old_card == new_card and old_nickname == new_nickname:
        return None

    return MemberProfileChange(
        group_id=group_id,
        user_id=user_id,
        detection_mode=detection_mode,
        observed_at=observed_at,
        old_card=old_card,
        new_card=new_card,
        old_nickname=old_nickname,
        new_nickname=new_nickname,
    )


def _build_passive_entry(
    previous: dict[str, Any] | None,
    user_id: str,
    observed_card: str | None,
    observed_nickname: str | None,
    observed_at: str,
) -> dict[str, str]:
    previous_card = _profile_text(previous, "card")
    previous_nickname = _profile_text(previous, "nickname")
    current_card = _merge_passive_card(previous_card, observed_card, observed_nickname)
    current_nickname = previous_nickname

    if observed_nickname is not None:
        current_nickname = _normalize_observed_nickname(
            user_id,
            observed_nickname,
            observed_card,
            previous_card,
            previous_nickname,
        )
    elif previous is None:
        current_nickname = ""

    return build_member_profile_entry(user_id, current_card, current_nickname, observed_at)


def _merge_passive_card(
    previous_card: str,
    observed_card: str | None,
    observed_nickname: str | None,
) -> str:
    if observed_card is None:
        return previous_card
    if observed_card:
        return observed_card
    if not previous_card:
        return ""
    if not observed_nickname or _looks_like_display_name_alias(
        observed_nickname,
        observed_card,
        previous_card,
    ):
        return previous_card
    return ""


def _looks_like_display_name_alias(
    nickname: str,
    observed_card: str | None,
    previous_card: str,
) -> bool:
    nickname = nickname.strip()
    if not nickname:
        return False

    # Group message payloads may expose the rendered sender name here, which can
    # be the member card instead of the account nickname. Ignore that alias in
    # passive mode so it does not fight with polling snapshots.
    candidate_cards = {
        value.strip()
        for value in (observed_card, previous_card)
        if isinstance(value, str) and value.strip()
    }
    return nickname in candidate_cards


def _normalize_observed_nickname(
    user_id: str,
    observed_nickname: str,
    observed_card: str | None,
    previous_card: str,
    previous_nickname: str,
) -> str:
    observed_nickname = observed_nickname.strip()
    if not observed_nickname:
        return previous_nickname
    if _looks_like_display_name_alias(observed_nickname, observed_card, previous_card):
        return previous_nickname
    if _looks_like_user_id_placeholder(observed_nickname, user_id):
        return previous_nickname
    return observed_nickname


def _looks_like_user_id_placeholder(nickname: str, user_id: str) -> bool:
    nickname = nickname.strip()
    user_id = user_id.strip()
    return bool(nickname and user_id and nickname == user_id)


def _optional_sender_text(sender: dict[str, Any], key: str) -> str | None:
    if key not in sender:
        return None
    return str(sender.get(key, "") or "").strip()


def _profile_text(profile: dict[str, Any] | None, key: str) -> str:
    if not isinstance(profile, dict):
        return ""
    return str(profile.get(key, "") or "").strip()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
