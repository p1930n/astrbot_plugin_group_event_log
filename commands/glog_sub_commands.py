from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

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
        ALL_AVATAR_ACTIONS,
        ALL_MEMBER_ACTIONS,
        AvatarAction,
        MemberAction,
    )
    from .glog_config_service import GlogConfigService
    from .glog_event_service import GlogEventSwitchService
    from .glog_group_service import GlogGroupService
except ImportError:
    from commands.glog_command_constants import (
        ALL_AVATAR_ACTIONS,
        ALL_MEMBER_ACTIONS,
        AvatarAction,
        MemberAction,
    )
    from commands.glog_config_service import GlogConfigService
    from commands.glog_event_service import GlogEventSwitchService
    from commands.glog_group_service import GlogGroupService


class SubCommandHandler(Protocol):
    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        ...


class HelpCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        del event
        del args
        return self._config_service.build_help_result()


class StatusCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_status(event, args)


class ListCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_list(event, args)


class PluginCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_plugin(event, args)


class EnableCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_enable(event, args)


class DisableCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_disable(event, args)


class PushCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_push(event, args)


class BindCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_bind(event, args)


class UnbindCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_unbind(event, args)


class RecallCommandHandler:
    def __init__(self, config_service: GlogConfigService) -> None:
        self._config_service = config_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._config_service.handle_recall(event, args)


class EventCommandHandler:
    def __init__(self, event_switch_service: GlogEventSwitchService) -> None:
        self._event_switch_service = event_switch_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._event_switch_service.handle_event(event, args)


class RollbackCommandHandler:
    def __init__(self, group_service: GlogGroupService) -> None:
        self._group_service = group_service

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        return await self._group_service.handle_rollback(event, args)


class AvatarCommandHandler:
    def __init__(
        self,
        config_service: GlogConfigService,
        group_service: GlogGroupService,
    ) -> None:
        self._action_registry: dict[
            str,
            Callable[[AstrMessageEvent, list[str]], Awaitable[MessageEventResult]],
        ] = {
            AvatarAction.PROBE: group_service.handle_avatar_probe,
            AvatarAction.CHECK: group_service.handle_avatar_check,
            AvatarAction.STATUS: group_service.handle_avatar_status,
            AvatarAction.INTERVAL: config_service.handle_avatar_interval,
        }

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        if not args or args[0].lower() not in ALL_AVATAR_ACTIONS:
            return self._message(
                "usage: /glog avatar probe [group_id]\n"
                "usage: /glog avatar check [group_id]\n"
                "usage: /glog avatar interval <seconds>\n"
                "usage: /glog avatar status [group_id]"
            )

        action = args[0].lower()
        return await self._action_registry[action](event, args[1:])

    def _message(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)


class MemberCommandHandler:
    def __init__(
        self,
        config_service: GlogConfigService,
        group_service: GlogGroupService,
    ) -> None:
        self._action_registry: dict[
            str,
            Callable[[AstrMessageEvent, list[str]], Awaitable[MessageEventResult]],
        ] = {
            MemberAction.CHECK: group_service.handle_member_check,
            MemberAction.STATUS: group_service.handle_member_status,
            MemberAction.POLL: config_service.handle_member_poll,
            MemberAction.INTERVAL: config_service.handle_member_interval,
        }

    async def handle(self, event: AstrMessageEvent, args: list[str]) -> MessageEventResult:
        if not args or args[0].lower() not in ALL_MEMBER_ACTIONS:
            return self._message(
                "usage: /glog member check [group_id]\n"
                "usage: /glog member status [group_id]\n"
                "usage: /glog member poll on|off [group_id]\n"
                "usage: /glog member interval <seconds>"
            )

        action = args[0].lower()
        return await self._action_registry[action](event, args[1:])

    def _message(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)
