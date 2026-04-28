import shutil
import unittest
from pathlib import Path

from domain.avatar_guard_models import AvatarRollbackFailureReason
from services.bot_api_service import BotApiService


class FakePermissionService:
    def __init__(self, bot) -> None:
        self._bot = bot

    def get_bot_from_event(self, event):
        return self._bot

    async def get_bot_instance(self):
        return self._bot


class FakeBotApi:
    def __init__(self, accepted_file: str | None = None) -> None:
        self.accepted_file = accepted_file
        self.calls: list[dict[str, object]] = []

    async def call_action(self, action: str, **kwargs):
        self.calls.append({"action": action, **kwargs})
        if action != "set_group_portrait":
            return {}
        if self.accepted_file is not None and kwargs.get("file") == self.accepted_file:
            return {"ok": True}
        raise RuntimeError(f"rejected: {kwargs.get('file')}")


class FakeBot:
    def __init__(self, api) -> None:
        self.api = api


class BotApiServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.workspace_root = Path(__file__).parent / "test_bot_api_service_workspace"
        self._reset_workspace()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    async def asyncTearDown(self) -> None:
        self._reset_workspace()

    async def test_rollback_group_avatar_reports_missing_path(self) -> None:
        service = BotApiService(FakePermissionService(FakeBot(FakeBotApi())))

        result = await service.rollback_group_avatar("10001", "")

        self.assertFalse(result.success)
        self.assertEqual(result.failure_reason, AvatarRollbackFailureReason.PATH_MISSING)

    async def test_rollback_group_avatar_reports_unreadable_local_path(self) -> None:
        service = BotApiService(FakePermissionService(FakeBot(FakeBotApi())))
        missing_path = str(self.workspace_root / "astrbot-missing-baseline.png")

        result = await service.rollback_group_avatar("10001", missing_path)

        self.assertFalse(result.success)
        self.assertEqual(result.failure_reason, AvatarRollbackFailureReason.PATH_UNREADABLE)
        self.assertIn("not found", result.error)

    async def test_rollback_group_avatar_tracks_applied_input(self) -> None:
        baseline_path = self.workspace_root / "success" / "baseline.png"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_bytes(b"baseline")
        accepted_file = baseline_path.as_uri()
        api = FakeBotApi(accepted_file=accepted_file)
        service = BotApiService(FakePermissionService(FakeBot(api)))

        result = await service.rollback_group_avatar("10001", str(baseline_path))

        self.assertTrue(result.success)
        self.assertEqual(result.applied_input, accepted_file)
        self.assertIn(str(baseline_path), result.attempted_inputs)
        self.assertIn(accepted_file, result.attempted_inputs)

    async def test_rollback_group_avatar_reports_api_rejected(self) -> None:
        baseline_path = self.workspace_root / "rejected" / "baseline.png"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_bytes(b"baseline")
        service = BotApiService(FakePermissionService(FakeBot(FakeBotApi())))

        result = await service.rollback_group_avatar("10001", str(baseline_path))

        self.assertFalse(result.success)
        self.assertEqual(result.failure_reason, AvatarRollbackFailureReason.API_REJECTED)
        self.assertIn("rejected:", result.error)

    def _reset_workspace(self) -> None:
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)
