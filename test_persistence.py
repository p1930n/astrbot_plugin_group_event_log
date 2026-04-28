import asyncio
import json
import sqlite3
import shutil
import time
import unittest
from pathlib import Path

from storage.persistence import ConfigPersistence, PLUGIN_DATA_DIR_NAME
from storage.sqlite_repository import SQLiteStateRepository


class ConfigPersistenceMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.workspace_root = Path(__file__).parent / "test_workspace"
        self.plugin_dir = self.workspace_root / "plugin_source"
        self.runtime_root = self.workspace_root / "runtime_root"
        self.legacy_data_dir = self.plugin_dir / "data"
        self.runtime_data_dir = self.runtime_root / "data" / PLUGIN_DATA_DIR_NAME
        self._reset_workspace()
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)

    async def asyncTearDown(self) -> None:
        self._reset_workspace()

    async def test_legacy_json_state_is_migrated_into_runtime_sqlite(self) -> None:
        self._write_json(
            "config.json",
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
            "avatar_hash/10001.json",
            {
                "group_id": "10001",
                "baseline_hash": "abc",
                "last_checked_at": "2026-04-09T12:01:00",
            },
        )
        self._write_json(
            "group_name_guard/10001.json",
            {
                "group_id": "10001",
                "baseline_name": "group-name",
            },
        )
        self._write_json(
            "member_profile/10001.json",
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
        self._write_json(
            "avatar_probe/10001.json",
            {
                "group_id": "10001",
                "saved_at": "2026-04-09T12:03:00",
            },
        )
        runtime_owner_path = self.legacy_data_dir / "runtime_owner.txt"
        runtime_owner_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_owner_path.write_text("runtime-token", encoding="utf-8")

        persistence = ConfigPersistence(self.plugin_dir, self.runtime_root)

        config = await persistence.load_config()
        avatar_state = await persistence.load_avatar_hash_state("10001")
        group_name_state = await persistence.load_group_name_guard("10001")
        member_state = await persistence.load_member_profile_state("10001")
        probe_record = await persistence.load_avatar_probe("10001")
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
        self.assertEqual(probe_record["group_id"], "10001")
        self.assertEqual(runtime_owner, "runtime-token")
        self.assertEqual(
            Path(persistence.database_path),
            self.runtime_data_dir / "state.sqlite3",
        )
        self.assertTrue(Path(persistence.database_path).exists())
        self.assertEqual(
            Path(persistence.avatar_probe_path("10001")),
            self.runtime_data_dir / "avatar_probe" / "10001.json",
        )
        self.assertTrue(Path(persistence.avatar_probe_path("10001")).exists())

    async def test_sqlite_round_trip_works_without_legacy_files(self) -> None:
        persistence = ConfigPersistence(self.plugin_dir, self.runtime_root)

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

        probe_path = await persistence.save_avatar_probe(
            "10001",
            {"group_id": "10001", "saved_at": "2026-04-09T12:10:00"},
        )

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
        self.assertEqual(
            Path(probe_path),
            self.runtime_data_dir / "avatar_probe" / "10001.json",
        )
        self.assertEqual(
            Path(persistence.database_path),
            self.runtime_data_dir / "state.sqlite3",
        )

    async def test_async_sqlite_init_supports_concurrent_access_and_preserves_wal(self) -> None:
        persistence = ConfigPersistence(self.plugin_dir, self.runtime_root)

        async def write_and_load(group_id: str) -> dict[str, object]:
            await persistence.save_avatar_hash_state(
                group_id,
                {
                    "group_id": group_id,
                    "baseline_hash": f"hash-{group_id}",
                },
            )
            return await persistence.load_avatar_hash_state(group_id)

        results = await asyncio.gather(
            write_and_load("10001"),
            write_and_load("10002"),
            write_and_load("10003"),
        )

        self.assertEqual(
            [result["baseline_hash"] for result in results],
            ["hash-10001", "hash-10002", "hash-10003"],
        )

        connection = sqlite3.connect(persistence.database_path)
        try:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(str(journal_mode).lower(), "wal")

    async def test_legacy_sqlite_store_is_copied_and_baseline_paths_are_rewritten(self) -> None:
        legacy_repository = SQLiteStateRepository(self.legacy_data_dir)
        legacy_baseline_path = self.legacy_data_dir / "avatar_baseline" / "10001" / "baseline.png"
        legacy_baseline_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_baseline_path.write_bytes(b"baseline")

        await legacy_repository.save_config({"plugin_enabled": False})
        await legacy_repository.save_avatar_hash_state(
            "10001",
            {
                "group_id": "10001",
                "baseline_hash": "legacy-hash",
                "baseline_image_path": str(legacy_baseline_path),
            },
        )
        await legacy_repository.save_runtime_owner("legacy-runtime")

        persistence = ConfigPersistence(self.plugin_dir, self.runtime_root)

        self.assertEqual(await persistence.load_config(), {"plugin_enabled": False})
        self.assertEqual(await persistence.load_runtime_owner(), "legacy-runtime")
        self.assertEqual(
            (await persistence.load_avatar_hash_state("10001"))["baseline_hash"],
            "legacy-hash",
        )
        self.assertEqual(
            (await persistence.load_avatar_hash_state("10001"))["baseline_image_path"],
            str(self.runtime_data_dir / "avatar_baseline" / "10001" / "baseline.png"),
        )
        self.assertTrue((self.runtime_data_dir / "state.sqlite3").exists())
        self.assertTrue(
            (self.runtime_data_dir / "avatar_baseline" / "10001" / "baseline.png").exists()
        )

    def _write_json(self, relative_path: str, payload: dict[str, object]) -> None:
        file_path = self.legacy_data_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _reset_workspace(self) -> None:
        if self.workspace_root.exists():
            last_error: PermissionError | None = None
            for _ in range(10):
                try:
                    shutil.rmtree(self.workspace_root)
                    return
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.05)
            if last_error is not None:
                raise last_error
