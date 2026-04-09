import json
import unittest
from pathlib import Path

from persistence import ConfigPersistence


class ConfigPersistenceMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.plugin_dir = Path(__file__).parent / "test_workspace"
        self._reset_workspace()

    async def asyncTearDown(self) -> None:
        self._reset_workspace()

    async def test_legacy_json_state_is_migrated_into_sqlite(self) -> None:
        self._write_json(
            "data/config.json",
            {
                "plugin_enabled": True,
                "debug_raw_notice": False,
                "avatar_poll_interval_seconds": 300,
                "member_profile_poll_interval_seconds": 60,
                "monitored_groups": {
                    "10001": {
                        "enabled": True,
                        "push_group_ids": ["20001"],
                        "avatar_rollback_enabled": True,
                        "group_name_rollback_enabled": False,
                        "member_profile_polling_enabled": True,
                        "recall_message_enabled": True,
                        "event_switches": {
                            "group_recall": True,
                            "avatar_hash": True,
                        },
                    }
                },
                "push_groups": {
                    "20001": {
                        "enabled": True,
                        "label": "push",
                    }
                },
                "last_updated": "2026-04-09T12:00:00",
            },
        )
        self._write_json(
            "data/avatar_hash/10001.json",
            {
                "group_id": "10001",
                "baseline_hash": "abc",
                "last_checked_at": "2026-04-09T12:01:00",
            },
        )
        self._write_json(
            "data/group_name_guard/10001.json",
            {
                "group_id": "10001",
                "baseline_name": "group-name",
            },
        )
        self._write_json(
            "data/member_profile/10001.json",
            {
                "group_id": "10001",
                "members": {
                    "30001": {
                        "user_id": "30001",
                        "card": "",
                        "nickname": "tester",
                        "last_seen_at": "2026-04-09T12:02:00",
                    }
                },
            },
        )
        runtime_owner_path = self.plugin_dir / "data" / "runtime_owner.txt"
        runtime_owner_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_owner_path.write_text("runtime-token", encoding="utf-8")

        persistence = ConfigPersistence(self.plugin_dir)

        config = await persistence.load_config()
        avatar_state = await persistence.load_avatar_hash_state("10001")
        group_name_state = await persistence.load_group_name_guard("10001")
        member_state = await persistence.load_member_profile_state("10001")
        runtime_owner = await persistence.load_runtime_owner()

        self.assertTrue(config["plugin_enabled"])
        self.assertEqual(
            config["monitored_groups"]["10001"]["push_group_ids"],
            ["20001"],
        )
        self.assertEqual(avatar_state["baseline_hash"], "abc")
        self.assertEqual(group_name_state["baseline_name"], "group-name")
        self.assertEqual(
            member_state["members"]["30001"]["nickname"],
            "tester",
        )
        self.assertEqual(runtime_owner, "runtime-token")
        self.assertTrue(Path(persistence.database_path).exists())

    async def test_sqlite_round_trip_works_without_legacy_files(self) -> None:
        persistence = ConfigPersistence(self.plugin_dir)

        await persistence.save_config({"plugin_enabled": False})
        await persistence.save_avatar_hash_state(
            "10001",
            {
                "group_id": "10001",
                "baseline_hash": "next",
            },
        )
        await persistence.save_group_name_guard(
            "10001",
            {
                "group_id": "10001",
                "baseline_name": "stable-name",
            },
        )
        await persistence.save_member_profile_state(
            "10001",
            {
                "group_id": "10001",
                "members": {},
            },
        )
        await persistence.save_runtime_owner("active-runtime")

        self.assertEqual(
            await persistence.load_config(),
            {"plugin_enabled": False},
        )
        self.assertEqual(
            (await persistence.load_avatar_hash_state("10001"))["baseline_hash"],
            "next",
        )
        self.assertEqual(
            (await persistence.load_group_name_guard("10001"))["baseline_name"],
            "stable-name",
        )
        self.assertEqual(
            (await persistence.load_member_profile_state("10001"))["group_id"],
            "10001",
        )
        self.assertEqual(await persistence.load_runtime_owner(), "active-runtime")

    def _write_json(self, relative_path: str, payload: dict[str, object]) -> None:
        file_path = self.plugin_dir / relative_path
        file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _reset_workspace(self) -> None:
        self._clear_directory(self.plugin_dir / "data")
        self._clear_directory(self.plugin_dir / "data" / "avatar_hash")
        self._clear_directory(self.plugin_dir / "data" / "group_name_guard")
        self._clear_directory(self.plugin_dir / "data" / "member_profile")

    def _clear_directory(self, directory_path: Path) -> None:
        for file_path in directory_path.iterdir():
            if file_path.name == ".gitkeep":
                continue
            if file_path.is_file():
                file_path.unlink()
