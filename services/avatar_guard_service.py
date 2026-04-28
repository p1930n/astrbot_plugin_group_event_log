from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable

try:
    from ..domain.avatar_guard_models import (
        DEFAULT_AVATAR_VERIFY_RETRY_POLICY,
        AvatarHashStatus,
        AvatarRollbackFailureReason,
        AvatarRollbackResult,
        AvatarVerifyRetryPolicy,
    )
    from ..domain.avatar_hash import (
        AvatarHashFetchResult,
        AvatarHashTransition,
        apply_avatar_hash_result,
        fetch_group_avatar_hash,
    )
except ImportError:
    from domain.avatar_guard_models import (
        DEFAULT_AVATAR_VERIFY_RETRY_POLICY,
        AvatarHashStatus,
        AvatarRollbackFailureReason,
        AvatarRollbackResult,
        AvatarVerifyRetryPolicy,
    )
    from domain.avatar_hash import (
        AvatarHashFetchResult,
        AvatarHashTransition,
        apply_avatar_hash_result,
        fetch_group_avatar_hash,
    )

if TYPE_CHECKING:
    try:
        from ..services.bot_api_service import BotApiService
        from ..services.log_dispatch_service import LogDispatchService
        from ..domain.models import SourceGroupConfig
    except ImportError:
        from services.bot_api_service import BotApiService
        from services.log_dispatch_service import LogDispatchService
        from domain.models import SourceGroupConfig


class AvatarGuardService:
    def __init__(
        self,
        persistence: Any,
        bot_api: "BotApiService",
        log_dispatcher: "LogDispatchService",
        fetch_avatar_hash: Callable[[str], Awaitable[AvatarHashFetchResult]] = fetch_group_avatar_hash,
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_policy: AvatarVerifyRetryPolicy = DEFAULT_AVATAR_VERIFY_RETRY_POLICY,
    ) -> None:
        self._persistence = persistence
        self._bot_api = bot_api
        self._log_dispatcher = log_dispatcher
        self._fetch_avatar_hash = fetch_avatar_hash
        self._sleep = sleep_func
        self._retry_policy = retry_policy

    async def check_group_avatar(
        self,
        group_id: str,
        source_config: "SourceGroupConfig | None",
        push_group_ids: list[str],
        trigger: str,
        emit_logs: bool,
        force_adopt_baseline: bool = False,
    ) -> tuple[AvatarHashTransition, list[str]]:
        previous_state = await self._persistence.load_avatar_hash_state(group_id)
        fetch_result = await self._fetch_avatar_hash(group_id)
        protect_baseline = bool(
            source_config
            and source_config.avatar_rollback_enabled
            and not force_adopt_baseline
        )
        transition = apply_avatar_hash_result(
            group_id,
            previous_state,
            fetch_result,
            protect_baseline,
        )

        if fetch_result.ok and (
            transition.baseline_created
            or transition.adopted_new_baseline
            or force_adopt_baseline
        ):
            baseline_image_path = await self._persistence.save_avatar_baseline_image(
                group_id,
                fetch_result.image_bytes,
                fetch_result.file_suffix,
            )
            transition.state["baseline_image_path"] = baseline_image_path
            transition.state["baseline_hash"] = fetch_result.hash_value
            transition.state["last_hash"] = fetch_result.hash_value
            transition.state["baseline_updated_at"] = fetch_result.checked_at
            transition.baseline_image_path = baseline_image_path
            transition.baseline_hash = fetch_result.hash_value

        if protect_baseline and transition.changed:
            transition.rollback_attempted = True
            rollback_execution = await self._bot_api.rollback_group_avatar(
                group_id,
                str(transition.state.get("baseline_image_path", "")).strip(),
            )
            success = rollback_execution.success
            rollback_error = rollback_execution.error
            transition.rollback_succeeded = success
            transition.rollback_error = rollback_error
            transition.rollback_failure_reason = (
                rollback_execution.failure_reason.value
                if rollback_execution.failure_reason
                else ""
            )
            transition.rollback_applied_input = rollback_execution.applied_input
            transition.rollback_attempted_inputs = rollback_execution.attempted_inputs
            transition.state["last_rollback_at"] = transition.checked_at
            transition.state["last_rollback_result"] = (
                AvatarRollbackResult.SUCCESS.value
                if success
                else AvatarRollbackResult.FAILED.value
            )
            transition.state["last_rollback_failure_reason"] = (
                transition.rollback_failure_reason
            )
            transition.state["last_rollback_applied_input"] = (
                transition.rollback_applied_input
            )
            transition.state["last_rollback_attempted_inputs"] = list(
                transition.rollback_attempted_inputs
            )
            transition.state["last_rollback_error"] = rollback_error
            if success:
                verified_hash, verify_error = await self._refresh_compare_hash_after_rollback(
                    group_id,
                    transition.state,
                )
                if verified_hash:
                    transition.state["baseline_hash"] = verified_hash
                    transition.state["last_hash"] = verified_hash
                    transition.state["last_observed_hash"] = verified_hash
                    transition.state["last_error"] = ""
                    transition.state["last_rollback_failure_reason"] = ""
                    transition.state["last_rollback_error"] = ""
                    transition.rollback_failure_reason = ""
                    transition.rollback_error = ""
                    transition.status = AvatarHashStatus.ROLLBACK_SUCCESS
                else:
                    transition.state["last_error"] = verify_error
                    transition.rollback_error = verify_error
                    transition.rollback_failure_reason = (
                        AvatarRollbackFailureReason.VERIFY_FAILED.value
                    )
                    transition.state["last_rollback_failure_reason"] = (
                        transition.rollback_failure_reason
                    )
                    transition.state["last_rollback_error"] = verify_error
                    transition.status = AvatarHashStatus.ROLLBACK_SUCCESS_UNVERIFIED
            else:
                transition.status = AvatarHashStatus.ROLLBACK_FAILED

        await self._persistence.save_avatar_hash_state(group_id, transition.state)

        sent_push_groups: list[str] = []
        if (
            emit_logs
            and transition.changed
            and source_config
            and source_config.enabled
            and source_config.event_switches.get("avatar_hash", True)
            and push_group_ids
        ):
            await self._log_dispatcher.dispatch_avatar_hash_logs(
                group_id,
                push_group_ids,
                transition,
                trigger,
            )
            sent_push_groups = list(push_group_ids)

        return transition, sent_push_groups

    async def _refresh_compare_hash_after_rollback(
        self,
        group_id: str,
        state: dict[str, object],
    ) -> tuple[str, str]:
        last_error = "avatar verify after rollback failed"

        for delay_seconds in self._retry_policy.delays_seconds:
            await self._sleep(delay_seconds)
            fetch_result = await self._fetch_avatar_hash(group_id)
            if not fetch_result.ok:
                last_error = fetch_result.error
                continue

            verified_hash = fetch_result.hash_value
            state["last_observed_source_url"] = fetch_result.source_url
            state["last_observed_byte_size"] = fetch_result.byte_size
            state["last_observed_content_type"] = fetch_result.content_type
            state["last_verified_after_rollback_at"] = fetch_result.checked_at
            state["last_verified_after_rollback_hash"] = verified_hash
            return verified_hash, ""

        return "", last_error
