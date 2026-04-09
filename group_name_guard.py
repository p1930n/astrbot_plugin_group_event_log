from __future__ import annotations

from datetime import datetime
from typing import Any


def build_group_name_baseline_state(group_id: str, baseline_name: str) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "group_id": group_id,
        "baseline_name": baseline_name,
        "last_observed_name": baseline_name,
        "baseline_updated_at": now,
        "last_checked_at": now,
        "last_changed_at": "",
        "last_rollback_at": "",
        "last_rollback_result": "",
        "change_count": 0,
        "last_error": "",
    }


def summarize_group_name_guard(state: dict[str, Any]) -> list[str]:
    return [
        "group name guard",
        f"group_id: {state.get('group_id', '-')}",
        f"baseline_name: {state.get('baseline_name', '-')}",
        f"last_observed_name: {state.get('last_observed_name', '-')}",
        f"baseline_updated_at: {state.get('baseline_updated_at', '-')}",
        f"last_checked_at: {state.get('last_checked_at', '-')}",
        f"last_changed_at: {state.get('last_changed_at', '-')}",
        f"last_rollback_at: {state.get('last_rollback_at', '-')}",
        f"last_rollback_result: {state.get('last_rollback_result', '-')}",
        f"change_count: {state.get('change_count', 0)}",
        f"last_error: {state.get('last_error', '-')}",
    ]
