from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_NOTICE_EVENTS = {
    "group_increase",
    "group_decrease",
    "group_ban",
    "group_card",
    "group_admin",
    "group_recall",
    "notify.group_name",
    "notify.title",
}


@dataclass(slots=True)
class GroupNoticeEvent:
    event_key: str
    notice_type: str
    sub_type: str
    group_id: str
    user_id: str = ""
    operator_id: str = ""
    self_id: str = ""
    details: dict[str, str] = field(default_factory=dict)
    summary: str = ""


def parse_group_notice(payload: dict[str, Any] | None) -> GroupNoticeEvent | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("post_type") != "notice":
        return None

    group_id = _to_text(payload.get("group_id"))
    if not group_id:
        return None

    notice_type = _to_text(payload.get("notice_type"))
    sub_type = _to_text(payload.get("sub_type"))
    if not notice_type:
        return None

    event_key = f"notify.{sub_type}" if notice_type == "notify" and sub_type else notice_type
    if event_key not in SUPPORTED_NOTICE_EVENTS:
        return None

    user_id = _to_text(payload.get("user_id"))
    operator_id = _to_text(payload.get("operator_id"))
    self_id = _to_text(payload.get("self_id"))
    details = _extract_details(event_key, payload)
    details["time_raw"] = _to_text(payload.get("time"))
    summary = _build_summary(event_key, sub_type, details)

    return GroupNoticeEvent(
        event_key=event_key,
        notice_type=notice_type,
        sub_type=sub_type,
        group_id=group_id,
        user_id=user_id,
        operator_id=operator_id,
        self_id=self_id,
        details=details,
        summary=summary,
    )


def _extract_details(event_key: str, payload: dict[str, Any]) -> dict[str, str]:
    details: dict[str, str] = {}

    if event_key == "group_ban":
        details["duration"] = _to_text(payload.get("duration"))
    elif event_key == "group_recall":
        details["message_id"] = _to_text(payload.get("message_id"))
    elif event_key == "group_card":
        details["card_old"] = _to_text(payload.get("card_old"))
        details["card_new"] = _to_text(payload.get("card_new"))
    elif event_key == "notify.group_name":
        details["name_new"] = _to_text(payload.get("name_new"))
    elif event_key == "notify.title":
        details["title"] = _to_text(payload.get("title"))

    return details


def _build_summary(event_key: str, sub_type: str, details: dict[str, str]) -> str:
    if event_key == "group_increase":
        if sub_type == "approve":
            return "member joined by approval"
        if sub_type == "invite":
            return "member joined by invite"
        return "member joined"

    if event_key == "group_decrease":
        if sub_type == "leave":
            return "member left group"
        if sub_type == "kick":
            return "member was kicked"
        if sub_type == "kick_me":
            return "bot was kicked"
        if sub_type == "disband":
            return "group was disbanded"
        return "member left group"

    if event_key == "group_ban":
        if sub_type == "lift_ban":
            return "member mute removed"
        duration = details.get("duration") or "0"
        return f"member muted for {duration}s"

    if event_key == "group_recall":
        return "group message recalled"

    if event_key == "group_card":
        return "member card changed"

    if event_key == "group_admin":
        return "admin granted" if sub_type == "set" else "admin removed"

    if event_key == "notify.group_name":
        return "group name changed"

    if event_key == "notify.title":
        return "group title changed"

    return event_key


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
