import unittest

from models import PluginConfig, SourceGroupConfig
from plugin_runtime_state import PluginRuntimeState
from polling_scheduler import BOT_READY_RETRY_SECONDS, PollingSchedulerService


class FakePollingBotApi:
    def __init__(self, ready_sequence: list[bool]) -> None:
        self.ready_sequence = list(ready_sequence)

    async def is_bot_ready(self) -> bool:
        if self.ready_sequence:
            return self.ready_sequence.pop(0)
        return True


class FakeRuntimeSessionService:
    async def is_active_runtime(self) -> bool:
        return True


class FakeGroupRuntimeService:
    def __init__(self) -> None:
        self.avatar_calls: list[str] = []
        self.member_calls: list[str] = []

    async def run_avatar_poll_check(self, group_id: str) -> None:
        self.avatar_calls.append(group_id)

    async def run_member_profile_poll_check(self, group_id: str) -> None:
        self.member_calls.append(group_id)


class PollingSchedulerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_avatar_poll_loop_runs_enabled_avatar_groups_only(self) -> None:
        config = PluginConfig(avatar_poll_interval_seconds=99)
        config.monitored_groups["10001"] = SourceGroupConfig(enabled=True)
        config.monitored_groups["10002"] = SourceGroupConfig(enabled=False)
        disabled_avatar = SourceGroupConfig(enabled=True)
        disabled_avatar.event_switches["avatar_hash"] = False
        config.monitored_groups["10003"] = disabled_avatar

        state = PluginRuntimeState(config=config, is_ready=True, is_running=True)
        bot_api = FakePollingBotApi([True])
        runtime_session_service = FakeRuntimeSessionService()
        group_runtime_service = FakeGroupRuntimeService()
        sleep_calls: list[float] = []

        async def sleep_func(seconds: float) -> None:
            sleep_calls.append(seconds)
            if seconds == config.avatar_poll_interval_seconds:
                state.is_running = False

        service = PollingSchedulerService(
            bot_api,
            state,
            runtime_session_service,
            group_runtime_service,
            sleep_func=sleep_func,
        )

        await service.avatar_poll_loop()

        self.assertEqual(group_runtime_service.avatar_calls, ["10001"])
        self.assertEqual(group_runtime_service.member_calls, [])
        self.assertIn(1, sleep_calls)
        self.assertIn(config.avatar_poll_interval_seconds, sleep_calls)

    async def test_member_profile_poll_loop_waits_until_bot_ready(self) -> None:
        config = PluginConfig(member_profile_poll_interval_seconds=88)
        config.monitored_groups["10001"] = SourceGroupConfig(
            enabled=True,
            member_profile_polling_enabled=True,
        )
        state = PluginRuntimeState(config=config, is_ready=True, is_running=True)
        bot_api = FakePollingBotApi([False])
        runtime_session_service = FakeRuntimeSessionService()
        group_runtime_service = FakeGroupRuntimeService()
        sleep_calls: list[float] = []

        async def sleep_func(seconds: float) -> None:
            sleep_calls.append(seconds)
            state.is_running = False

        service = PollingSchedulerService(
            bot_api,
            state,
            runtime_session_service,
            group_runtime_service,
            sleep_func=sleep_func,
        )

        await service.member_profile_poll_loop()

        self.assertEqual(group_runtime_service.avatar_calls, [])
        self.assertEqual(group_runtime_service.member_calls, [])
        self.assertEqual(sleep_calls, [BOT_READY_RETRY_SECONDS])
