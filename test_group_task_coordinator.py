import unittest

from group_task_coordinator import GroupTaskCoordinator


class GroupTaskCoordinatorTests(unittest.TestCase):
    def test_same_group_and_same_scope_reuses_lock(self) -> None:
        coordinator = GroupTaskCoordinator()

        first_lock = coordinator.avatar_lock("10001")
        second_lock = coordinator.avatar_lock("10001")

        self.assertIs(first_lock, second_lock)

    def test_different_scopes_use_different_lock_pools(self) -> None:
        coordinator = GroupTaskCoordinator()

        avatar_lock = coordinator.avatar_lock("10001")
        group_name_lock = coordinator.group_name_lock("10001")
        member_profile_lock = coordinator.member_profile_lock("10001")

        self.assertIsNot(avatar_lock, group_name_lock)
        self.assertIsNot(avatar_lock, member_profile_lock)
        self.assertIsNot(group_name_lock, member_profile_lock)
