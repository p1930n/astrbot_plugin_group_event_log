import unittest

from member_profile import build_member_profile_state
from member_profile_service import MemberProfileService


class FakeMemberProfilePersistence:
    def __init__(self) -> None:
        self.member_states: dict[str, dict[str, object]] = {}

    async def load_member_profile_state(self, group_id: str) -> dict[str, object]:
        return dict(self.member_states.get(group_id, {}))

    async def save_member_profile_state(self, group_id: str, data: dict[str, object]) -> str:
        self.member_states[group_id] = dict(data)
        return f"memory://member_profile_states/{group_id}"


class FakeMemberProfileBotApi:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls: list[str] = []

    async def call_group_member_list_api(self, group_id: str) -> dict[str, object]:
        self.calls.append(group_id)
        return dict(self.result)


class FakeMemberProfileLogDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch_member_profile_logs(
        self,
        group_id: str,
        push_group_ids: list[str],
        changes,
    ) -> list[str]:
        self.calls.append(
            {
                "group_id": group_id,
                "push_group_ids": list(push_group_ids),
                "change_count": len(changes),
            }
        )
        return list(push_group_ids)


class MemberProfileServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_passive_member_profile_updates_state_and_dispatches(self) -> None:
        persistence = FakeMemberProfilePersistence()
        persistence.member_states["10001"] = build_member_profile_state("10001")
        persistence.member_states["10001"]["members"] = {
            "20001": {
                "user_id": "20001",
                "card": "old-card",
                "nickname": "tester",
                "last_seen_at": "2026-04-09T20:00:00",
            }
        }
        persistence.member_states["10001"]["member_count"] = 1
        bot_api = FakeMemberProfileBotApi({"ok": True, "data": []})
        dispatcher = FakeMemberProfileLogDispatcher()
        service = MemberProfileService(persistence, bot_api, dispatcher)

        await service.handle_passive_member_profile(
            "10001",
            "20001",
            "new-card",
            "new-card",
            ["30001"],
        )

        self.assertEqual(
            persistence.member_states["10001"]["members"]["20001"]["card"],
            "new-card",
        )
        self.assertEqual(len(dispatcher.calls), 1)
        self.assertEqual(dispatcher.calls[0]["push_group_ids"], ["30001"])

    async def test_check_group_member_profiles_updates_state_and_logs(self) -> None:
        persistence = FakeMemberProfilePersistence()
        persistence.member_states["10001"] = build_member_profile_state("10001")
        persistence.member_states["10001"]["members"] = {
            "20001": {
                "user_id": "20001",
                "card": "old-card",
                "nickname": "tester",
                "last_seen_at": "2026-04-09T20:00:00",
            }
        }
        persistence.member_states["10001"]["member_count"] = 1
        bot_api = FakeMemberProfileBotApi(
            {
                "ok": True,
                "data": [{"user_id": "20001", "card": "new-card", "nickname": "tester"}],
            }
        )
        dispatcher = FakeMemberProfileLogDispatcher()
        service = MemberProfileService(persistence, bot_api, dispatcher)

        state, changes, sent_push_groups = await service.check_group_member_profiles(
            "10001",
            "manual_snapshot",
            True,
            ["30001"],
        )

        self.assertEqual(len(changes), 1)
        self.assertEqual(sent_push_groups, ["30001"])
        self.assertEqual(state["last_update_mode"], "manual_snapshot")
        self.assertEqual(len(dispatcher.calls), 1)

    async def test_check_group_member_profiles_persists_error_state(self) -> None:
        persistence = FakeMemberProfilePersistence()
        bot_api = FakeMemberProfileBotApi(
            {
                "ok": False,
                "error": "not ready",
            }
        )
        dispatcher = FakeMemberProfileLogDispatcher()
        service = MemberProfileService(persistence, bot_api, dispatcher)

        state, changes, sent_push_groups = await service.check_group_member_profiles(
            "10001",
            "polling_snapshot",
            True,
            ["30001"],
        )

        self.assertEqual(changes, [])
        self.assertEqual(sent_push_groups, [])
        self.assertEqual(state["last_error"], "not ready")
        self.assertEqual(len(dispatcher.calls), 0)
