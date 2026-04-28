import unittest

from commands.command_context import CommandContext
from commands.group_context_service import GroupContextService


class FakeEvent:
    def __init__(self, group_id: str = "10001", sender_id: str = "20001") -> None:
        self._group_id = group_id
        self._sender_id = sender_id

    def get_group_id(self) -> str:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_message_str(self) -> str:
        return "/glog"


def command_context(event: FakeEvent) -> CommandContext:
    return CommandContext.from_event(event)


class FakePermissionService:
    def __init__(
        self,
        is_global_admin: bool = False,
        is_group_admin_or_owner: bool = False,
    ) -> None:
        self._is_global_admin = is_global_admin
        self._is_group_admin_or_owner = is_group_admin_or_owner
        self.group_admin_checks: list[tuple[str, str]] = []

    def is_global_admin(self, event) -> bool:
        return self._is_global_admin

    async def is_group_admin_or_owner(self, event, user_id: str, group_id: str) -> bool:
        self.group_admin_checks.append((user_id, group_id))
        return self._is_group_admin_or_owner


class GroupContextServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_can_manage_source_group_allows_global_admin(self) -> None:
        service = GroupContextService(FakePermissionService(is_global_admin=True))

        allowed = await service.can_manage_source_group(
            command_context(FakeEvent()),
            "99999",
        )

        self.assertTrue(allowed)

    async def test_can_manage_source_group_requires_same_group_admin(self) -> None:
        permissions = FakePermissionService(is_group_admin_or_owner=True)
        service = GroupContextService(permissions)

        allowed = await service.can_manage_source_group(
            command_context(FakeEvent(group_id="10001")),
            "10001",
        )

        self.assertTrue(allowed)
        self.assertEqual(permissions.group_admin_checks, [("20001", "10001")])

    async def test_can_query_group_metadata_rejects_cross_group_non_admin(self) -> None:
        service = GroupContextService(FakePermissionService())

        allowed = await service.can_query_group_metadata(
            command_context(FakeEvent(group_id="10001")),
            "20002",
        )

        self.assertFalse(allowed)

    def test_resolve_bind_args_uses_current_group_when_only_push_group_passed(self) -> None:
        service = GroupContextService(FakePermissionService())

        source_group_id, push_group_id, error = service.resolve_bind_args(
            command_context(FakeEvent(group_id="10001")),
            ["30001"],
        )

        self.assertEqual((source_group_id, push_group_id, error), ("10001", "30001", ""))
