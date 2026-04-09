from __future__ import annotations

import logging
import uuid
from typing import Any

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent
except ImportError:
    logger = logging.getLogger(__name__)
    AstrMessageEvent = Any

try:
    from .avatar_hash import AvatarHashTransition
    from .bot_api_service import BotApiService
    from .log_formatter import (
        format_avatar_hash_log,
        format_group_name_rollback_log,
        format_group_recall_log,
        format_member_profile_change_log,
        format_notice_log,
    )
    from .member_profile import MemberProfileChange
    from .message_cache import CachedGroupMessage
    from .notice_adapter import GroupNoticeEvent
except ImportError:
    from avatar_hash import AvatarHashTransition
    from bot_api_service import BotApiService
    from log_formatter import (
        format_avatar_hash_log,
        format_group_name_rollback_log,
        format_group_recall_log,
        format_member_profile_change_log,
        format_notice_log,
    )
    from member_profile import MemberProfileChange
    from message_cache import CachedGroupMessage
    from notice_adapter import GroupNoticeEvent


class LogDispatchService:
    def __init__(self, bot_api: BotApiService) -> None:
        self._bot_api = bot_api

    async def dispatch_notice_logs(
        self,
        event: AstrMessageEvent,
        notice: GroupNoticeEvent,
        push_group_ids: list[str],
    ) -> None:
        bot = await self._bot_api.get_bot(event)
        if not bot or not hasattr(bot, "api"):
            logger.error(
                "[GroupEventLog] no bot available for notice dispatch group=%s event=%s",
                notice.group_id,
                notice.event_key,
            )
            return

        trace_id = uuid.uuid4().hex[:8]
        message = format_notice_log(notice, trace_id)
        await self._send_group_logs(
            bot,
            push_group_ids,
            message,
            f"{notice.event_key} from {notice.group_id}",
        )

    async def dispatch_avatar_hash_logs(
        self,
        group_id: str,
        push_group_ids: list[str],
        transition: AvatarHashTransition,
        trigger: str,
    ) -> None:
        bot = await self._bot_api.get_bot()
        if not bot or not hasattr(bot, "api"):
            logger.error(
                "[GroupEventLog] no bot available for avatar dispatch group=%s",
                group_id,
            )
            return

        trace_id = uuid.uuid4().hex[:8]
        message = format_avatar_hash_log(transition, trace_id, trigger)
        await self._send_group_logs(
            bot,
            push_group_ids,
            message,
            f"avatar_hash.changed from {group_id}",
        )

    async def dispatch_group_name_rollback_logs(
        self,
        group_id: str,
        push_group_ids: list[str],
        observed_name: str,
        baseline_name: str,
        rollback_result: str,
        error: str = "",
    ) -> None:
        if not push_group_ids:
            return

        bot = await self._bot_api.get_bot()
        if not bot or not hasattr(bot, "api"):
            logger.error(
                "[GroupEventLog] no bot available for group name rollback log group=%s",
                group_id,
            )
            return

        trace_id = uuid.uuid4().hex[:8]
        message = format_group_name_rollback_log(
            group_id,
            trace_id,
            observed_name,
            baseline_name,
            rollback_result,
            error,
        )
        await self._send_group_logs(
            bot,
            push_group_ids,
            message,
            f"group_name.rollback from {group_id}",
        )

    async def dispatch_member_profile_logs(
        self,
        group_id: str,
        push_group_ids: list[str],
        changes: list[MemberProfileChange],
    ) -> list[str]:
        if not push_group_ids:
            return []

        bot = await self._bot_api.get_bot()
        if not bot or not hasattr(bot, "api"):
            logger.error(
                "[GroupEventLog] no bot available for member profile log group=%s",
                group_id,
            )
            return []

        for change in changes:
            trace_id = uuid.uuid4().hex[:8]
            message = format_member_profile_change_log(change, trace_id)
            await self._send_group_logs(
                bot,
                push_group_ids,
                message,
                f"member_profile.changed from {group_id}:{change.user_id}",
            )

        return list(push_group_ids)

    async def dispatch_group_recall_logs(
        self,
        event: AstrMessageEvent,
        notice: GroupNoticeEvent,
        push_group_ids: list[str],
        cached_message: CachedGroupMessage | None,
        show_message_content: bool,
    ) -> None:
        if not push_group_ids:
            return

        bot = await self._bot_api.get_bot(event)
        if not bot or not hasattr(bot, "api"):
            logger.error(
                "[GroupEventLog] no bot available for recall dispatch group=%s",
                notice.group_id,
            )
            return

        trace_id = uuid.uuid4().hex[:8]
        message = format_group_recall_log(
            notice,
            trace_id,
            cached_message,
            show_message_content,
        )
        await self._send_group_logs(
            bot,
            push_group_ids,
            message,
            f"group_recall from {notice.group_id}:{notice.details.get('message_id', '-')}",
        )

    async def _send_group_logs(
        self,
        bot: Any,
        push_group_ids: list[str],
        message: str,
        log_label: str,
    ) -> None:
        for push_group_id in push_group_ids:
            try:
                await bot.api.call_action(
                    "send_group_msg",
                    group_id=int(push_group_id),
                    message=message,
                )
                logger.info(
                    "[GroupEventLog] dispatched %s to push group %s",
                    log_label,
                    push_group_id,
                )
            except Exception as exc:
                logger.error(
                    "[GroupEventLog] push failed label=%s target=%s err=%s",
                    log_label,
                    push_group_id,
                    exc,
                )
