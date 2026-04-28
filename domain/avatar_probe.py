from __future__ import annotations

from datetime import datetime
from typing import Any


AVATAR_KEYWORDS = (
    "avatar",
    "portrait",
    "head",
    "icon",
    "face",
    "logo",
)


def build_avatar_probe_record(
    group_id: str,
    group_info: dict[str, Any],
    group_info_ex: dict[str, Any],
) -> dict[str, Any]:
    collected_at = datetime.now().isoformat(timespec="seconds")
    return {
        "group_id": group_id,
        "collected_at": collected_at,
        "get_group_info": _normalize_result(group_info),
        "get_group_info_ex": _normalize_result(group_info_ex),
    }


def summarize_avatar_probe(record: dict[str, Any]) -> list[str]:
    lines = [
        "avatar probe summary",
        f"group_id: {record.get('group_id', '-')}",
        f"collected_at: {record.get('collected_at', '-')}",
    ]

    for action in ("get_group_info", "get_group_info_ex"):
        action_data = record.get(action, {})
        lines.append(f"{action}: {'ok' if action_data.get('ok') else 'failed'}")
        if action_data.get("error"):
            lines.append(f"{action}_error: {action_data['error']}")
            continue

        top_keys = action_data.get("top_level_keys", [])
        lines.append(f"{action}_top_level_keys: {', '.join(top_keys) or '-'}")

        candidates = action_data.get("candidate_fields", [])
        if candidates:
            lines.append(
                f"{action}_candidate_fields: "
                + "; ".join(_render_candidate(candidate) for candidate in candidates[:8])
            )
        else:
            lines.append(f"{action}_candidate_fields: -")

    return lines


def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    if not raw.get("ok"):
        return {
            "ok": False,
            "error": str(raw.get("error", "unknown error")),
        }

    data = raw.get("data")
    candidate_fields = _collect_candidate_fields(data)
    top_level_keys = sorted(data.keys()) if isinstance(data, dict) else []
    return {
        "ok": True,
        "top_level_keys": top_level_keys,
        "candidate_fields": candidate_fields,
        "raw": data,
    }


def _collect_candidate_fields(data: Any) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    _walk(data, "", results, depth=0)
    return results


def _walk(data: Any, path: str, results: list[dict[str, str]], depth: int) -> None:
    if depth > 6:
        return

    if isinstance(data, dict):
        for key, value in data.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if _looks_like_avatar_key(key_text):
                results.append(
                    {
                        "path": child_path,
                        "value_preview": _preview_value(value),
                    }
                )
            _walk(value, child_path, results, depth + 1)
        return

    if isinstance(data, list):
        for index, item in enumerate(data[:20]):
            child_path = f"{path}[{index}]"
            _walk(item, child_path, results, depth + 1)


def _looks_like_avatar_key(key: str) -> bool:
    lowered = key.lower()
    return any(keyword in lowered for keyword in AVATAR_KEYWORDS)


def _preview_value(value: Any) -> str:
    text = str(value)
    return text if len(text) <= 120 else text[:117] + "..."


def _render_candidate(candidate: dict[str, str]) -> str:
    return f"{candidate.get('path', '?')}={candidate.get('value_preview', '')}"
