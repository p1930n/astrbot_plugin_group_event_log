import unittest
from unittest.mock import patch

from commands.glog_command_constants import MIN_POLL_INTERVAL_SECONDS
from commands.glog_command_handler import GlogCommandHandler
from commands.glog_config_service import GlogConfigService
from commands.glog_group_service import GlogGroupService
from domain.models import PluginConfig, PushGroupConfig, SourceGroupConfig
from runtime.plugin_runtime_state import PluginRuntimeState


class DummyResult:
    def __init__(self, text: str = "ok") -> None:
        self.message_text = text


class FakeEvent:
    def __init__(
        self,
        message_str: str,
        group_id: str = "10001",
        sender_id: str = "20001",
    ) -> None:
        self._message_str = message_str
        self._group_id = group_id
        self._sender_id = sender_id

    def get_message_str(self) -> str:
        return self._message_str

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id


class FakePermissionService:
    def __init__(self, is_global_admin: bool) -> None:
        self._is_global_admin = is_global_admin

    def is_global_admin(self, event) -> bool:
        return self._is_global_admin


class FakeGroupContextService:
    async def can_manage_source_group(self, event, group_id: str) -> bool:
        return True

    async def can_query_group_metadata(self, event, group_id: str) -> bool:
        return True

    def current_group_id(self, event) -> str:
        return str(event.get_group_id() or "").strip()

    def resolve_bind_args(self, event, args: list[str]) -> tuple[str, str, str]:
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


class FakeRuntimeConfigStore:
    def __init__(self, runtime_state: PluginRuntimeState) -> None:
        self._runtime_state = runtime_state
        self.save_calls = 0

    @property
    def config(self) -> PluginConfig:
        return self._runtime_state.config

    async def save(self) -> None:
        self.save_calls += 1


class FakeMessageRecallService:
    def __init__(self) -> None:
        self.cleared_groups: list[str] = []

    def clear_group_cache(self, group_id: str) -> None:
        self.cleared_groups.append(group_id)


class FakeGroupRuntimeService:
    def __init__(self) -> None:
        self.avatar_check_calls: list[str] = []
        self.member_check_calls: list[str] = []
        self.avatar_probe_calls: list[tuple[str, str]] = []
        self.avatar_status_calls: list[str] = []
        self.member_status_calls: list[str] = []
        self.rollback_calls: list[tuple[str, str, bool]] = []
        self.raise_avatar_check_error = False

    async def handle_avatar_probe(self, event, group_id: str):
        self.avatar_probe_calls.append((str(event.get_group_id() or "").strip(), group_id))
        return DummyResult("avatar probe")

    async def handle_avatar_check(self, group_id: str):
        if self.raise_avatar_check_error:
            raise RuntimeError("boom")
        self.avatar_check_calls.append(group_id)
        return DummyResult("avatar check")

    async def handle_avatar_status(self, group_id: str):
        self.avatar_status_calls.append(group_id)
        return DummyResult("avatar status")

    async def handle_member_check(self, group_id: str):
        self.member_check_calls.append(group_id)
        return DummyResult("member check")

    async def handle_member_status(self, group_id: str):
        self.member_status_calls.append(group_id)
        return DummyResult("member status")

    async def set_avatar_rollback(self, group_id: str, source_config, enabled: bool):
        self.rollback_calls.append(("avatar", group_id, enabled))
        source_config.avatar_rollback_enabled = enabled
        return DummyResult("avatar rollback")

    async def set_group_name_rollback(self, group_id: str, source_config, enabled: bool):
        self.rollback_calls.append(("group_name", group_id, enabled))
        source_config.group_name_rollback_enabled = enabled
        return DummyResult("group name rollback")


class CommandTestHarness:
    def __init__(self) -> None:
        self.runtime_state = PluginRuntimeState(config=PluginConfig())
        self.permission_service = FakePermissionService(is_global_admin=True)
        self.group_context_service = FakeGroupContextService()
        self.runtime_config_store = FakeRuntimeConfigStore(self.runtime_state)
        self.message_recall_service = FakeMessageRecallService()
        self.group_runtime_service = FakeGroupRuntimeService()

    @property
    def config(self) -> PluginConfig:
        return self.runtime_state.config

    def build_config_service(self, is_global_admin: bool = True) -> GlogConfigService:
        self.permission_service = FakePermissionService(is_global_admin=is_global_admin)
        return GlogConfigService(
            self.permission_service,
            self.runtime_state,
            self.runtime_config_store,
            self.group_context_service,
            self.message_recall_service,
        )

    def build_group_service(self) -> GlogGroupService:
        return GlogGroupService(
            self.runtime_state,
            self.group_context_service,
            self.group_runtime_service,
        )

    def build_handler(self, is_global_admin: bool = True) -> GlogCommandHandler:
        return GlogCommandHandler(
            self.build_config_service(is_global_admin=is_global_admin),
            self.build_group_service(),
        )


class GlogConfigServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_plugin_command_updates_global_switch_and_saves(self) -> None:
        harness = CommandTestHarness()
        service = harness.build_config_service(is_global_admin=True)

        await service.handle_plugin(FakeEvent("/glog plugin off"), ["off"])

        self.assertFalse(harness.config.plugin_enabled)
        self.assertEqual(harness.runtime_config_store.save_calls, 1)

    async def test_recall_off_clears_group_cache(self) -> None:
        harness = CommandTestHarness()
        harness.config.monitored_groups["10001"] = SourceGroupConfig(
            enabled=True,
            recall_message_enabled=True,
        )
        service = harness.build_config_service()

        await service.handle_recall(FakeEvent("/glog recall off", group_id="10001"), ["off"])

        self.assertFalse(harness.config.monitored_groups["10001"].recall_message_enabled)
        self.assertEqual(harness.message_recall_service.cleared_groups, ["10001"])
        self.assertEqual(harness.runtime_config_store.save_calls, 1)

    async def test_bind_command_adds_binding_only_once(self) -> None:
        harness = CommandTestHarness()
        harness.config.monitored_groups["10001"] = SourceGroupConfig(enabled=True)
        harness.config.push_groups["20001"] = PushGroupConfig(enabled=True)
        service = harness.build_config_service()
        event = FakeEvent("/glog bind 20001", group_id="10001")

        await service.handle_bind(event, ["20001"])
        await service.handle_bind(event, ["20001"])

        self.assertEqual(harness.config.monitored_groups["10001"].push_group_ids, ["20001"])
        self.assertEqual(harness.runtime_config_store.save_calls, 1)

    async def test_member_interval_uses_shared_minimum_constant(self) -> None:
        harness = CommandTestHarness()
        service = harness.build_config_service(is_global_admin=True)

        result = await service.handle_member_interval(
            FakeEvent("/glog member interval 10"),
            ["10"],
        )

        self.assertEqual(
            result.message_text,
            f"interval must be at least {MIN_POLL_INTERVAL_SECONDS} seconds",
        )


class GlogGroupServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_avatar_check_routes_to_group_runtime_service(self) -> None:
        harness = CommandTestHarness()
        service = harness.build_group_service()

        await service.handle_avatar_check(FakeEvent("/glog avatar check", group_id="10001"), [])

        self.assertEqual(harness.group_runtime_service.avatar_check_calls, ["10001"])
        self.assertEqual(harness.group_runtime_service.member_check_calls, [])

    async def test_rollback_group_name_routes_to_group_runtime_service(self) -> None:
        harness = CommandTestHarness()
        harness.config.monitored_groups["10001"] = SourceGroupConfig(enabled=True)
        service = harness.build_group_service()

        await service.handle_rollback(
            FakeEvent("/glog rollback group_name on", group_id="10001"),
            ["group_name", "on"],
        )

        self.assertEqual(
            harness.group_runtime_service.rollback_calls,
            [("group_name", "10001", True)],
        )


class GlogCommandHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_glog_routes_via_registry(self) -> None:
        harness = CommandTestHarness()
        handler = harness.build_handler()

        await handler.handle_glog(FakeEvent("/glog avatar check", group_id="10001"))

        self.assertEqual(harness.group_runtime_service.avatar_check_calls, ["10001"])

    async def test_handle_glog_catches_exceptions_and_logs(self) -> None:
        harness = CommandTestHarness()
        harness.group_runtime_service.raise_avatar_check_error = True
        handler = harness.build_handler()

        with patch("commands.glog_command_handler.logger") as logger_mock:
            result = await handler.handle_glog(
                FakeEvent("/glog avatar check", group_id="10001")
            )

        self.assertEqual(result.message_text, "command failed: avatar")
        logger_mock.error.assert_called_once()
