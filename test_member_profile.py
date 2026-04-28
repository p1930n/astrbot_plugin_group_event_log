import unittest

from domain.member_profile import (
    apply_passive_member_profile,
    apply_polled_member_profiles,
    build_member_profile_state,
)


class PassiveMemberProfileTests(unittest.TestCase):
    def test_message_display_name_does_not_override_polled_nickname(self) -> None:
        state = build_member_profile_state("10001")
        state["members"] = {
            "20002": {
                "user_id": "20002",
                "card": "group-card",
                "nickname": "qq-nickname",
                "last_seen_at": "2026-04-09T00:00:00",
            }
        }
        state["member_count"] = 1

        state, change = apply_passive_member_profile(
            state,
            "10001",
            "20002",
            "group-card",
            "group-card",
            "passive_message",
        )

        self.assertIsNone(change)
        self.assertEqual(state["members"]["20002"]["nickname"], "qq-nickname")

    def test_missing_nickname_does_not_clear_existing_snapshot(self) -> None:
        state = build_member_profile_state("10001")
        state["members"] = {
            "20002": {
                "user_id": "20002",
                "card": "group-card",
                "nickname": "qq-nickname",
                "last_seen_at": "2026-04-09T00:00:00",
            }
        }
        state["member_count"] = 1

        state, change = apply_passive_member_profile(
            state,
            "10001",
            "20002",
            "group-card",
            None,
            "passive_message",
        )

        self.assertIsNone(change)
        self.assertEqual(state["members"]["20002"]["nickname"], "qq-nickname")

    def test_empty_card_with_display_name_alias_does_not_clear_existing_card(self) -> None:
        state = build_member_profile_state("10001")
        state["members"] = {
            "20002": {
                "user_id": "20002",
                "card": "group-card",
                "nickname": "qq-nickname",
                "last_seen_at": "2026-04-09T00:00:00",
            }
        }
        state["member_count"] = 1

        state, change = apply_passive_member_profile(
            state,
            "10001",
            "20002",
            "",
            "group-card",
            "passive_message",
        )

        self.assertIsNone(change)
        self.assertEqual(state["members"]["20002"]["card"], "group-card")
        self.assertEqual(state["members"]["20002"]["nickname"], "qq-nickname")

    def test_first_seen_user_id_placeholder_is_not_saved_as_nickname(self) -> None:
        state, change = apply_passive_member_profile(
            None,
            "10001",
            "20002",
            "",
            "20002",
            "passive_message",
        )

        self.assertIsNone(change)
        self.assertEqual(state["members"]["20002"]["nickname"], "")

    def test_existing_nickname_is_not_replaced_by_user_id_placeholder(self) -> None:
        state = build_member_profile_state("10001")
        state["members"] = {
            "20002": {
                "user_id": "20002",
                "card": "",
                "nickname": "real-nickname",
                "last_seen_at": "2026-04-09T00:00:00",
            }
        }
        state["member_count"] = 1

        state, change = apply_passive_member_profile(
            state,
            "10001",
            "20002",
            "",
            "20002",
            "passive_message",
        )

        self.assertIsNone(change)
        self.assertEqual(state["members"]["20002"]["nickname"], "real-nickname")

    def test_polling_user_id_placeholder_does_not_flip_nickname(self) -> None:
        state = build_member_profile_state("10001")
        state["members"] = {
            "20002": {
                "user_id": "20002",
                "card": "",
                "nickname": "real-nickname",
                "last_seen_at": "2026-04-09T00:00:00",
            }
        }
        state["member_count"] = 1

        state, changes = apply_polled_member_profiles(
            state,
            "10001",
            [{"user_id": "20002", "card": "", "nickname": "20002"}],
        )

        self.assertEqual(changes, [])
        self.assertEqual(state["members"]["20002"]["nickname"], "real-nickname")

    def test_real_card_change_still_emits_change(self) -> None:
        state = build_member_profile_state("10001")
        state["members"] = {
            "20002": {
                "user_id": "20002",
                "card": "old-card",
                "nickname": "qq-nickname",
                "last_seen_at": "2026-04-09T00:00:00",
            }
        }
        state["member_count"] = 1

        state, change = apply_passive_member_profile(
            state,
            "10001",
            "20002",
            "new-card",
            "new-card",
            "passive_message",
        )

        self.assertIsNotNone(change)
        self.assertEqual(change.changed_fields, ["card"])
        self.assertEqual(state["members"]["20002"]["card"], "new-card")
        self.assertEqual(state["members"]["20002"]["nickname"], "qq-nickname")

    def test_real_nickname_change_still_emits_change(self) -> None:
        state = build_member_profile_state("10001")
        state["members"] = {
            "20002": {
                "user_id": "20002",
                "card": "group-card",
                "nickname": "old-nickname",
                "last_seen_at": "2026-04-09T00:00:00",
            }
        }
        state["member_count"] = 1

        state, change = apply_passive_member_profile(
            state,
            "10001",
            "20002",
            "group-card",
            "new-nickname",
            "passive_message",
        )

        self.assertIsNotNone(change)
        self.assertEqual(change.changed_fields, ["nickname"])
        self.assertEqual(state["members"]["20002"]["nickname"], "new-nickname")


if __name__ == "__main__":
    unittest.main()
