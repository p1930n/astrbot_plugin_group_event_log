from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_EVENT_SWITCHES = {
    "group_increase": True,
    "group_decrease": True,
    "group_ban": True,
    "group_card": True,
    "group_admin": True,
    "group_recall": True,
    "bot_kick_member": True,
    "bot_ban_member": True,
    "bot_recall_own_message": True,
    "bot_recall_other_message": True,
    "notify.group_name": True,
    "notify.title": True,
    "avatar_hash": True,
}


def _normalize_id_list(values: list[Any] | None) -> list[str]:
    if not values:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _build_event_switches(values: dict[str, Any] | None) -> dict[str, bool]:
    result = DEFAULT_EVENT_SWITCHES.copy()
    if not values:
        return result

    for key, value in values.items():
        result[str(key)] = bool(value)
    return result


@dataclass(slots=True)
class PushGroupConfig:
    enabled: bool = True
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PushGroupConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            label=str(data.get("label", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "label": self.label,
        }


@dataclass(slots=True)
class SourceGroupConfig:
    enabled: bool = True
    push_group_ids: list[str] = field(default_factory=list)
    avatar_rollback_enabled: bool = False
    group_name_rollback_enabled: bool = False
    member_profile_polling_enabled: bool = False
    recall_message_enabled: bool = True
    event_switches: dict[str, bool] = field(
        default_factory=lambda: DEFAULT_EVENT_SWITCHES.copy()
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceGroupConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            push_group_ids=_normalize_id_list(data.get("push_group_ids")),
            avatar_rollback_enabled=bool(data.get("avatar_rollback_enabled", False)),
            group_name_rollback_enabled=bool(
                data.get("group_name_rollback_enabled", False)
            ),
            member_profile_polling_enabled=bool(
                data.get("member_profile_polling_enabled", False)
            ),
            recall_message_enabled=bool(data.get("recall_message_enabled", True)),
            event_switches=_build_event_switches(data.get("event_switches")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "push_group_ids": list(self.push_group_ids),
            "avatar_rollback_enabled": self.avatar_rollback_enabled,
            "group_name_rollback_enabled": self.group_name_rollback_enabled,
            "member_profile_polling_enabled": self.member_profile_polling_enabled,
            "recall_message_enabled": self.recall_message_enabled,
            "event_switches": dict(self.event_switches),
        }


@dataclass(slots=True)
class PluginConfig:
    plugin_enabled: bool = True
    debug_raw_notice: bool = False
    avatar_poll_interval_seconds: int = 300
    member_profile_poll_interval_seconds: int = 300
    monitored_groups: dict[str, SourceGroupConfig] = field(default_factory=dict)
    push_groups: dict[str, PushGroupConfig] = field(default_factory=dict)
    last_updated: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PluginConfig":
        data = data or {}
        monitored_raw = data.get("monitored_groups", {})
        push_raw = data.get("push_groups", {})

        monitored_groups = {
            str(group_id): SourceGroupConfig.from_dict(group_data)
            for group_id, group_data in monitored_raw.items()
        }
        push_groups = {
            str(group_id): PushGroupConfig.from_dict(group_data)
            for group_id, group_data in push_raw.items()
        }

        return cls(
            plugin_enabled=bool(data.get("plugin_enabled", True)),
            debug_raw_notice=bool(data.get("debug_raw_notice", False)),
            avatar_poll_interval_seconds=max(
                30, int(data.get("avatar_poll_interval_seconds", 300) or 300)
            ),
            member_profile_poll_interval_seconds=max(
                30, int(data.get("member_profile_poll_interval_seconds", 300) or 300)
            ),
            monitored_groups=monitored_groups,
            push_groups=push_groups,
            last_updated=str(data.get("last_updated", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_enabled": self.plugin_enabled,
            "debug_raw_notice": self.debug_raw_notice,
            "avatar_poll_interval_seconds": self.avatar_poll_interval_seconds,
            "member_profile_poll_interval_seconds": self.member_profile_poll_interval_seconds,
            "monitored_groups": {
                group_id: group_config.to_dict()
                for group_id, group_config in self.monitored_groups.items()
            },
            "push_groups": {
                group_id: push_group.to_dict()
                for group_id, push_group in self.push_groups.items()
            },
            "last_updated": self.last_updated,
        }
