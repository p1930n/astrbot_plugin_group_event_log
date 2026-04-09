from __future__ import annotations

from typing import Any

import astrbot.api.event.filter as filter
import astrbot.api.star as star
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class PermissionService:
    def __init__(self, context: star.Context) -> None:
        self._context = context

    async def get_bot_instance(self, platform: str = "aiocqhttp") -> Any:
        try:
            if platform != "aiocqhttp":
                return None

            adapter = self._context.get_platform(filter.PlatformAdapterType.AIOCQHTTP)
            if adapter and hasattr(adapter, "get_client"):
                return adapter.get_client()
            return adapter
        except Exception as exc:
            logger.error("[GroupEventLog] get bot instance failed: %s", exc)
            return None

    def get_bot_from_event(self, event: AstrMessageEvent) -> Any:
        try:
            if event.get_platform_name() != "aiocqhttp":
                return None

            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            if isinstance(event, AiocqhttpMessageEvent):
                return event.bot
            return None
        except Exception as exc:
            logger.error("[GroupEventLog] get bot from event failed: %s", exc)
            return None

    def is_global_admin(self, event: AstrMessageEvent) -> bool:
        try:
            user_id = str(event.get_sender_id())
            if not hasattr(self._context, "get_config"):
                return False

            config = self._context.get_config()
            if hasattr(config, "get") and config.get("admins_id"):
                return user_id in [str(item) for item in config.get("admins_id", [])]
            if hasattr(config, "admins_id") and config.admins_id:
                return user_id in [str(item) for item in config.admins_id]
            return False
        except Exception:
            return False

    async def is_group_admin_or_owner(
        self, event: AstrMessageEvent, user_id: str, group_id: str
    ) -> bool:
        try:
            bot = self.get_bot_from_event(event)
            if not bot:
                bot = await self.get_bot_instance()
            if not bot or not hasattr(bot, "api"):
                return False

            member_info = await bot.api.call_action(
                "get_group_member_info",
                group_id=int(group_id),
                user_id=int(user_id),
            )
            role = str(member_info.get("role", "member"))
            return role in {"admin", "owner"}
        except Exception as exc:
            logger.error("[GroupEventLog] group admin check failed: %s", exc)
            return False
