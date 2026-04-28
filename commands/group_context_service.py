from __future__ import annotations

from typing import Any

try:
    from astrbot.api.event import AstrMessageEvent
except ImportError:
    AstrMessageEvent = Any


class GroupContextService:
    """聚合群上下文解析与权限边界判断。"""

    def __init__(self, permissions: Any) -> None:
        self._permissions = permissions

    def current_group_id(self, event: AstrMessageEvent) -> str:
        return str(event.get_group_id() or "").strip()

    async def can_manage_source_group(
        self,
        event: AstrMessageEvent,
        source_group_id: str,
    ) -> bool:
        if self._permissions.is_global_admin(event):
            return True

        current_group_id = self.current_group_id(event)
        if not current_group_id or current_group_id != source_group_id:
            return False

        user_id = str(event.get_sender_id())
        return await self._permissions.is_group_admin_or_owner(
            event,
            user_id,
            source_group_id,
        )

    async def can_query_group_metadata(
        self,
        event: AstrMessageEvent,
        group_id: str,
    ) -> bool:
        if self._permissions.is_global_admin(event):
            return True

        current_group_id = self.current_group_id(event)
        if not current_group_id or current_group_id != group_id:
            return False

        user_id = str(event.get_sender_id())
        return await self._permissions.is_group_admin_or_owner(event, user_id, group_id)

    def resolve_bind_args(
        self,
        event: AstrMessageEvent,
        args: list[str],
    ) -> tuple[str, str, str]:
        if len(args) == 1:
            source_group_id = self.current_group_id(event)
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
