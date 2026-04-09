import unittest

from models import PluginConfig, SourceGroupConfig
from polling_scheduler import BOT_READY_RETRY_SECONDS, PollingSchedulerService


class FakePollingBotApi:
    def __init__(self, ready_sequence: list[bool]) -> None:
        self.ready_sequence = list(ready_sequence)

    async def is_bot_ready(self) -> bool:
        if self.ready_sequence:
            return self.ready_sequence.pop(0)
        return True


class MutableRuntimeState:
    def __init__(self, config: PluginConfig) -> None:
        self.config = config
        self.running = True
        self.plugin_ready = True


class PollingSchedulerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_avatar_poll_loop_runs_enabled_avatar_groups_only(self) -> None:
        config = PluginConfig(avatar_poll_interval_seconds=99)
        config.monitored_groups["10001"] = SourceGroupConfig(enabled=True)
        config.monitored_groups["10002"] = SourceGroupConfig(enabled=False)
        disabled_avatar = SourceGroupConfig(enabled=True)
        disabled_avatar.event_switches["avatar_hash"] = False
        config.monitored_groups["10003"] = disabled_avatar

        state = MutableRuntimeState(config)
        bot_api = FakePollingBotApi([True])
        checked_groups: list[str] = []
        sleep_calls: list[float] = []

        async def is_active_runtime() -> bool:
            return True

        async def run_avatar_check(group_id: str) -> None:
            checked_groups.append(group_id)

        async def run_member_profile_check(group_id: str) -> None:
            raise AssertionError("member profile callback should not run")

        async def sleep_func(seconds: float) -> None:
            sleep_calls.append(seconds)
            if seconds == config.avatar_poll_interval_seconds:
                state.running = False

        service = PollingSchedulerService(
            bot_api,
            is_active_runtime,
            lambda: state.plugin_ready,
            lambda: state.running,
            lambda: state.config,
            run_avatar_check,
            run_member_profile_check,
            sleep_func=sleep_func,
        )

        await service.avatar_poll_loop()

        self.assertEqual(checked_groups, ["10001"])
        self.assertIn(1, sleep_calls)
        self.assertIn(config.avatar_poll_interval_seconds, sleep_calls)

    async def test_member_profile_poll_loop_waits_until_bot_ready(self) -> None:
        config = PluginConfig(member_profile_poll_interval_seconds=88)
        config.monitored_groups["10001"] = SourceGroupConfig(
            enabled=True,
            member_profile_polling_enabled=True,
        )
        state = MutableRuntimeState(config)
        bot_api = FakePollingBotApi([False])
        checked_groups: list[str] = []
        sleep_calls: list[float] = []

        async def is_active_runtime() -> bool:
            return True

        async def run_avatar_check(group_id: str) -> None:
            raise AssertionError("avatar callback should not run")

        async def run_member_profile_check(group_id: str) -> None:
            checked_groups.append(group_id)

        async def sleep_func(seconds: float) -> None:
            sleep_calls.append(seconds)
            state.running = False

        service = PollingSchedulerService(
            bot_api,
            is_active_runtime,
            lambda: state.plugin_ready,
            lambda: state.running,
            lambda: state.config,
            run_avatar_check,
            run_member_profile_check,
            sleep_func=sleep_func,
        )

        await service.member_profile_poll_loop()

        self.assertEqual(checked_groups, [])
        self.assertEqual(sleep_calls, [BOT_READY_RETRY_SECONDS])
