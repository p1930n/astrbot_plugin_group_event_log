from __future__ import annotations

from datetime import datetime

try:
    from .avatar_hash import AvatarHashTransition
    from .message_cache import CachedGroupMessage
    from .member_profile import MemberProfileChange
    from .notice_adapter import GroupNoticeEvent
except ImportError:
    from avatar_hash import AvatarHashTransition
    from message_cache import CachedGroupMessage
    from member_profile import MemberProfileChange
    from notice_adapter import GroupNoticeEvent


def format_notice_log(notice: GroupNoticeEvent, trace_id: str) -> str:
    timestamp = _format_time(notice.details.get("time_raw"))
    lines = [
        "[GROUP_EVENT_LOG]",
        f"time: {timestamp}",
        f"trace_id: {trace_id}",
        f"source_group_id: {notice.group_id}",
        f"event: {notice.event_key}",
        f"summary: {notice.summary}",
    ]

    if notice.notice_type:
        lines.append(f"notice_type: {notice.notice_type}")
    if notice.sub_type:
        lines.append(f"sub_type: {notice.sub_type}")
    if notice.user_id:
        lines.append(f"user_id: {notice.user_id}")
    if notice.operator_id:
        lines.append(f"operator_id: {notice.operator_id}")

    for key in ("duration", "card_old", "card_new", "name_new", "title"):
        value = notice.details.get(key, "")
        if value:
            lines.append(f"{key}: {value}")

    return "\n".join(lines)


def format_avatar_hash_log(
    transition: AvatarHashTransition, trace_id: str, trigger: str
) -> str:
    event_name = (
        "avatar_hash.rollback"
        if transition.rollback_attempted
        else "avatar_hash.changed"
    )
    summary = (
        "group avatar changed and rollback attempted"
        if transition.rollback_attempted
        else "group avatar hash changed"
    )
    lines = [
        "[GROUP_EVENT_LOG]",
        f"time: {_format_time(transition.checked_at)}",
        f"trace_id: {trace_id}",
        f"source_group_id: {transition.group_id}",
        f"event: {event_name}",
        f"summary: {summary}",
        f"trigger: {trigger}",
        f"baseline_hash: {_short_hash(transition.baseline_hash)}",
        f"observed_hash: {_short_hash(transition.observed_hash)}",
    ]

    if transition.previous_hash:
        lines.append(f"previous_hash: {_short_hash(transition.previous_hash)}")

    if transition.byte_size:
        lines.append(f"byte_size: {transition.byte_size}")
    if transition.content_type:
        lines.append(f"content_type: {transition.content_type}")
    if transition.source_url:
        lines.append(f"source_url: {transition.source_url}")
    if transition.rollback_attempted:
        lines.append(
            f"rollback_result: {'success' if transition.rollback_succeeded else 'failed'}"
        )
    if transition.rollback_error:
        lines.append(f"rollback_error: {transition.rollback_error}")

    return "\n".join(lines)


def format_group_name_rollback_log(
    group_id: str,
    trace_id: str,
    observed_name: str,
    baseline_name: str,
    rollback_result: str,
    error: str = "",
) -> str:
    lines = [
        "[GROUP_EVENT_LOG]",
        f"time: {_format_time(None)}",
        f"trace_id: {trace_id}",
        f"source_group_id: {group_id}",
        "event: group_name.rollback",
        "summary: group name changed and rollback attempted",
        f"baseline_name: {baseline_name or '-'}",
        f"observed_name: {observed_name or '-'}",
        f"rollback_result: {rollback_result}",
    ]
    if error:
        lines.append(f"rollback_error: {error}")
    return "\n".join(lines)


def format_member_profile_change_log(
    change: MemberProfileChange,
    trace_id: str,
) -> str:
    lines = [
        "[GROUP_EVENT_LOG]",
        f"time: {_format_time(change.observed_at)}",
        f"trace_id: {trace_id}",
        f"source_group_id: {change.group_id}",
        "event: member_profile.changed",
        "summary: member profile changed",
        f"detection_mode: {change.detection_mode}",
        f"user_id: {change.user_id}",
        f"changed_fields: {', '.join(change.changed_fields) or '-'}",
        f"old_card: {change.old_card or '-'}",
        f"new_card: {change.new_card or '-'}",
        f"old_nickname: {change.old_nickname or '-'}",
        f"new_nickname: {change.new_nickname or '-'}",
    ]
    return "\n".join(lines)


def format_group_recall_log(
    notice: GroupNoticeEvent,
    trace_id: str,
    cached_message: CachedGroupMessage | None,
    show_message_content: bool,
) -> str:
    message_id = str(notice.details.get("message_id", "")).strip() or "-"
    recalled_sender_user_id = (
        cached_message.user_id if cached_message and cached_message.user_id else notice.user_id
    ) or "-"
    lines = [
        "[GROUP_EVENT_LOG]",
        f"time: {_format_time(notice.details.get('time_raw'))}",
        f"trace_id: {trace_id}",
        f"source_group_id: {notice.group_id}",
        "event: group_recall",
        "summary: group message recalled",
        f"recalled_by_user_id: {notice.operator_id or notice.user_id or '-'}",
        f"recalled_sender_user_id: {recalled_sender_user_id}",
    ]

    if not show_message_content:
        lines.append("message_detail: hidden")
        return "\n".join(lines)

    lines.extend(
        [
            f"message_id: {message_id}",
            f"recall_type: {_build_recall_type(notice)}",
            f"recalled_sender_card: {_sender_card(cached_message)}",
            f"recalled_sender_nickname: {_sender_nickname(cached_message)}",
            f"cache_hit: {'true' if cached_message else 'false'}",
        ]
    )

    if cached_message:
        lines.extend(
            [
                f"message_sent_at: {_format_time(cached_message.sent_at)}",
                f"message_text: {_format_inline(cached_message.message_text)}",
                f"message_content: {_format_inline(cached_message.message_content)}",
            ]
        )
    else:
        lines.extend(
            [
                "message_sent_at: -",
                "message_text: -",
                "message_content: cache_miss",
            ]
        )

    return "\n".join(lines)


def _format_time(raw_time: str | None) -> str:
    if not raw_time:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        return datetime.fromtimestamp(int(raw_time)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        try:
            return datetime.fromisoformat(raw_time).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _short_hash(value: str) -> str:
    return value[:12] if value else "-"


def _sender_card(cached_message: CachedGroupMessage | None) -> str:
    if not cached_message:
        return "-"
    return cached_message.sender_card or "-"


def _sender_nickname(cached_message: CachedGroupMessage | None) -> str:
    if not cached_message:
        return "-"
    return cached_message.sender_nickname or "-"


def _build_recall_type(notice: GroupNoticeEvent) -> str:
    if notice.operator_id and notice.user_id and notice.operator_id == notice.user_id:
        return "self_recall"
    if notice.operator_id and notice.user_id:
        return "operator_recall"
    if notice.user_id:
        return "self_recall"
    return "unknown"


def _format_inline(value: str, limit: int = 600) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return "-"

    text = text.replace("\n", "\\n")
    if len(text) > limit:
        return f"{text[: limit - 15]}...(truncated)"
    return text
