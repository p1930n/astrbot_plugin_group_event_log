from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

try:
    from .group_name_guard import build_group_name_baseline_state
    from .notice_adapter import GroupNoticeEvent
except ImportError:
    from group_name_guard import build_group_name_baseline_state
    from notice_adapter import GroupNoticeEvent

if TYPE_CHECKING:
    try:
        from .bot_api_service import BotApiService
        from .log_dispatch_service import LogDispatchService
    except ImportError:
        from bot_api_service import BotApiService
        from log_dispatch_service import LogDispatchService


class GroupNameGuardService:
    def __init__(
        self,
        persistence: Any,
        bot_api: "BotApiService",
        log_dispatcher: "LogDispatchService",
    ) -> None:
        self._persistence = persistence
        self._bot_api = bot_api
        self._log_dispatcher = log_dispatcher

    async def refresh_baseline(self, group_id: str) -> tuple[bool, str, str]:
        current_name, error = await self._bot_api.get_current_group_name(group_id)
        if error:
            return False, "", error

        state = build_group_name_baseline_state(group_id, current_name)
        await self._persistence.save_group_name_guard(group_id, state)
        return True, current_name, ""

    async def handle_rollback(
        self,
        notice: GroupNoticeEvent,
        push_group_ids: list[str],
    ) -> None:
        state = await self._persistence.load_group_name_guard(notice.group_id)
        baseline_name = str(state.get("baseline_name", "")).strip()
        observed_name = str(notice.details.get("name_new", "")).strip()

        if not baseline_name:
            success, _, error = await self.refresh_baseline(notice.group_id)
            if not success:
                logger.error(
                    "[GroupEventLog] group name baseline refresh failed group=%s err=%s",
                    notice.group_id,
                    error,
                )
            return

        now = datetime.now().isoformat(timespec="seconds")
        state["group_id"] = notice.group_id
        state["last_checked_at"] = now
        state["last_observed_name"] = observed_name or state.get("last_observed_name", "")

        if not observed_name or observed_name == baseline_name:
            state["last_error"] = ""
            await self._persistence.save_group_name_guard(notice.group_id, state)
            return

        success, error = await self._bot_api.set_group_name(
            notice.group_id,
            baseline_name,
        )
        state["last_changed_at"] = now
        state["change_count"] = int(state.get("change_count", 0) or 0) + 1
        state["last_rollback_at"] = now
        state["last_rollback_result"] = "success" if success else "failed"
        state["last_error"] = error
        await self._persistence.save_group_name_guard(notice.group_id, state)

        await self._log_dispatcher.dispatch_group_name_rollback_logs(
            notice.group_id,
            push_group_ids,
            observed_name,
            baseline_name,
            state["last_rollback_result"],
            error,
        )
