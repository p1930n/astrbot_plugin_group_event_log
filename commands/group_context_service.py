from __future__ import annotations

from typing import Any

try:
    from .command_context import CommandContext
except ImportError:
    from commands.command_context import CommandContext


class GroupContextService:
    """聚合群上下文解析与权限边界判断。"""

    def __init__(self, permissions: Any) -> None:
        self._permissions = permissions

    def current_group_id(self, context: CommandContext) -> str:
        return context.group_id

    def is_global_admin(self, context: CommandContext) -> bool:
        if not context.source_event:
            return False
        return bool(self._permissions.is_global_admin(context.source_event))

    async def can_manage_source_group(
        self,
        context: CommandContext,
        source_group_id: str,
    ) -> bool:
        if self.is_global_admin(context):
            return True

        current_group_id = self.current_group_id(context)
        if not current_group_id or current_group_id != source_group_id:
            return False

        user_id = context.sender_id
        if not context.source_event:
            return False
        return await self._permissions.is_group_admin_or_owner(
            context.source_event,
            user_id,
            source_group_id,
        )

    async def can_query_group_metadata(
        self,
        context: CommandContext,
        group_id: str,
    ) -> bool:
        if self.is_global_admin(context):
            return True

        current_group_id = self.current_group_id(context)
        if not current_group_id or current_group_id != group_id:
            return False

        user_id = context.sender_id
        if not context.source_event:
            return False
        return await self._permissions.is_group_admin_or_owner(
            context.source_event,
            user_id,
            group_id,
        )

    def resolve_bind_args(
        self,
        context: CommandContext,
        args: list[str],
    ) -> tuple[str, str, str]:
        if len(args) == 1:
            source_group_id = self.current_group_id(context)
            push_group_id = args[0].strip()
            if not source_group_id:
                return "", "", "usage: /glog bind <source_group_id> <push_group_id>"
            return source_group_id, push_group_id, ""

        if len(args) == 2:
            return args[0].strip(), args[1].strip(), ""

        return "", "", (
            "usage: /glog bind <push_group_id>\n"
            "usage: /glog bind <source_group_id> <push_group_id>"
        )
