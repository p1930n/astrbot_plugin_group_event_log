from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from ..domain.avatar_guard_models import (
        AvatarRollbackExecution,
        AvatarRollbackFailureReason,
    )
    from ..platforms.bot_api_results import (
        BotApiCallResult,
        GroupInfoResult,
        GroupMemberListResult,
        GroupNameSetResult,
        GroupPortraitSetResult,
    )
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent
except ImportError:
    from domain.avatar_guard_models import AvatarRollbackExecution, AvatarRollbackFailureReason
    from platforms.bot_api_results import (
        BotApiCallResult,
        GroupInfoResult,
        GroupMemberListResult,
        GroupNameSetResult,
        GroupPortraitSetResult,
    )
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
        result = await self.call_group_metadata_result(action, group_id, event)
        return result.as_legacy_dict()

    async def call_group_metadata_result(
        self,
        action: str,
        group_id: str,
        event: AstrMessageEvent | None = None,
    ) -> BotApiCallResult:
        bot = await self.get_bot(event)
        if not bot or not hasattr(bot, "api"):
            return BotApiCallResult(
                ok=False,
                action=action,
                error="no bot api available",
            )
        return await self.call_group_metadata_result_with_bot(bot, action, group_id)

    async def call_group_metadata_api_with_bot(
        self, bot: Any, action: str, group_id: str
    ) -> dict[str, object]:
        result = await self.call_group_metadata_result_with_bot(bot, action, group_id)
        return result.as_legacy_dict()

    async def call_group_metadata_result_with_bot(
        self, bot: Any, action: str, group_id: str
    ) -> BotApiCallResult:
        try:
            data = await bot.api.call_action(action, group_id=int(group_id))
            return BotApiCallResult(ok=True, action=action, data=data)
        except Exception as exc:
            safe_error = self._safe_exception_message(exc, f"{action} failed")
            logger.error(
                "[GroupEventLog] %s failed for group=%s err=%s",
                action,
                group_id,
                safe_error,
            )
            return BotApiCallResult(
                ok=False,
                action=action,
                error=safe_error,
            )

    async def call_group_member_list_api(self, group_id: str) -> dict[str, object]:
        result = await self.get_group_member_list_result(group_id)
        return result.as_legacy_dict()

    async def get_group_member_list_result(
        self,
        group_id: str,
    ) -> GroupMemberListResult:
        bot = await self.get_bot()
        if not bot or not hasattr(bot, "api"):
            return GroupMemberListResult(
                ok=False,
                group_id=group_id,
                error="no bot api available",
            )

        try:
            data = await bot.api.call_action(
                "get_group_member_list",
                group_id=int(group_id),
                no_cache=True,
            )
            return GroupMemberListResult(
                ok=True,
                group_id=group_id,
                payload=data,
                used_no_cache=True,
            )
        except Exception as first_exc:
            try:
                data = await bot.api.call_action(
                    "get_group_member_list",
                    group_id=int(group_id),
                )
                return GroupMemberListResult(
                    ok=True,
                    group_id=group_id,
                    payload=data,
                    fallback_used=True,
                )
            except Exception as second_exc:
                first_error = self._safe_exception_message(
                    first_exc,
                    "get_group_member_list failed",
                )
                second_error = self._safe_exception_message(
                    second_exc,
                    "get_group_member_list failed",
                )
                logger.error(
                    "[GroupEventLog] get_group_member_list failed for group=%s err=%s / %s",
                    group_id,
                    first_error,
                    second_error,
                )
                return GroupMemberListResult(
                    ok=False,
                    group_id=group_id,
                    error=second_error,
                )

    async def get_current_group_name(self, group_id: str) -> tuple[str, str]:
        result = await self.get_group_info_result(group_id)
        if not result.ok:
            return "", result.error

        return result.group_name, ""

    async def get_group_info_result(self, group_id: str) -> GroupInfoResult:
        response = await self.call_group_metadata_result("get_group_info", group_id)
        if not response.ok:
            return GroupInfoResult(
                ok=False,
                group_id=group_id,
                error=response.error or "get_group_info failed",
            )

        if not isinstance(response.data, dict):
            return GroupInfoResult(
                ok=False,
                group_id=group_id,
                error="invalid group info payload",
            )

        return GroupInfoResult(ok=True, group_id=group_id, payload=response.data)

    async def set_group_name(self, group_id: str, group_name: str) -> tuple[bool, str]:
        result = await self.set_group_name_result(group_id, group_name)
        return result.as_legacy_tuple()

    async def set_group_name_result(
        self,
        group_id: str,
        group_name: str,
    ) -> GroupNameSetResult:
        bot = await self.get_bot()
        if not bot or not hasattr(bot, "api"):
            return GroupNameSetResult(
                ok=False,
                group_id=group_id,
                group_name=group_name,
                error="no bot api available",
            )

        try:
            await bot.api.call_action(
                "set_group_name",
                group_id=int(group_id),
                group_name=group_name,
            )
            return GroupNameSetResult(ok=True, group_id=group_id, group_name=group_name)
        except Exception as exc:
            safe_error = self._safe_exception_message(exc, "set_group_name failed")
            logger.error(
                "[GroupEventLog] set_group_name failed for group=%s err=%s",
                group_id,
                safe_error,
            )
            return GroupNameSetResult(
                ok=False,
                group_id=group_id,
                group_name=group_name,
                error=safe_error,
            )

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
                error=self._public_portrait_path_error(path_error),
                failure_reason=AvatarRollbackFailureReason.PATH_UNREADABLE,
                attempted_inputs=tuple(candidates),
            )

        result = await self.set_group_portrait_result(group_id, candidates)
        if result.ok:
            return AvatarRollbackExecution(
                success=True,
                applied_input=result.applied_input,
                attempted_inputs=result.attempted_inputs,
            )

        return AvatarRollbackExecution(
            success=False,
            error=result.error,
            failure_reason=AvatarRollbackFailureReason.API_REJECTED,
            attempted_inputs=result.attempted_inputs,
        )

    async def set_group_portrait_result(
        self,
        group_id: str,
        candidates: list[str],
    ) -> GroupPortraitSetResult:
        attempted_inputs = tuple(candidates)
        bot = await self.get_bot()
        if not bot or not hasattr(bot, "api"):
            return GroupPortraitSetResult(
                ok=False,
                group_id=group_id,
                attempted_inputs=attempted_inputs,
                error="no bot api available",
            )

        last_error = "set_group_portrait failed"
        for file_value in candidates:
            try:
                await bot.api.call_action(
                    "set_group_portrait",
                    group_id=int(group_id),
                    file=file_value,
                )
                return GroupPortraitSetResult(
                    ok=True,
                    group_id=group_id,
                    applied_input=file_value,
                    attempted_inputs=attempted_inputs,
                )
            except Exception as exc:
                last_error = self._safe_exception_message(
                    exc,
                    "set_group_portrait failed",
                    (file_value,),
                )
        logger.error(
            "[GroupEventLog] set_group_portrait failed group=%s attempted_inputs=%s err=%s",
            group_id,
            candidates,
            last_error,
        )
        return GroupPortraitSetResult(
            ok=False,
            group_id=group_id,
            error=last_error,
            attempted_inputs=attempted_inputs,
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

    def _safe_exception_message(
        self,
        exc: Exception,
        fallback: str,
        sensitive_fragments: tuple[str, ...] = (),
    ) -> str:
        message = str(exc).strip()
        if not message or "\n" in message or "\r" in message:
            return fallback
        lowered = message.lower()
        sensitive_markers = ("token", "authorization", "cookie", "traceback")
        if any(marker in lowered for marker in sensitive_markers):
            return fallback
        if any(fragment and fragment in message for fragment in sensitive_fragments):
            return fallback
        return message

    def _public_portrait_path_error(self, path_error: str) -> str:
        if "not found" in path_error:
            return "baseline image path not found"
        if "not a file" in path_error:
            return "baseline image path is not a file"
        return "baseline image path unreadable"
