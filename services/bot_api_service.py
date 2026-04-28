from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from ..domain.avatar_guard_models import (
        AvatarRollbackExecution,
        AvatarRollbackFailureReason,
    )
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent
except ImportError:
    from domain.avatar_guard_models import AvatarRollbackExecution, AvatarRollbackFailureReason
    logger = logging.getLogger(__name__)
    AstrMessageEvent = Any

if TYPE_CHECKING:
    try:
        from ..platforms.permissions import PermissionService
    except ImportError:
        from platforms.permissions import PermissionService


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
    ) -> AvatarRollbackExecution:
        normalized_path = str(baseline_image_path).strip()
        if not normalized_path:
            return AvatarRollbackExecution(
                success=False,
                error="baseline image path missing",
                failure_reason=AvatarRollbackFailureReason.PATH_MISSING,
            )

        candidates, path_error = self._build_group_portrait_candidates(normalized_path)
        if path_error:
            logger.error(
                "[GroupEventLog] set_group_portrait skipped group=%s path=%s reason=%s",
                group_id,
                normalized_path,
                path_error,
            )
            return AvatarRollbackExecution(
                success=False,
                error=path_error,
                failure_reason=AvatarRollbackFailureReason.PATH_UNREADABLE,
                attempted_inputs=tuple(candidates),
            )

        bot = await self.get_bot()
        if not bot or not hasattr(bot, "api"):
            return AvatarRollbackExecution(
                success=False,
                error="no bot api available",
                failure_reason=AvatarRollbackFailureReason.API_REJECTED,
                attempted_inputs=tuple(candidates),
            )

        last_error = "set_group_portrait failed"
        for file_value in candidates:
            try:
                await bot.api.call_action(
                    "set_group_portrait",
                    group_id=int(group_id),
                    file=file_value,
                )
                return AvatarRollbackExecution(
                    success=True,
                    applied_input=file_value,
                    attempted_inputs=tuple(candidates),
                )
            except Exception as exc:
                last_error = str(exc)
        logger.error(
            "[GroupEventLog] set_group_portrait failed group=%s attempted_inputs=%s err=%s",
            group_id,
            candidates,
            last_error,
        )
        return AvatarRollbackExecution(
            success=False,
            error=last_error,
            failure_reason=AvatarRollbackFailureReason.API_REJECTED,
            attempted_inputs=tuple(candidates),
        )

    def _build_group_portrait_candidates(
        self, baseline_image_path: str
    ) -> tuple[list[str], str]:
        candidates: list[str] = []
        normalized_path = str(baseline_image_path).strip()
        self._append_unique_candidate(candidates, normalized_path)

        if not self._is_local_filesystem_path(normalized_path):
            return candidates, ""

        baseline_path = Path(normalized_path)
        if not baseline_path.exists():
            return candidates, f"baseline image path not found: {normalized_path}"
        if not baseline_path.is_file():
            return candidates, f"baseline image path is not a file: {normalized_path}"

        self._append_unique_candidate(candidates, baseline_path.as_posix())
        self._append_unique_candidate(candidates, baseline_path.as_uri())
        return candidates, ""

    def _is_local_filesystem_path(self, value: str) -> bool:
        lowered = value.lower()
        if lowered.startswith(("http://", "https://", "file://", "base64://", "data:")):
            return False
        return Path(value).is_absolute()

    def _append_unique_candidate(self, candidates: list[str], value: str) -> None:
        normalized = str(value).strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
