from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AvatarHashStatus(str, Enum):
    FETCH_FAILED = "fetch_failed"
    UNCHANGED = "unchanged"
    BASELINE_CREATED = "baseline_created"
    CHANGED = "changed"
    CHANGED_ADOPTED = "changed_adopted"
    ROLLBACK_SUCCESS = "rollback_success"
    ROLLBACK_SUCCESS_UNVERIFIED = "rollback_success_unverified"
    ROLLBACK_FAILED = "rollback_failed"

    def __str__(self) -> str:
        return self.value


class AvatarRollbackResult(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AvatarVerifyRetryPolicy:
    delays_seconds: tuple[float, ...] = (2.0, 4.0, 8.0, 16.0)

    def __post_init__(self) -> None:
        if not self.delays_seconds:
            raise ValueError("avatar verify retry policy must contain at least one delay")
        if any(delay <= 0 for delay in self.delays_seconds):
            raise ValueError("avatar verify retry delays must be positive")


DEFAULT_AVATAR_VERIFY_RETRY_POLICY = AvatarVerifyRetryPolicy()
