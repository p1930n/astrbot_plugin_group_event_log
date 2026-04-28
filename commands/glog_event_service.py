from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from astrbot.api.event import AstrMessageEvent, MessageEventResult
except ImportError:
    AstrMessageEvent = Any  # type: ignore[misc,assignment]

    class MessageEventResult:
        def __init__(self) -> None:
            self.message_text = ""

        def message(self, text: str) -> "MessageEventResult":
            self.message_text = text
            return self

try:
    from .glog_command_constants import (
        ALL_SWITCH_VALUES,
        EVENT_SWITCH_ALIASES,
        SELF_OPERATION_EVENT_SWITCHES,
        SwitchValue,
    )
    from ..domain.models import SourceGroupConfig
except ImportError:
    from commands.glog_command_constants import (
        ALL_SWITCH_VALUES,
        EVENT_SWITCH_ALIASES,
        SELF_OPERATION_EVENT_SWITCHES,
        SwitchValue,
    )
    from domain.models import SourceGroupConfig

if TYPE_CHECKING:
    try:
        from ..commands.group_context_service import GroupContextService
        from ..runtime.plugin_runtime_state import PluginRuntimeState
        from ..runtime.runtime_config_store import RuntimeConfigStore
    except ImportError:
        from commands.group_context_service import GroupContextService
        from runtime.plugin_runtime_state import PluginRuntimeState
        from runtime.runtime_config_store import RuntimeConfigStore


class GlogEventSwitchService:
    def __init__(
        self,
        runtime_state: "PluginRuntimeState",
        runtime_config_store: "RuntimeConfigStore",
        group_context_service: "GroupContextService",
        default_event_switches: dict[str, bool] | None = None,
    ) -> None:
        self._runtime_state = runtime_state
        self._runtime_config_store = runtime_config_store
        self._group_context_service = group_context_service
        self._default_event_switches = default_event_switches or {}

    async def handle_event(
        self, event: AstrMessageEvent, args: list[str]
    ) -> MessageEventResult:
        if not args:
            return self._message(
                "usage: /glog event <kick|ban|recall-own|recall-other> on|off [group_id]\n"
                "usage: /glog event status [group_id]"
            )

        if args[0].lower() == "status":
            return await self._handle_status(event, args[1:])

        if len(args) < 2:
            return self._message(
                "usage: /glog event <kick|ban|recall-own|recall-other> on|off [group_id]"
            )

        event_key = EVENT_SWITCH_ALIASES.get(args[0].lower())
        if not event_key:
            return self._message("event must be kick, ban, recall-own, or recall-other")

        switch_value = args[1].lower()
        if switch_value not in ALL_SWITCH_VALUES:
            return self._message("event switch must be on or off")

        target_group_id = self._target_group_id(event, args[2:])
        if not target_group_id:
            return self._message("run this command in a group or pass group_id explicitly")

        source_config, error = await self._load_manageable_source_config(
            event,
            target_group_id,
        )
        if error:
            return self._message(error)
        if not source_config:
            return self._message(f"source group {target_group_id} is not enabled yet")

        source_config.event_switches[event_key] = switch_value == SwitchValue.ON
        await self._runtime_config_store.save()
        return self._message(
            f"event {event_key} for {target_group_id} set to {switch_value}"
        )

    async def _handle_status(
        self, event: AstrMessageEvent, args: list[str]
    ) -> MessageEventResult:
        target_group_id = self._target_group_id(event, args)
        if not target_group_id:
            return self._message("run this command in a group or pass group_id explicitly")

        source_config, error = await self._load_manageable_source_config(
            event,
            target_group_id,
        )
        if error:
            return self._message(error)
        if not source_config:
            return self._message(f"source group {target_group_id} is not enabled yet")

        return self._message(
            "\n".join(
                [f"bot self-operation switches for {target_group_id}"]
                + self.format_self_operation_switches(source_config)
            )
        )

    async def _load_manageable_source_config(
        self,
        event: AstrMessageEvent,
        target_group_id: str,
    ) -> tuple[SourceGroupConfig | None, str]:
        if not await self._group_context_service.can_manage_source_group(
            event,
            target_group_id,
        ):
            return None, "no permission to manage this source group"

        source_config = self._runtime_state.config.monitored_groups.get(target_group_id)
        if not source_config or not source_config.enabled:
            return None, ""
        return source_config, ""

    def new_source_group_config(self, enabled: bool = True) -> SourceGroupConfig:
        source_config = SourceGroupConfig(enabled=enabled)
        for event_key, enabled_value in self._default_event_switches.items():
            source_config.event_switches[event_key] = enabled_value
        return source_config

    def format_self_operation_switches(
        self,
        source_config: SourceGroupConfig,
    ) -> list[str]:
        return [
            f"{event_key}: {'on' if source_config.event_switches.get(event_key, True) else 'off'}"
            for event_key in sorted(SELF_OPERATION_EVENT_SWITCHES)
        ]

    def format_self_operation_switch_summary(
        self,
        source_config: SourceGroupConfig,
    ) -> str:
        return ",".join(
            f"{event_key}:{'on' if source_config.event_switches.get(event_key, True) else 'off'}"
            for event_key in sorted(SELF_OPERATION_EVENT_SWITCHES)
        )

    def _target_group_id(self, event: AstrMessageEvent, args: list[str]) -> str:
        return (
            args[0].strip()
            if args
            else self._group_context_service.current_group_id(event)
        )

    def _message(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)
