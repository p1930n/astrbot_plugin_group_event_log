from __future__ import annotations

import asyncio


class GroupTaskCoordinator:
    """统一托管按群粒度的运行时锁。"""

    def __init__(self) -> None:
        self._avatar_group_locks: dict[str, asyncio.Lock] = {}
        self._group_name_locks: dict[str, asyncio.Lock] = {}
        self._member_profile_locks: dict[str, asyncio.Lock] = {}

    def avatar_lock(self, group_id: str) -> asyncio.Lock:
        return self._get_lock(self._avatar_group_locks, group_id)

    def group_name_lock(self, group_id: str) -> asyncio.Lock:
        return self._get_lock(self._group_name_locks, group_id)

    def member_profile_lock(self, group_id: str) -> asyncio.Lock:
        return self._get_lock(self._member_profile_locks, group_id)

    def _get_lock(
        self,
        lock_store: dict[str, asyncio.Lock],
        group_id: str,
    ) -> asyncio.Lock:
        if group_id not in lock_store:
            lock_store[group_id] = asyncio.Lock()
        return lock_store[group_id]
