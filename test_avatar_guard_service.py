import unittest

from avatar_guard_models import AvatarHashStatus, AvatarVerifyRetryPolicy
from avatar_guard_service import AvatarGuardService
from avatar_hash import AvatarHashFetchResult
from models import SourceGroupConfig


class FakeAvatarPersistence:
    def __init__(self) -> None:
        self.avatar_states: dict[str, dict[str, object]] = {}
        self.baseline_images: list[tuple[str, bytes, str]] = []

    async def load_avatar_hash_state(self, group_id: str) -> dict[str, object]:
        return dict(self.avatar_states.get(group_id, {}))

    async def save_avatar_hash_state(self, group_id: str, data: dict[str, object]) -> str:
        self.avatar_states[group_id] = dict(data)
        return f"memory://avatar_hash_states/{group_id}"

    async def save_avatar_baseline_image(
        self, group_id: str, image_bytes: bytes, suffix: str
    ) -> str:
        self.baseline_images.append((group_id, image_bytes, suffix))
        return f"memory://avatar_baseline/{group_id}/baseline{suffix}"


class FakeAvatarBotApi:
    def __init__(self, rollback_ok: bool = True) -> None:
        self.rollback_ok = rollback_ok
        self.rollback_calls: list[tuple[str, str]] = []

    async def rollback_group_avatar(
        self, group_id: str, baseline_image_path: str
    ) -> tuple[bool, str]:
        self.rollback_calls.append((group_id, baseline_image_path))
        if self.rollback_ok:
            return True, ""
        return False, "rollback failed"


class FakeAvatarLogDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch_avatar_hash_logs(
        self,
        group_id: str,
        push_group_ids: list[str],
        transition,
        trigger: str,
    ) -> None:
        self.calls.append(
            {
                "group_id": group_id,
                "push_group_ids": list(push_group_ids),
                "status": transition.status,
                "trigger": trigger,
            }
        )


class SequentialAvatarFetcher:
    def __init__(self, results: list[AvatarHashFetchResult]) -> None:
        self._results = list(results)

    async def __call__(self, group_id: str) -> AvatarHashFetchResult:
        return self._results.pop(0)


async def _noop_sleep(seconds: float) -> None:
    return None


class AvatarGuardServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_group_avatar_creates_baseline(self) -> None:
        persistence = FakeAvatarPersistence()
        bot_api = FakeAvatarBotApi()
        dispatcher = FakeAvatarLogDispatcher()
        fetcher = SequentialAvatarFetcher(
            [
                AvatarHashFetchResult(
                    ok=True,
                    group_id="10001",
                    checked_at="2026-04-09T20:20:00",
                    hash_value="hash-a",
                    source_url="https://example/avatar-a",
                    byte_size=3,
                    content_type="image/png",
                    file_suffix=".png",
                    image_bytes=b"abc",
                )
            ]
        )
        service = AvatarGuardService(
            persistence,
            bot_api,
            dispatcher,
            fetch_avatar_hash=fetcher,
            sleep_func=_noop_sleep,
        )

        transition, sent_push_groups = await service.check_group_avatar(
            "10001",
            SourceGroupConfig(enabled=True),
            ["20001"],
            "manual",
            True,
        )

        self.assertTrue(transition.baseline_created)
        self.assertEqual(transition.status, AvatarHashStatus.BASELINE_CREATED)
        self.assertEqual(sent_push_groups, [])
        self.assertEqual(len(persistence.baseline_images), 1)
        self.assertEqual(
            persistence.avatar_states["10001"]["baseline_hash"],
            "hash-a",
        )

    async def test_check_group_avatar_rolls_back_and_logs(self) -> None:
        persistence = FakeAvatarPersistence()
        persistence.avatar_states["10001"] = {
            "group_id": "10001",
            "baseline_hash": "hash-old",
            "last_hash": "hash-old",
            "baseline_image_path": "memory://avatar_baseline/10001/baseline.png",
            "first_baseline_at": "2026-04-09T20:00:00",
            "change_count": 0,
        }
        bot_api = FakeAvatarBotApi(rollback_ok=True)
        dispatcher = FakeAvatarLogDispatcher()
        fetcher = SequentialAvatarFetcher(
            [
                AvatarHashFetchResult(
                    ok=True,
                    group_id="10001",
                    checked_at="2026-04-09T20:21:00",
                    hash_value="hash-new",
                    source_url="https://example/avatar-new",
                    byte_size=3,
                    content_type="image/png",
                    file_suffix=".png",
                    image_bytes=b"new",
                ),
                AvatarHashFetchResult(
                    ok=True,
                    group_id="10001",
                    checked_at="2026-04-09T20:21:02",
                    hash_value="hash-old",
                    source_url="https://example/avatar-old",
                    byte_size=3,
                    content_type="image/png",
                    file_suffix=".png",
                    image_bytes=b"old",
                ),
            ]
        )
        service = AvatarGuardService(
            persistence,
            bot_api,
            dispatcher,
            fetch_avatar_hash=fetcher,
            sleep_func=_noop_sleep,
        )
        source_config = SourceGroupConfig(
            enabled=True,
            avatar_rollback_enabled=True,
        )

        transition, sent_push_groups = await service.check_group_avatar(
            "10001",
            source_config,
            ["20001"],
            "poll",
            True,
        )

        self.assertTrue(transition.rollback_attempted)
        self.assertTrue(transition.rollback_succeeded)
        self.assertEqual(transition.status, AvatarHashStatus.ROLLBACK_SUCCESS)
        self.assertEqual(sent_push_groups, ["20001"])
        self.assertEqual(
            bot_api.rollback_calls,
            [("10001", "memory://avatar_baseline/10001/baseline.png")],
        )
        self.assertEqual(len(dispatcher.calls), 1)
        self.assertEqual(dispatcher.calls[0]["push_group_ids"], ["20001"])

    async def test_check_group_avatar_uses_retry_policy_delays(self) -> None:
        persistence = FakeAvatarPersistence()
        persistence.avatar_states["10001"] = {
            "group_id": "10001",
            "baseline_hash": "hash-old",
            "last_hash": "hash-old",
            "baseline_image_path": "memory://avatar_baseline/10001/baseline.png",
            "first_baseline_at": "2026-04-09T20:00:00",
            "change_count": 0,
        }
        bot_api = FakeAvatarBotApi(rollback_ok=True)
        dispatcher = FakeAvatarLogDispatcher()
        fetcher = SequentialAvatarFetcher(
            [
                AvatarHashFetchResult(
                    ok=True,
                    group_id="10001",
                    checked_at="2026-04-09T20:21:00",
                    hash_value="hash-new",
                    source_url="https://example/avatar-new",
                    byte_size=3,
                    content_type="image/png",
                    file_suffix=".png",
                    image_bytes=b"new",
                ),
                AvatarHashFetchResult(
                    ok=False,
                    group_id="10001",
                    checked_at="2026-04-09T20:21:01",
                    error="retry-1",
                ),
                AvatarHashFetchResult(
                    ok=False,
                    group_id="10001",
                    checked_at="2026-04-09T20:21:03",
                    error="retry-2",
                ),
                AvatarHashFetchResult(
                    ok=True,
                    group_id="10001",
                    checked_at="2026-04-09T20:21:07",
                    hash_value="hash-old",
                    source_url="https://example/avatar-old",
                    byte_size=3,
                    content_type="image/png",
                    file_suffix=".png",
                    image_bytes=b"old",
                ),
            ]
        )
        sleep_calls: list[float] = []

        async def record_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        service = AvatarGuardService(
            persistence,
            bot_api,
            dispatcher,
            fetch_avatar_hash=fetcher,
            sleep_func=record_sleep,
            retry_policy=AvatarVerifyRetryPolicy(delays_seconds=(1.0, 2.0, 4.0)),
        )
        source_config = SourceGroupConfig(
            enabled=True,
            avatar_rollback_enabled=True,
        )

        transition, _ = await service.check_group_avatar(
            "10001",
            source_config,
            ["20001"],
            "poll",
            True,
        )

        self.assertEqual(sleep_calls, [1.0, 2.0, 4.0])
        self.assertEqual(transition.status, AvatarHashStatus.ROLLBACK_SUCCESS)
