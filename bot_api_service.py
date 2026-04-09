from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent
except ImportError:
    logger = logging.getLogger(__name__)
    AstrMessageEvent = Any

if TYPE_CHECKING:
    try:
        from .permissions import PermissionService
    except ImportError:
        from permissions import PermissionService


class BotApiService:
    def __init__(self, permissions: "PermissionService") -> None:
        self._permissions = permissions

    async def get_bot(self, event: AstrMessageEvent | None = None) -> Any:
        bot = self._permissions.get_bot_from_event(event) if event else None
        if not bot:
            bot = await self._permissions.get_bot_instance()
        return bot

    async def is_bot_ready(self, event: AstrMessageEvent | None = None) -> bool:
        bot = await self.get_bot(event)
        if not bot or not hasattr(bot, "api"):
            return False

        try:
            await bot.api.call_action("get_login_info")
            return True
        except Exception:
            return False

    async def call_group_metadata_api(
        self,
        action: str,
        group_id: str,
        event: AstrMessageEvent | None = None,
    ) -> dict[str, object]:
        bot = await self.get_bot(event)
        if not bot or not hasattr(bot, "api"):
            return {
                "ok": False,
                "error": "no bot api available",
            }
        return await self.call_group_metadata_api_with_bot(bot, action, group_id)

    async def call_group_metadata_api_with_bot(
        self, bot: Any, action: str, group_id: str
    ) -> dict[str, object]:
        try:
            data = await bot.api.call_action(action, group_id=int(group_id))
            return {
                "ok": True,
                "data": data,
            }
        except Exception as exc:
            logger.error(
                "[GroupEventLog] %s failed for group=%s err=%s",
                action,
                group_id,
                exc,
            )
            return {
                "ok": False,
                "error": str(exc),
            }

    async def call_group_member_list_api(self, group_id: str) -> dict[str, object]:
        bot = await self.get_bot()
        if not bot or not hasattr(bot, "api"):
            return {
                "ok": False,
                "error": "no bot api available",
            }

        try:
            data = await bot.api.call_action(
                "get_group_member_list",
                group_id=int(group_id),
                no_cache=True,
            )
            return {
                "ok": True,
                "data": data,
            }
        except Exception as first_exc:
            try:
                data = await bot.api.call_action(
                    "get_group_member_list",
                    group_id=int(group_id),
                )
                return {
                    "ok": True,
                    "data": data,
                }
            except Exception as second_exc:
                logger.error(
                    "[GroupEventLog] get_group_member_list failed for group=%s err=%s / %s",
                    group_id,
                    first_exc,
                    second_exc,
                )
                return {
                    "ok": False,
                    "error": str(second_exc),
                }

    async def get_current_group_name(self, group_id: str) -> tuple[str, str]:
        response = await self.call_group_metadata_api("get_group_info", group_id)
        if not response.get("ok"):
            return "", str(response.get("error", "get_group_info failed"))

        data = response.get("data", {})
        if not isinstance(data, dict):
            return "", "invalid group info payload"

        return str(data.get("group_name", "")).strip(), ""

    async def set_group_name(self, group_id: str, group_name: str) -> tuple[bool, str]:
        bot = await self.get_bot()
        if not bot or not hasattr(bot, "api"):
            return False, "no bot api available"

        try:
            await bot.api.call_action(
                "set_group_name",
                group_id=int(group_id),
                group_name=group_name,
            )
            return True, ""
        except Exception as exc:
            return False, str(exc)

    async def rollback_group_avatar(
        self, group_id: str, baseline_image_path: str
    ) -> tuple[bool, str]:
        if not baseline_image_path:
            return False, "baseline image path missing"

        bot = await self.get_bot()
        if not bot or not hasattr(bot, "api"):
            return False, "no bot api available"

        candidates = [baseline_image_path]
        baseline_path = Path(baseline_image_path)
        if baseline_path.is_absolute():
            candidates.append(baseline_path.as_uri())

        last_error = "set_group_portrait failed"
        for file_value in candidates:
            try:
                await bot.api.call_action(
                    "set_group_portrait",
                    group_id=int(group_id),
                    file=file_value,
                )
                return True, ""
            except Exception as exc:
                last_error = str(exc)
        return False, last_error
