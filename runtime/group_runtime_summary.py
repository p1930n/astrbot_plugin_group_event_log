from __future__ import annotations

from typing import Any

try:
    from ..domain.avatar_hash import (
        AvatarHashTransition,
        summarize_avatar_hash_state,
        summarize_avatar_hash_transition,
    )
    from ..domain.avatar_probe import summarize_avatar_probe
    from ..domain.group_name_guard import summarize_group_name_guard
    from ..domain.member_profile import MemberProfileChange, summarize_member_profile_state
except ImportError:
    from domain.avatar_hash import (
        AvatarHashTransition,
        summarize_avatar_hash_state,
        summarize_avatar_hash_transition,
    )
    from domain.avatar_probe import summarize_avatar_probe
    from domain.group_name_guard import summarize_group_name_guard
    from domain.member_profile import MemberProfileChange, summarize_member_profile_state


AVATAR_HASH_STATE_RECORD_PREFIX = "avatar_hash_states"
GROUP_NAME_STATE_RECORD_PREFIX = "group_name_guard_states"
MEMBER_PROFILE_STATE_RECORD_PREFIX = "member_profile_states"


def build_avatar_probe_summary(record: dict[str, Any], saved_path: str) -> list[str]:
    lines = summarize_avatar_probe(record)
    lines.append(f"saved_to: {saved_path}")
    return lines


def build_avatar_check_summary(
    transition: AvatarHashTransition,
    sent_push_groups: list[str],
    database_path: str,
) -> list[str]:
    lines = summarize_avatar_hash_transition(transition, sent_push_groups)
    lines.extend(
        _state_path_lines(
            "state",
            database_path,
            _avatar_hash_record_key(transition.group_id),
        )
    )
    return lines


def build_avatar_status_summary(
    group_id: str,
    state: dict[str, Any],
    probe_record: dict[str, Any],
    group_name_state: dict[str, Any],
    database_path: str,
    probe_snapshot_path: str,
) -> list[str]:
    if not state and not probe_record and not group_name_state:
        return [f"no avatar or group-name data found for group {group_id}"]

    lines: list[str] = []
    if state:
        lines.extend(summarize_avatar_hash_state(state))
        lines.extend(
            _state_path_lines(
                "hash_state",
                database_path,
                _avatar_hash_record_key(group_id),
            )
        )
    if group_name_state:
        _append_section_separator(lines)
        lines.extend(summarize_group_name_guard(group_name_state))
        lines.extend(
            _state_path_lines(
                "group_name_state",
                database_path,
                _group_name_record_key(group_id),
            )
        )
    if probe_record:
        _append_section_separator(lines)
        lines.extend(summarize_avatar_probe(probe_record))
        lines.append(f"probe_snapshot_path: {probe_snapshot_path}")
    return lines


def build_member_check_summary(
    group_id: str,
    state: dict[str, Any],
    changes: list[MemberProfileChange],
    push_group_ids: list[str],
    database_path: str,
) -> list[str]:
    lines = summarize_member_profile_state(state)
    lines.append(f"detected_changes: {len(changes)}")
    lines.append("logs_sent_to: " + (", ".join(push_group_ids) if push_group_ids else "-"))
    lines.extend(
        _state_path_lines(
            "member_profile_state",
            database_path,
            _member_profile_record_key(group_id),
        )
    )
    return lines


def build_member_status_summary(
    group_id: str,
    state: dict[str, Any],
    database_path: str,
) -> list[str]:
    if not state:
        return [f"no member profile snapshot found for group {group_id}"]

    lines = summarize_member_profile_state(state)
    lines.extend(
        _state_path_lines(
            "member_profile_state",
            database_path,
            _member_profile_record_key(group_id),
        )
    )
    return lines


def _state_path_lines(prefix: str, database_path: str, record_key: str) -> list[str]:
    return [
        f"{prefix}_db_path: {database_path}",
        f"{prefix}_record_key: {record_key}",
    ]


def _avatar_hash_record_key(group_id: str) -> str:
    return f"{AVATAR_HASH_STATE_RECORD_PREFIX}/{group_id}"


def _group_name_record_key(group_id: str) -> str:
    return f"{GROUP_NAME_STATE_RECORD_PREFIX}/{group_id}"


def _member_profile_record_key(group_id: str) -> str:
    return f"{MEMBER_PROFILE_STATE_RECORD_PREFIX}/{group_id}"


def _append_section_separator(lines: list[str]) -> None:
    if lines:
        lines.append("----")
