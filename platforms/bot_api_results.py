from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BotApiCallResult:
    ok: bool
    action: str
    data: object = None
    error: str = ""

    def as_legacy_dict(self) -> dict[str, object]:
        if self.ok:
            return {
                "ok": True,
                "data": self.data,
            }
        return {
            "ok": False,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GroupInfoResult:
    ok: bool
    group_id: str
    payload: dict[str, Any] | None = None
    error: str = ""

    @property
    def group_name(self) -> str:
        if not self.payload:
            return ""
        return str(self.payload.get("group_name", "")).strip()


@dataclass(frozen=True, slots=True)
class GroupMemberListResult:
    ok: bool
    group_id: str
    payload: object = None
    error: str = ""
    used_no_cache: bool = False
    fallback_used: bool = False

    def as_legacy_dict(self) -> dict[str, object]:
        if self.ok:
            return {
                "ok": True,
                "data": self.payload,
            }
        return {
            "ok": False,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GroupNameSetResult:
    ok: bool
    group_id: str
    group_name: str
    error: str = ""

    def as_legacy_tuple(self) -> tuple[bool, str]:
        return self.ok, self.error


@dataclass(frozen=True, slots=True)
class GroupPortraitSetResult:
    ok: bool
    group_id: str
    attempted_inputs: tuple[str, ...]
    applied_input: str = ""
    error: str = ""

