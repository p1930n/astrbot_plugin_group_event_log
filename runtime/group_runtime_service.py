from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from astrbot.api.event import AstrMessageEvent, MessageEventResult
except ImportError:
    AstrMessageEvent = Any  # type: ignore[misc,assignment]

    class MessageEventResult:
        def __init__(self) -> None:
            self.message_text = ""

        def message(self, text: str) -> "MessageEventResult":
            self.message_text = text
            return self

try:
    from ..domain.avatar_guard_models import AvatarHashStatus
    from ..domain.avatar_hash import AvatarHashTransition
    from ..domain.avatar_probe import build_avatar_probe_record
    from ..domain.member_profile import MemberProfileChange
    from ..domain.models import SourceGroupConfig
    from ..domain.notice_adapter import GroupNoticeEvent
    from .group_runtime_summary import (
        build_avatar_check_summary,
        build_avatar_probe_summary,
        build_avatar_status_summary,
        build_member_check_summary,
        build_member_status_summary,
    )
except ImportError:
    from domain.avatar_guard_models import AvatarHashStatus
    from domain.avatar_hash import AvatarHashTransition
    from domain.avatar_probe import build_avatar_probe_record
    from domain.member_profile import MemberProfileChange
    from domain.models import SourceGroupConfig
    from domain.notice_adapter import GroupNoticeEvent
    from runtime.group_runtime_summary import (
        build_avatar_check_summary,
        build_avatar_probe_summary,
        build_avatar_status_summary,
        build_member_check_summary,
        build_member_status_summary,
    )

if TYPE_CHECKING:
    try:
        from ..services.avatar_guard_service import AvatarGuardService
        from ..services.bot_api_service import BotApiService
        from ..services.group_name_guard_service import GroupNameGuardService
        from .group_task_coordinator import GroupTaskCoordinator
        from ..services.member_profile_service import MemberProfileService
        from ..storage.persistence import ConfigPersistence
        from ..runtime.runtime_config_store import RuntimeConfigStore
    except ImportError:
        from services.avatar_guard_service import AvatarGuardService
        from services.bot_api_service import BotApiService
        from services.group_name_guard_service import GroupNameGuardService
        from runtime.group_task_coordinator import GroupTaskCoordinator
        from services.member_profile_service import MemberProfileService
        from storage.persistence import ConfigPersistence
        from runtime.runtime_config_store import RuntimeConfigStore


class GroupRuntimeService:
    def __init__(
        self,
        config_store: "RuntimeConfigStore",
        persistence: "ConfigPersistence",
        bot_api: "BotApiService",
        avatar_guard: "AvatarGuardService",
        group_name_guard: "GroupNameGuardService",
        member_profile_service: "MemberProfileService",
        group_task_coordinator: "GroupTaskCoordinator",
    ) -> None:
        self._config_store = config_store
        self._persistence = persistence
        self._bot_api = bot_api
        self._avatar_guard = avatar_guard
        self._group_name_guard = group_name_guard
        self._member_profile_service = member_profile_service
        self._group_task_coordinator = group_task_coordinator

    def resolve_enabled_push_targets(self, source_config: SourceGroupConfig) -> list[str]:
        result: list[str] = []
        for push_group_id in source_config.push_group_ids:
            push_group = self._config_store.config.push_groups.get(push_group_id)
            if push_group and push_group.enabled:
                result.append(push_group_id)
        return result

    async def run_avatar_poll_check(self, group_id: str) -> None:
        await self._check_group_avatar(group_id, trigger="poll", emit_logs=True)

    async def run_member_profile_poll_check(self, group_id: str) -> None:
        await self._check_group_member_profiles(
            group_id,
            detection_mode="polling_snapshot",
            emit_logs=True,
        )

    async def handle_passive_member_profile(
        self,
        group_id: str,
        user_id: str,
        card: str | None,
        nickname: str | None,
        push_group_ids: list[str],
    ) -> None:
        async with self._group_task_coordinator.member_profile_lock(group_id):
            await self._member_profile_service.handle_passive_member_profile(
                group_id,
                user_id,
                card,
                nickname,
                push_group_ids,
            )

    async def handle_group_name_rollback(
        self,
        notice: GroupNoticeEvent,
        push_group_ids: list[str],
    ) -> None:
        async with self._group_task_coordinator.group_name_lock(notice.group_id):
            await self._group_name_guard.handle_rollback(notice, push_group_ids)

    async def handle_avatar_probe(
        self, event: AstrMessageEvent, group_id: str
    ) -> MessageEventResult:
        bot = await self._bot_api.get_bot(event)
        if not bot or not hasattr(bot, "api"):
            return MessageEventResult().message("no bot api available")

        group_info = await self._bot_api.call_group_metadata_api_with_bot(
            bot,
            "get_group_info",
            group_id,
        )
        group_info_ex = await self._bot_api.call_group_metadata_api_with_bot(
            bot,
            "get_group_info_ex",
            group_id,
        )
        record = build_avatar_probe_record(group_id, group_info, group_info_ex)
        saved_path = await self._persistence.save_avatar_probe(group_id, record)

        return MessageEventResult().message(
            "\n".join(build_avatar_probe_summary(record, saved_path))
        )

    async def handle_avatar_check(self, group_id: str) -> MessageEventResult:
        transition, sent_push_groups = await self._check_group_avatar(
            group_id,
            trigger="manual",
            emit_logs=True,
        )
        return MessageEventResult().message(
            "\n".join(
                build_avatar_check_summary(
                    transition,
                    sent_push_groups,
                    self._persistence.database_path,
                )
            )
        )

    async def handle_avatar_status(self, group_id: str) -> MessageEventResult:
        state = await self._persistence.load_avatar_hash_state(group_id)
        record = await self._persistence.load_avatar_probe(group_id)
        group_name_state = await self._persistence.load_group_name_guard(group_id)
        return MessageEventResult().message(
            "\n".join(
                build_avatar_status_summary(
                    group_id,
                    state,
                    record,
                    group_name_state,
                    self._persistence.database_path,
                    self._persistence.avatar_probe_path(group_id),
                )
            )
        )

    async def handle_member_check(self, group_id: str) -> MessageEventResult:
        state, changes, push_group_ids = await self._check_group_member_profiles(
            group_id,
            detection_mode="manual_snapshot",
            emit_logs=True,
        )
        return MessageEventResult().message(
            "\n".join(
                build_member_check_summary(
                    group_id,
                    state,
                    changes,
                    push_group_ids,
                    self._persistence.database_path,
                )
            )
        )

    async def handle_member_status(self, group_id: str) -> MessageEventResult:
        state = await self._persistence.load_member_profile_state(group_id)
        return MessageEventResult().message(
            "\n".join(
                build_member_status_summary(
                    group_id,
                    state,
                    self._persistence.database_path,
                )
            )
        )

    async def set_avatar_rollback(
        self,
        group_id: str,
        source_config: SourceGroupConfig,
        enabled: bool,
    ) -> MessageEventResult:
        if enabled:
            transition, _ = await self._check_group_avatar(
                group_id,
                trigger="rollback_baseline_refresh",
                emit_logs=False,
                force_adopt_baseline=True,
            )
            if transition.status == AvatarHashStatus.FETCH_FAILED:
                return MessageEventResult().message(
                    f"avatar rollback baseline refresh failed: {transition.error}"
                )

        source_config.avatar_rollback_enabled = enabled
        await self._config_store.save()
        return MessageEventResult().message(
            f"avatar rollback for {group_id} set to {'on' if enabled else 'off'}"
        )

    async def set_group_name_rollback(
        self,
        group_id: str,
        source_config: SourceGroupConfig,
        enabled: bool,
    ) -> MessageEventResult:
        if enabled:
            success, baseline_name, error = await self._group_name_guard.refresh_baseline(group_id)
            if not success:
                return MessageEventResult().message(
                    f"group name rollback baseline refresh failed: {error}"
                )
        else:
            baseline_name = ""

        source_config.group_name_rollback_enabled = enabled
        await self._config_store.save()
        suffix = f"\nbaseline_name: {baseline_name}" if baseline_name else ""
        return MessageEventResult().message(
            f"group name rollback for {group_id} set to {'on' if enabled else 'off'}{suffix}"
        )

    async def _check_group_avatar(
        self,
        group_id: str,
        trigger: str,
        emit_logs: bool,
        force_adopt_baseline: bool = False,
    ) -> tuple[AvatarHashTransition, list[str]]:
        async with self._group_task_coordinator.avatar_lock(group_id):
            source_config = self._config_store.config.monitored_groups.get(group_id)
            push_group_ids = (
                self.resolve_enabled_push_targets(source_config)
                if source_config
                else []
            )
            return await self._avatar_guard.check_group_avatar(
                group_id,
                source_config,
                push_group_ids,
                trigger,
                emit_logs,
                force_adopt_baseline=force_adopt_baseline,
            )

    async def _check_group_member_profiles(
        self,
        group_id: str,
        detection_mode: str,
        emit_logs: bool,
    ) -> tuple[dict[str, object], list[MemberProfileChange], list[str]]:
        async with self._group_task_coordinator.member_profile_lock(group_id):
            source_config = self._config_store.config.monitored_groups.get(group_id)
            push_group_ids = (
                self.resolve_enabled_push_targets(source_config)
                if source_config and source_config.enabled
                else []
            )
            return await self._member_profile_service.check_group_member_profiles(
                group_id,
                detection_mode,
                emit_logs,
                push_group_ids,
            )
