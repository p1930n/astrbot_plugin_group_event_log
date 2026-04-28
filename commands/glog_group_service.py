from __future__ import annotations

from typing import TYPE_CHECKING

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
        ALL_ROLLBACK_TARGETS,
        ALL_SWITCH_VALUES,
        RollbackTarget,
        SwitchValue,
    )
    from ..domain.models import SourceGroupConfig
except ImportError:
    from commands.command_context import CommandContext
    from commands.glog_command_constants import (
        ALL_ROLLBACK_TARGETS,
        ALL_SWITCH_VALUES,
        RollbackTarget,
        SwitchValue,
    )
    from domain.models import SourceGroupConfig

if TYPE_CHECKING:
    try:
        from ..commands.group_context_service import GroupContextService
        from ..runtime.group_runtime_service import GroupRuntimeService
        from ..runtime.plugin_runtime_state import PluginRuntimeState
    except ImportError:
        from commands.group_context_service import GroupContextService
        from runtime.group_runtime_service import GroupRuntimeService
        from runtime.plugin_runtime_state import PluginRuntimeState


class GlogGroupService:
    def __init__(
        self,
        runtime_state: "PluginRuntimeState",
        group_context_service: "GroupContextService",
        group_runtime_service: "GroupRuntimeService",
    ) -> None:
        self._runtime_state = runtime_state
        self._group_context_service = group_context_service
        self._group_runtime_service = group_runtime_service

    async def handle_avatar_probe(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(context, args)
        if error:
            return self._message(error)
        return await self._group_runtime_service.handle_avatar_probe(
            context.source_event,
            group_id,
        )

    async def handle_avatar_check(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(context, args)
        if error:
            return self._message(error)
        return await self._group_runtime_service.handle_avatar_check(group_id)

    async def handle_avatar_status(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(context, args)
        if error:
            return self._message(error)
        return await self._group_runtime_service.handle_avatar_status(group_id)

    async def handle_member_check(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(context, args)
        if error:
            return self._message(error)
        return await self._group_runtime_service.handle_member_check(group_id)

    async def handle_member_status(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(context, args)
        if error:
            return self._message(error)
        return await self._group_runtime_service.handle_member_status(group_id)

    async def handle_rollback(
        self, context: CommandContext, args: list[str]
    ) -> MessageEventResult:
        if len(args) < 2 or args[0].lower() not in ALL_ROLLBACK_TARGETS:
            return self._message(
                "usage: /glog rollback avatar on|off [group_id]\n"
                "usage: /glog rollback group_name on|off [group_id]"
            )

        rollback_target = args[0].lower()
        switch_value = args[1].lower()
        if switch_value not in ALL_SWITCH_VALUES:
            return self._message("rollback switch must be on or off")

        target_group_id = (
            args[2].strip()
            if len(args) >= 3
            else self._group_context_service.current_group_id(context)
        )
        if not target_group_id:
            return self._message("run this command in a group or pass group_id explicitly")

        if not await self._group_context_service.can_manage_source_group(
            context,
            target_group_id,
        ):
            return self._message("no permission to manage this source group")

        source_config = self._runtime_state.config.monitored_groups.get(target_group_id)
        if not source_config or not source_config.enabled:
            return self._message(f"source group {target_group_id} is not enabled yet")

        enabled = switch_value == SwitchValue.ON
        if rollback_target == RollbackTarget.AVATAR:
            return await self._group_runtime_service.set_avatar_rollback(
                target_group_id,
                source_config,
                enabled,
            )
        return await self._group_runtime_service.set_group_name_rollback(
            target_group_id,
            source_config,
            enabled,
        )

    async def _resolve_query_group_id(
        self, context: CommandContext, args: list[str]
    ) -> tuple[str, str]:
        group_id = (
            args[0].strip()
            if args
            else self._group_context_service.current_group_id(context)
        )
        if not group_id:
            return "", "run this command in a group or pass group_id explicitly"
        if not await self._group_context_service.can_query_group_metadata(
            context,
            group_id,
        ):
            return "", "no permission to inspect this group"
        return group_id, ""

    def _message(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)
