import unittest
from types import SimpleNamespace

from services.bot_api_service import BotApiService
from services.group_name_guard_service import GroupNameGuardService
from services.log_dispatch_service import LogDispatchService
from domain.member_profile import MemberProfileChange
from domain.notice_adapter import GroupNoticeEvent


class FakePermissionService:
    def __init__(self, event_bot=None, fallback_bot=None) -> None:
        self._event_bot = event_bot
        self._fallback_bot = fallback_bot

    def get_bot_from_event(self, event):
        return self._event_bot

    async def get_bot_instance(self):
        return self._fallback_bot


class FakeBotApi:
    def __init__(
        self,
        fail_no_cache: bool = False,
        group_info_payload=None,
        set_group_name_error: str = "",
    ) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._fail_no_cache = fail_no_cache
        self._group_info_payload = group_info_payload or {"group_name": "stable-name"}
        self._set_group_name_error = set_group_name_error
        self.fail_login_info = False

    async def call_action(self, action: str, **kwargs):
        self.calls.append((action, dict(kwargs)))
        if action == "get_login_info" and self.fail_login_info:
            raise RuntimeError("not ready")
        if action == "get_login_info":
            return {"user_id": 1}
        if action == "get_group_member_list" and kwargs.get("no_cache") and self._fail_no_cache:
            raise RuntimeError("no_cache unsupported")
        if action == "get_group_member_list":
            return [{"user_id": "1", "card": "", "nickname": "tester"}]
        if action == "get_group_info":
            return self._group_info_payload
        if action == "set_group_name" and self._set_group_name_error:
            raise RuntimeError(self._set_group_name_error)
        if action == "send_group_msg":
            return {"ok": True}
        return {"ok": True}


class FakeGroupNameBotApi:
    def __init__(self, current_name: str = "baseline-name", set_name_ok: bool = True) -> None:
        self.current_name = current_name
        self.set_name_ok = set_name_ok
        self.set_name_calls: list[tuple[str, str]] = []

    async def get_current_group_name(self, group_id: str) -> tuple[str, str]:
        return self.current_name, ""

    async def set_group_name(self, group_id: str, group_name: str) -> tuple[bool, str]:
        self.set_name_calls.append((group_id, group_name))
        if self.set_name_ok:
            return True, ""
        return False, "set failed"


class FakePersistence:
    def __init__(self) -> None:
        self.group_name_states: dict[str, dict[str, object]] = {}

    async def load_group_name_guard(self, group_id: str) -> dict[str, object]:
        return dict(self.group_name_states.get(group_id, {}))

    async def save_group_name_guard(self, group_id: str, data: dict[str, object]) -> str:
        self.group_name_states[group_id] = dict(data)
        return f"memory://group_name_guard/{group_id}"


class FakeGroupNameLogDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch_group_name_rollback_logs(
        self,
        group_id: str,
        push_group_ids: list[str],
        observed_name: str,
        baseline_name: str,
        rollback_result: str,
        error: str = "",
    ) -> None:
        self.calls.append(
            {
                "group_id": group_id,
                "push_group_ids": list(push_group_ids),
                "observed_name": observed_name,
                "baseline_name": baseline_name,
                "rollback_result": rollback_result,
                "error": error,
            }
        )


class BotApiServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_bot_prefers_event_bot(self) -> None:
        event_bot = SimpleNamespace(api=FakeBotApi())
        fallback_bot = SimpleNamespace(api=FakeBotApi())
        service = BotApiService(FakePermissionService(event_bot, fallback_bot))

        bot = await service.get_bot(object())

        self.assertIs(bot, event_bot)

    async def test_call_group_member_list_api_falls_back_without_no_cache(self) -> None:
        bot = SimpleNamespace(api=FakeBotApi(fail_no_cache=True))
        service = BotApiService(FakePermissionService(None, bot))

        result = await service.call_group_member_list_api("10001")

        self.assertTrue(result["ok"])
        self.assertEqual(len(bot.api.calls), 2)
        self.assertEqual(bot.api.calls[0][0], "get_group_member_list")
        self.assertTrue(bot.api.calls[0][1]["no_cache"])
        self.assertEqual(bot.api.calls[1][0], "get_group_member_list")
        self.assertNotIn("no_cache", bot.api.calls[1][1])

    async def test_group_member_list_result_exposes_fallback_state(self) -> None:
        bot = SimpleNamespace(api=FakeBotApi(fail_no_cache=True))
        service = BotApiService(FakePermissionService(None, bot))

        result = await service.get_group_member_list_result("10001")

        self.assertTrue(result.ok)
        self.assertFalse(result.used_no_cache)
        self.assertTrue(result.fallback_used)
        self.assertEqual(
            result.payload,
            [{"user_id": "1", "card": "", "nickname": "tester"}],
        )

    async def test_group_info_result_normalizes_group_name(self) -> None:
        bot = SimpleNamespace(
            api=FakeBotApi(group_info_payload={"group_name": "  name  "})
        )
        service = BotApiService(FakePermissionService(None, bot))

        result = await service.get_group_info_result("10001")

        self.assertTrue(result.ok)
        self.assertEqual(result.group_name, "name")

    async def test_set_group_name_result_masks_sensitive_error(self) -> None:
        bot = SimpleNamespace(api=FakeBotApi(set_group_name_error="token=secret leaked"))
        service = BotApiService(FakePermissionService(None, bot))

        result = await service.set_group_name_result("10001", "stable-name")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "set_group_name failed")

    async def test_is_bot_ready_returns_true_when_login_info_succeeds(self) -> None:
        bot = SimpleNamespace(api=FakeBotApi())
        service = BotApiService(FakePermissionService(None, bot))

        ready = await service.is_bot_ready()

        self.assertTrue(ready)

    async def test_is_bot_ready_returns_false_when_login_info_fails(self) -> None:
        api = FakeBotApi()
        api.fail_login_info = True
        bot = SimpleNamespace(api=api)
        service = BotApiService(FakePermissionService(None, bot))

        ready = await service.is_bot_ready()

        self.assertFalse(ready)


class LogDispatchServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_member_profile_logs_sends_to_all_targets(self) -> None:
        bot = SimpleNamespace(api=FakeBotApi())
        bot_service = BotApiService(FakePermissionService(None, bot))
        service = LogDispatchService(bot_service)
        changes = [
            MemberProfileChange(
                group_id="10001",
                user_id="20001",
                detection_mode="passive_message",
                observed_at="2026-04-09T20:00:00",
                old_card="old-card",
                new_card="new-card",
                old_nickname="old-name",
                new_nickname="old-name",
            )
        ]

        sent_targets = await service.dispatch_member_profile_logs(
            "10001",
            ["30001", "30002"],
            changes,
        )

        send_calls = [call for call in bot.api.calls if call[0] == "send_group_msg"]
        self.assertEqual(sent_targets, ["30001", "30002"])
        self.assertEqual(len(send_calls), 2)
        self.assertEqual(send_calls[0][1]["group_id"], 30001)
        self.assertEqual(send_calls[1][1]["group_id"], 30002)


class GroupNameGuardServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_baseline_saves_state(self) -> None:
        persistence = FakePersistence()
        bot_api = FakeGroupNameBotApi(current_name="stable-name")
        dispatcher = FakeGroupNameLogDispatcher()
        service = GroupNameGuardService(persistence, bot_api, dispatcher)

        success, baseline_name, error = await service.refresh_baseline("10001")

        self.assertTrue(success)
        self.assertEqual(baseline_name, "stable-name")
        self.assertEqual(error, "")
        self.assertEqual(
            persistence.group_name_states["10001"]["baseline_name"],
            "stable-name",
        )

    async def test_handle_rollback_restores_changed_name_and_logs(self) -> None:
        persistence = FakePersistence()
        persistence.group_name_states["10001"] = {
            "group_id": "10001",
            "baseline_name": "stable-name",
            "last_observed_name": "stable-name",
            "change_count": 0,
            "last_error": "",
        }
        bot_api = FakeGroupNameBotApi(current_name="stable-name")
        dispatcher = FakeGroupNameLogDispatcher()
        service = GroupNameGuardService(persistence, bot_api, dispatcher)
        notice = GroupNoticeEvent(
            event_key="notify.group_name",
            notice_type="notify",
            sub_type="group_name",
            group_id="10001",
            details={"name_new": "mutated-name"},
        )

        await service.handle_rollback(notice, ["20001"])

        self.assertEqual(bot_api.set_name_calls, [("10001", "stable-name")])
        self.assertEqual(
            persistence.group_name_states["10001"]["last_rollback_result"],
            "success",
        )
        self.assertEqual(len(dispatcher.calls), 1)
        self.assertEqual(dispatcher.calls[0]["push_group_ids"], ["20001"])
