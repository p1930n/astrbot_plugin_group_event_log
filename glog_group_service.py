from __future__ import annotations

from typing import Any, Awaitable, Callable

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
        ALL_ROLLBACK_TARGETS,
        ALL_SWITCH_VALUES,
        RollbackTarget,
        SwitchValue,
    )
    from .models import PluginConfig, SourceGroupConfig
except ImportError:
    from glog_command_constants import (
        ALL_ROLLBACK_TARGETS,
        ALL_SWITCH_VALUES,
        RollbackTarget,
        SwitchValue,
    )
    from models import PluginConfig, SourceGroupConfig


class GlogGroupService:
    def __init__(
        self,
        get_config: Callable[[], PluginConfig],
        current_group_id: Callable[[AstrMessageEvent], str],
        can_manage_source_group: Callable[[AstrMessageEvent, str], Awaitable[bool]],
        can_query_group_metadata: Callable[[AstrMessageEvent, str], Awaitable[bool]],
        run_avatar_probe: Callable[[AstrMessageEvent, str], Awaitable[MessageEventResult]],
        run_avatar_check: Callable[[str], Awaitable[MessageEventResult]],
        run_avatar_status: Callable[[str], Awaitable[MessageEventResult]],
        run_member_check: Callable[[str], Awaitable[MessageEventResult]],
        run_member_status: Callable[[str], Awaitable[MessageEventResult]],
        set_avatar_rollback: Callable[
            [str, SourceGroupConfig, bool], Awaitable[MessageEventResult]
        ],
        set_group_name_rollback: Callable[
            [str, SourceGroupConfig, bool], Awaitable[MessageEventResult]
        ],
    ) -> None:
        self._get_config = get_config
        self._current_group_id = current_group_id
        self._can_manage_source_group = can_manage_source_group
        self._can_query_group_metadata = can_query_group_metadata
        self._run_avatar_probe = run_avatar_probe
        self._run_avatar_check = run_avatar_check
        self._run_avatar_status = run_avatar_status
        self._run_member_check = run_member_check
        self._run_member_status = run_member_status
        self._set_avatar_rollback = set_avatar_rollback
        self._set_group_name_rollback = set_group_name_rollback

    async def handle_avatar_probe(
        self, event: AstrMessageEvent, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(event, args)
        if error:
            return self._message(error)
        return await self._run_avatar_probe(event, group_id)

    async def handle_avatar_check(
        self, event: AstrMessageEvent, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(event, args)
        if error:
            return self._message(error)
        return await self._run_avatar_check(group_id)

    async def handle_avatar_status(
        self, event: AstrMessageEvent, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(event, args)
        if error:
            return self._message(error)
        return await self._run_avatar_status(group_id)

    async def handle_member_check(
        self, event: AstrMessageEvent, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(event, args)
        if error:
            return self._message(error)
        return await self._run_member_check(group_id)

    async def handle_member_status(
        self, event: AstrMessageEvent, args: list[str]
    ) -> MessageEventResult:
        group_id, error = await self._resolve_query_group_id(event, args)
        if error:
            return self._message(error)
        return await self._run_member_status(group_id)

    async def handle_rollback(
        self, event: AstrMessageEvent, args: list[str]
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

        target_group_id = args[2].strip() if len(args) >= 3 else self._current_group_id(event)
        if not target_group_id:
            return self._message("run this command in a group or pass group_id explicitly")

        if not await self._can_manage_source_group(event, target_group_id):
            return self._message("no permission to manage this source group")

        source_config = self._get_config().monitored_groups.get(target_group_id)
        if not source_config or not source_config.enabled:
            return self._message(f"source group {target_group_id} is not enabled yet")

        enabled = switch_value == SwitchValue.ON
        if rollback_target == RollbackTarget.AVATAR:
            return await self._set_avatar_rollback(target_group_id, source_config, enabled)
        return await self._set_group_name_rollback(target_group_id, source_config, enabled)

    async def _resolve_query_group_id(
        self, event: AstrMessageEvent, args: list[str]
    ) -> tuple[str, str]:
        group_id = args[0].strip() if args else self._current_group_id(event)
        if not group_id:
            return "", "run this command in a group or pass group_id explicitly"
        if not await self._can_query_group_metadata(event, group_id):
            return "", "no permission to inspect this group"
        return group_id, ""

    def _message(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)
