from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from astrbot.api.event import MessageEventResult
except ImportError:
    class MessageEventResult:
        def __init__(self) -> None:
            self.message_text = ""

        def message(self, text: str) -> "MessageEventResult":
            self.message_text = text
            return self

try:
    from .command_context import CommandContext
    from .glog_command_constants import (
        ALL_PUSH_ACTIONS,
        ALL_SWITCH_VALUES,
        HELP_TEXT,
        MIN_POLL_INTERVAL_SECONDS,
        PushAction,
        SwitchValue,
    )
    from .glog_event_service import GlogEventSwitchService
    from ..services.message_recall_service import MessageRecallService
    from ..domain.models import PushGroupConfig
except ImportError:
    from commands.command_context import CommandContext
    from commands.glog_command_constants import (
        ALL_PUSH_ACTIONS,
        ALL_SWITCH_VALUES,
        HELP_TEXT,
        MIN_POLL_INTERVAL_SECONDS,
        PushAction,
        SwitchValue,
    )
    from commands.glog_event_service import GlogEventSwitchService
    from services.message_recall_service import MessageRecallService
    from domain.models import PushGroupConfig

if TYPE_CHECKING:
    try:
        from ..commands.group_context_service import GroupContextService
        from ..runtime.plugin_runtime_state import PluginRuntimeState
        from ..runtime.runtime_config_store import RuntimeConfigStore
    except ImportError:
        from commands.group_context_service import GroupContextService
        from runtime.plugin_runtime_state import PluginRuntimeState
        from runtime.runtime_config_store import RuntimeConfigStore


class GlogConfigService:
    def __init__(
        self,
        permissions: Any,
        runtime_state: "PluginRuntimeState",
        runtime_config_store: "RuntimeConfigStore",
        group_context_service: "GroupContextService",
        message_recall_service: MessageRecallService,
        event_switch_service: GlogEventSwitchService,
    ) -> None:
        self._permissions = permissions
        self._runtime_state = runtime_state
        self._runtime_config_store = runtime_config_store
        self._group_context_service = group_context_service
        self._message_recall_service = message_recall_service
        self._event_switch_service = event_switch_service

    def build_help_result(self) -> MessageEventResult:
        return self._message(HELP_TEXT)

    async def handle_status(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        config = self._runtime_state.config
        current_group_id = self._group_context_service.current_group_id(context)
        is_global_admin = self._group_context_service.is_global_admin(context)
        target_group_id = current_group_id

        if args:
            if not is_global_admin:
                return self._message("global admin permission required")
            target_group_id = args[0].strip()

        monitored = config.monitored_groups.get(target_group_id) if target_group_id else None
        push_group = config.push_groups.get(target_group_id) if target_group_id else None
        lines = [
            "Group Event Log status",
            f"plugin_enabled: {config.plugin_enabled}",
            f"debug_raw_notice: {config.debug_raw_notice}",
            f"avatar_poll_interval_seconds: {config.avatar_poll_interval_seconds}",
            f"member_profile_poll_interval_seconds: {config.member_profile_poll_interval_seconds}",
            f"monitored_group_count: {len(config.monitored_groups)}",
            f"push_group_count: {len(config.push_groups)}",
            f"last_updated: {config.last_updated or '-'}",
        ]

        if target_group_id:
            lines.extend(
                [
                    f"target_group_id: {target_group_id}",
                    f"target_group_monitored: {bool(monitored and monitored.enabled)}",
                    f"target_group_push_enabled: {bool(push_group and push_group.enabled)}",
                ]
            )
            if monitored:
                lines.append(
                    "target_group_push_groups: " + (", ".join(monitored.push_group_ids) or "-")
                )
                lines.append(
                    f"target_group_avatar_rollback_enabled: {monitored.avatar_rollback_enabled}"
                )
                lines.append(
                    "target_group_group_name_rollback_enabled: "
                    f"{monitored.group_name_rollback_enabled}"
                )
                lines.append(
                    "target_group_member_profile_polling_enabled: "
                    f"{monitored.member_profile_polling_enabled}"
                )
                lines.append(
                    f"target_group_recall_message_enabled: {monitored.recall_message_enabled}"
                )
                lines.extend(
                    self._event_switch_service.format_self_operation_switches(monitored)
                )
        elif current_group_id:
            lines.append(f"current_group_id: {current_group_id}")

        return self._message("\n".join(lines))

    async def handle_list(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        del args
        if not self._group_context_service.is_global_admin(context):
            return self._message("global admin permission required")

        config = self._runtime_state.config
        monitored_lines = [
            f"{group_id}: {'on' if group_config.enabled else 'off'} -> "
            f"{', '.join(group_config.push_group_ids) or '-'} "
            f"[avatar_rb={'on' if group_config.avatar_rollback_enabled else 'off'} "
            f"name_rb={'on' if group_config.group_name_rollback_enabled else 'off'} "
            f"member_poll={'on' if group_config.member_profile_polling_enabled else 'off'} "
            f"recall_msg={'on' if group_config.recall_message_enabled else 'off'} "
            "self_ops="
            f"{self._event_switch_service.format_self_operation_switch_summary(group_config)}]"
            for group_id, group_config in sorted(config.monitored_groups.items())
        ]
        push_lines = [
            f"{group_id}: {'on' if group_config.enabled else 'off'}"
            for group_id, group_config in sorted(config.push_groups.items())
        ]
        lines = ["monitored_groups:"]
        lines.extend(monitored_lines or ["-"])
        lines.append("push_groups:")
        lines.extend(push_lines or ["-"])
        return self._message("\n".join(lines))

    async def handle_plugin(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        if not self._group_context_service.is_global_admin(context):
            return self._message("global admin permission required")
        if len(args) != 1 or args[0].lower() not in ALL_SWITCH_VALUES:
            return self._message("usage: /glog plugin on|off")

        config = self._runtime_state.config
        config.plugin_enabled = args[0].lower() == SwitchValue.ON
        await self._runtime_config_store.save()
        return self._message(f"plugin_enabled set to {config.plugin_enabled}")

    async def handle_enable(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        target_group_id = (
            args[0].strip()
            if args
            else self._group_context_service.current_group_id(context)
        )
        if not target_group_id:
            return self._message(
                "usage: /glog enable [group_id]\nrun it in a group or pass group_id"
            )

        if not await self._group_context_service.can_manage_source_group(
            context,
            target_group_id,
        ):
            return self._message("no permission to enable this group")

        config = self._runtime_state.config
        source_config = config.monitored_groups.get(target_group_id)
        if not source_config:
            source_config = self._event_switch_service.new_source_group_config()
            config.monitored_groups[target_group_id] = source_config
        source_config.enabled = True
        await self._runtime_config_store.save()
        return self._message(
            f"source group enabled: {target_group_id}\n"
            "the group will now listen silently for supported notice events"
        )

    async def handle_disable(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        target_group_id = (
            args[0].strip()
            if args
            else self._group_context_service.current_group_id(context)
        )
        if not target_group_id:
            return self._message(
                "usage: /glog disable [group_id]\nrun it in a group or pass group_id"
            )

        if not await self._group_context_service.can_manage_source_group(
            context,
            target_group_id,
        ):
            return self._message("no permission to disable this group")

        config = self._runtime_state.config
        source_config = config.monitored_groups.get(target_group_id)
        if not source_config:
            source_config = self._event_switch_service.new_source_group_config(enabled=False)
            config.monitored_groups[target_group_id] = source_config
        else:
            source_config.enabled = False
        await self._runtime_config_store.save()
        return self._message(
            f"source group disabled: {target_group_id}\n"
            "the group will no longer be monitored"
        )

    async def handle_push(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        if not self._group_context_service.is_global_admin(context):
            return self._message("global admin permission required")
        if len(args) < 2 or args[0].lower() not in ALL_PUSH_ACTIONS:
            return self._message(
                "usage: /glog push enable <group_id>\n"
                "usage: /glog push disable <group_id>"
            )

        action = args[0].lower()
        group_id = args[1].strip()
        if not group_id:
            return self._message("push group_id is required")

        config = self._runtime_state.config
        push_group = config.push_groups.get(group_id)
        if not push_group:
            push_group = PushGroupConfig()
            config.push_groups[group_id] = push_group

        push_group.enabled = action == PushAction.ENABLE
        await self._runtime_config_store.save()
        return self._message(
            f"push group {group_id} set to {'enabled' if push_group.enabled else 'disabled'}"
        )

    async def handle_bind(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        source_group_id, push_group_id, error = self._group_context_service.resolve_bind_args(
            context,
            args,
        )
        if error:
            return self._message(error)

        if not await self._group_context_service.can_manage_source_group(
            context,
            source_group_id,
        ):
            return self._message("no permission to manage this source group")

        config = self._runtime_state.config
        source_config = config.monitored_groups.get(source_group_id)
        if not source_config or not source_config.enabled:
            return self._message(f"source group {source_group_id} is not enabled yet")

        push_group = config.push_groups.get(push_group_id)
        if not push_group or not push_group.enabled:
            return self._message(f"push group {push_group_id} is not enabled yet")

        if push_group_id not in source_config.push_group_ids:
            source_config.push_group_ids.append(push_group_id)
            await self._runtime_config_store.save()

        return self._message(f"bound source {source_group_id} -> push {push_group_id}")

    async def handle_unbind(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        source_group_id, push_group_id, error = self._group_context_service.resolve_bind_args(
            context,
            args,
        )
        if error:
            return self._message(error)

        if not await self._group_context_service.can_manage_source_group(
            context,
            source_group_id,
        ):
            return self._message("no permission to manage this source group")

        config = self._runtime_state.config
        source_config = config.monitored_groups.get(source_group_id)
        if not source_config:
            return self._message(f"source group {source_group_id} is not configured")

        if push_group_id in source_config.push_group_ids:
            source_config.push_group_ids.remove(push_group_id)
            await self._runtime_config_store.save()

        return self._message(f"unbound source {source_group_id} -> push {push_group_id}")

    async def handle_recall(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        if len(args) < 1:
            return self._message("usage: /glog recall on|off [group_id]")

        switch_value = args[0].lower()
        if switch_value not in ALL_SWITCH_VALUES:
            return self._message("recall switch must be on or off")

        target_group_id = (
            args[1].strip()
            if len(args) >= 2
            else self._group_context_service.current_group_id(context)
        )
        if not target_group_id:
            return self._message("run this command in a group or pass group_id explicitly")

        if not await self._group_context_service.can_manage_source_group(
            context,
            target_group_id,
        ):
            return self._message("no permission to manage this source group")

        config = self._runtime_state.config
        source_config = config.monitored_groups.get(target_group_id)
        if not source_config or not source_config.enabled:
            return self._message(f"source group {target_group_id} is not enabled yet")

        enabled = switch_value == SwitchValue.ON
        source_config.recall_message_enabled = enabled
        if not enabled:
            self._message_recall_service.clear_group_cache(target_group_id)
        await self._runtime_config_store.save()
        return self._message(
            f"recalled message content for {target_group_id} set to {switch_value}"
        )

    async def handle_avatar_interval(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        if not self._group_context_service.is_global_admin(context):
            return self._message("global admin permission required")
        if len(args) != 1:
            return self._message("usage: /glog avatar interval <seconds>")

        seconds, error = self._parse_interval_seconds(args[0])
        if error:
            return self._message(error)

        config = self._runtime_state.config
        config.avatar_poll_interval_seconds = seconds
        await self._runtime_config_store.save()
        return self._message(
            f"avatar hash poll interval set to {config.avatar_poll_interval_seconds} seconds"
        )

    async def handle_member_interval(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        if not self._group_context_service.is_global_admin(context):
            return self._message("global admin permission required")
        if len(args) != 1:
            return self._message("usage: /glog member interval <seconds>")

        seconds, error = self._parse_interval_seconds(args[0])
        if error:
            return self._message(error)

        config = self._runtime_state.config
        config.member_profile_poll_interval_seconds = seconds
        await self._runtime_config_store.save()
        return self._message(
            "member profile poll interval set to "
            f"{config.member_profile_poll_interval_seconds} seconds"
        )

    async def handle_member_poll(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        if len(args) < 1:
            return self._message("usage: /glog member poll on|off [group_id]")

        switch_value = args[0].lower()
        if switch_value not in ALL_SWITCH_VALUES:
            return self._message("poll switch must be on or off")

        target_group_id = (
            args[1].strip()
            if len(args) >= 2
            else self._group_context_service.current_group_id(context)
        )
        if not target_group_id:
            return self._message("run this command in a group or pass group_id explicitly")

        if not await self._group_context_service.can_manage_source_group(
            context,
            target_group_id,
        ):
            return self._message("no permission to manage this source group")

        config = self._runtime_state.config
        source_config = config.monitored_groups.get(target_group_id)
        if not source_config or not source_config.enabled:
            return self._message(f"source group {target_group_id} is not enabled yet")

        source_config.member_profile_polling_enabled = switch_value == SwitchValue.ON
        await self._runtime_config_store.save()
        return self._message(
            f"member profile polling for {target_group_id} set to {switch_value}"
        )

    def _parse_interval_seconds(self, raw_value: str) -> tuple[int, str]:
        try:
            seconds = int(raw_value)
        except ValueError:
            return 0, "interval must be an integer number of seconds"

        if seconds < MIN_POLL_INTERVAL_SECONDS:
            return (
                0,
                f"interval must be at least {MIN_POLL_INTERVAL_SECONDS} seconds",
            )
        return seconds, ""

    def _message(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)
