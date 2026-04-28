from __future__ import annotations

import logging
from typing import Any

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent, MessageEventResult
except ImportError:
    logger = logging.getLogger(__name__)
    AstrMessageEvent = Any  # type: ignore[misc,assignment]

    class MessageEventResult:
        def __init__(self) -> None:
            self.message_text = ""

        def message(self, text: str) -> "MessageEventResult":
            self.message_text = text
            return self

try:
    from .glog_command_constants import GlogSubCommand
    from .glog_config_service import GlogConfigService
    from .glog_group_service import GlogGroupService
    from .glog_sub_commands import (
        AvatarCommandHandler,
        BindCommandHandler,
        DisableCommandHandler,
        EnableCommandHandler,
        HelpCommandHandler,
        ListCommandHandler,
        MemberCommandHandler,
        PluginCommandHandler,
        PushCommandHandler,
        RecallCommandHandler,
        RollbackCommandHandler,
        StatusCommandHandler,
        UnbindCommandHandler,
    )
except ImportError:
    from commands.glog_command_constants import GlogSubCommand
    from commands.glog_config_service import GlogConfigService
    from commands.glog_group_service import GlogGroupService
    from commands.glog_sub_commands import (
        AvatarCommandHandler,
        BindCommandHandler,
        DisableCommandHandler,
        EnableCommandHandler,
        HelpCommandHandler,
        ListCommandHandler,
        MemberCommandHandler,
        PluginCommandHandler,
        PushCommandHandler,
        RecallCommandHandler,
        RollbackCommandHandler,
        StatusCommandHandler,
        UnbindCommandHandler,
    )


class GlogCommandHandler:
    def __init__(
        self,
        config_service: GlogConfigService,
        group_service: GlogGroupService,
    ) -> None:
        self._help_handler = HelpCommandHandler(config_service)
        self._registry = {
            GlogSubCommand.HELP: self._help_handler,
            GlogSubCommand.STATUS: StatusCommandHandler(config_service),
            GlogSubCommand.LIST: ListCommandHandler(config_service),
            GlogSubCommand.PLUGIN: PluginCommandHandler(config_service),
            GlogSubCommand.ENABLE: EnableCommandHandler(config_service),
            GlogSubCommand.DISABLE: DisableCommandHandler(config_service),
            GlogSubCommand.PUSH: PushCommandHandler(config_service),
            GlogSubCommand.BIND: BindCommandHandler(config_service),
            GlogSubCommand.UNBIND: UnbindCommandHandler(config_service),
            GlogSubCommand.ROLLBACK: RollbackCommandHandler(group_service),
            GlogSubCommand.RECALL: RecallCommandHandler(config_service),
            GlogSubCommand.AVATAR: AvatarCommandHandler(config_service, group_service),
            GlogSubCommand.MEMBER: MemberCommandHandler(config_service, group_service),
        }

    async def handle_glog(self, event: AstrMessageEvent) -> MessageEventResult:
        args = event.get_message_str().strip().split()
        if len(args) < 2:
            return await self._help_handler.handle(event, [])

        sub_command = args[1].lower()
        command_handler = self._registry.get(sub_command)
        if not command_handler:
            return self._message(f"unknown sub-command: {sub_command}\nuse /glog help")

        try:
            return await command_handler.handle(event, args[2:])
        except Exception as exc:
            logger.error(
                "[GroupEventLog] glog command failed sub_command=%s args=%s err=%s",
                sub_command,
                args[2:],
                exc,
                exc_info=True,
            )
            return self._message(f"command failed: {sub_command}")

    def _message(self, text: str) -> MessageEventResult:
        return MessageEventResult().message(text)
