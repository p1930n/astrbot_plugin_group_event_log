import unittest

from runtime.group_runtime_summary import (
    build_avatar_status_summary,
    build_member_check_summary,
    build_member_status_summary,
)


class GroupRuntimeSummaryTests(unittest.TestCase):
    def test_avatar_status_summary_reports_missing_state(self) -> None:
        lines = build_avatar_status_summary(
            "10001",
            {},
            {},
            {},
            "data/state.sqlite3",
            "data/avatar_probe/10001.json",
        )

        self.assertEqual(lines, ["no avatar or group-name data found for group 10001"])

    def test_avatar_status_summary_includes_state_paths_and_sections(self) -> None:
        lines = build_avatar_status_summary(
            "10001",
            {
                "group_id": "10001",
                "last_checked_at": "2026-04-28T20:00:00",
                "baseline_hash": "abcdef1234567890",
            },
            {
                "group_id": "10001",
                "collected_at": "2026-04-28T20:00:01",
                "get_group_info": {"ok": True, "top_level_keys": [], "candidate_fields": []},
                "get_group_info_ex": {
                    "ok": True,
                    "top_level_keys": [],
                    "candidate_fields": [],
                },
            },
            {
                "group_id": "10001",
                "baseline_name": "group",
                "last_observed_name": "group",
            },
            "data/state.sqlite3",
            "data/avatar_probe/10001.json",
        )

        self.assertIn("hash_state_db_path: data/state.sqlite3", lines)
        self.assertIn("hash_state_record_key: avatar_hash_states/10001", lines)
        self.assertIn("group_name_state_db_path: data/state.sqlite3", lines)
        self.assertIn(
            "group_name_state_record_key: group_name_guard_states/10001",
            lines,
        )
        self.assertIn("probe_snapshot_path: data/avatar_probe/10001.json", lines)
        self.assertEqual(lines.count("----"), 2)

    def test_member_status_summary_reports_missing_state(self) -> None:
        lines = build_member_status_summary("10001", {}, "data/state.sqlite3")

        self.assertEqual(lines, ["no member profile snapshot found for group 10001"])

    def test_member_check_summary_keeps_change_and_log_lines(self) -> None:
        lines = build_member_check_summary(
            "10001",
            {
                "group_id": "10001",
                "member_count": 3,
                "change_count": 2,
                "last_scan_at": "2026-04-28T20:00:00",
                "last_update_mode": "manual_snapshot",
                "last_error": "",
            },
            [],
            ["20001", "20002"],
            "data/state.sqlite3",
        )

        self.assertIn("detected_changes: 0", lines)
        self.assertIn("logs_sent_to: 20001, 20002", lines)
        self.assertIn("member_profile_state_db_path: data/state.sqlite3", lines)
        self.assertIn("member_profile_state_record_key: member_profile_states/10001", lines)


if __name__ == "__main__":
    unittest.main()
