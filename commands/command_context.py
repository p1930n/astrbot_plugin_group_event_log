from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommandContext:
    message_text: str
    group_id: str
    sender_id: str
    platform: str
    source_event: Any | None = None

    @classmethod
    def from_event(cls, event: Any) -> "CommandContext":
        return cls(
            message_text=_call_string(event, "get_message_str"),
            group_id=_call_string(event, "get_group_id"),
            sender_id=_call_string(event, "get_sender_id"),
            platform=_call_string(event, "get_platform_name"),
            source_event=event,
        )


def _call_string(target: Any, method_name: str) -> str:
    method = getattr(target, method_name, None)
    if not callable(method):
        return ""
    try:
        return str(method() or "").strip()
    except Exception:
        return ""
