from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..commands.glog_command_handler import GlogCommandHandler
from ..commands.glog_config_service import GlogConfigService
from ..commands.glog_event_service import GlogEventSwitchService
from ..commands.glog_group_service import GlogGroupService
from ..commands.group_context_service import GroupContextService
from ..platforms.permissions import PermissionService
from ..services.avatar_guard_service import AvatarGuardService
from ..services.bot_api_service import BotApiService
from ..services.group_name_guard_service import GroupNameGuardService
from ..services.log_dispatch_service import LogDispatchService
from ..services.member_profile_service import MemberProfileService
from ..services.message_recall_service import MessageRecallService
from ..storage.persistence import ConfigPersistence
from .group_runtime_service import GroupRuntimeService
from .group_task_coordinator import GroupTaskCoordinator
from .notice_event_handler import NoticeEventHandler
from .passive_message_handler import PassiveMessageHandler
from .plugin_runtime_state import PluginRuntimeState
from .polling_scheduler import PollingSchedulerService
from .runtime_config_store import RuntimeConfigStore
from .runtime_session_service import RuntimeSessionService


@dataclass(slots=True)
class PluginRuntimeComponents:
    runtime_state: PluginRuntimeState
    runtime_config_store: RuntimeConfigStore
    runtime_session_service: RuntimeSessionService
    polling_scheduler: PollingSchedulerService
    passive_message_handler: PassiveMessageHandler
    notice_event_handler: NoticeEventHandler
    command_handler: GlogCommandHandler


def build_plugin_runtime(
    context: Any,
    config: Any | None,
    plugin_dir: Path,
    runtime_root: Path,
) -> PluginRuntimeComponents:
    default_event_switches = _build_default_event_switches(config)
    persistence = ConfigPersistence(
        plugin_dir=plugin_dir,
        runtime_root=runtime_root,
    )
    runtime_state = PluginRuntimeState()
    runtime_config_store = RuntimeConfigStore(
        persistence,
        runtime_state,
    )
    runtime_session_service = RuntimeSessionService(
        persistence,
        runtime_state,
        runtime_token=uuid.uuid4().hex,
    )
    permissions = PermissionService(context)
    group_context_service = GroupContextService(permissions)
    bot_api = BotApiService(permissions)
    log_dispatcher = LogDispatchService(bot_api)
    message_recall_service = MessageRecallService(log_dispatcher)
    avatar_guard = AvatarGuardService(
        persistence,
        bot_api,
        log_dispatcher,
    )
    member_profile_service = MemberProfileService(
        persistence,
        bot_api,
        log_dispatcher,
    )
    group_name_guard = GroupNameGuardService(
        persistence,
        bot_api,
        log_dispatcher,
    )
    group_runtime_service = GroupRuntimeService(
        runtime_config_store,
        persistence,
        bot_api,
        avatar_guard,
        group_name_guard,
        member_profile_service,
        GroupTaskCoordinator(),
    )
    polling_scheduler = PollingSchedulerService(
        bot_api,
        runtime_state,
        runtime_session_service,
        group_runtime_service,
    )
    passive_message_handler = PassiveMessageHandler(
        runtime_state,
        group_context_service,
        message_recall_service,
        group_runtime_service,
    )
    notice_event_handler = NoticeEventHandler(
        runtime_state,
        log_dispatcher,
        message_recall_service,
        group_runtime_service,
    )
    glog_event_switch_service = GlogEventSwitchService(
        runtime_state,
        runtime_config_store,
        group_context_service,
        default_event_switches=default_event_switches,
    )
    glog_config_service = GlogConfigService(
        permissions,
        runtime_state,
        runtime_config_store,
        group_context_service,
        message_recall_service,
        glog_event_switch_service,
    )
    glog_group_service = GlogGroupService(
        runtime_state,
        group_context_service,
        group_runtime_service,
    )
    command_handler = GlogCommandHandler(
        glog_config_service,
        glog_event_switch_service,
        glog_group_service,
    )
    return PluginRuntimeComponents(
        runtime_state=runtime_state,
        runtime_config_store=runtime_config_store,
        runtime_session_service=runtime_session_service,
        polling_scheduler=polling_scheduler,
        passive_message_handler=passive_message_handler,
        notice_event_handler=notice_event_handler,
        command_handler=command_handler,
    )


def _build_default_event_switches(config: Any | None) -> dict[str, bool]:
    return {
        "bot_kick_member": _config_bool(
            config,
            "default_bot_kick_member_enabled",
            True,
        ),
        "bot_ban_member": _config_bool(
            config,
            "default_bot_ban_member_enabled",
            True,
        ),
        "bot_recall_own_message": _config_bool(
            config,
            "default_bot_recall_own_message_enabled",
            True,
        ),
        "bot_recall_other_message": _config_bool(
            config,
            "default_bot_recall_other_message_enabled",
            True,
        ),
    }


def _config_bool(config: Any | None, key: str, default: bool) -> bool:
    if config is None:
        return default
    try:
        if hasattr(config, "get"):
            return bool(config.get(key, default))
        return bool(getattr(config, key, default))
    except Exception:
        return default
