from __future__ import annotations

import hashlib
import importlib
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    from .avatar_guard_models import AvatarHashStatus
except ImportError:
    from domain.avatar_guard_models import AvatarHashStatus


AVATAR_FETCH_USER_AGENT = "AstrBot-GroupEventLog/1.0"
AVATAR_FETCH_REQUEST_HEADERS = {
    "User-Agent": AVATAR_FETCH_USER_AGENT,
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@dataclass(slots=True)
class AvatarHashFetchResult:
    ok: bool
    group_id: str
    checked_at: str
    hash_value: str = ""
    source_url: str = ""
    byte_size: int = 0
    content_type: str = ""
    file_suffix: str = ".img"
    image_bytes: bytes = b""
    error: str = ""


@dataclass(slots=True)
class AvatarHashTransition:
    group_id: str
    status: AvatarHashStatus
    checked_at: str
    state: dict[str, Any]
    changed: bool = False
    baseline_created: bool = False
    adopted_new_baseline: bool = False
    rollback_enabled: bool = False
    rollback_attempted: bool = False
    rollback_succeeded: bool = False
    observed_hash: str = ""
    baseline_hash: str = ""
    previous_hash: str = ""
    source_url: str = ""
    byte_size: int = 0
    content_type: str = ""
    baseline_image_path: str = ""
    error: str = ""
    rollback_error: str = ""
    rollback_failure_reason: str = ""
    rollback_applied_input: str = ""
    rollback_attempted_inputs: tuple[str, ...] = ()


async def fetch_group_avatar_hash(
    group_id: str, timeout_seconds: int = 12
) -> AvatarHashFetchResult:
    checked_at = datetime.now().isoformat(timespec="seconds")
    try:
        async with _create_avatar_http_session(timeout_seconds) as session:
            return await _fetch_group_avatar_hash_with_session(
                group_id=group_id,
                checked_at=checked_at,
                session=session,
            )
    except Exception as exc:
        return AvatarHashFetchResult(
            ok=False,
            group_id=group_id,
            checked_at=checked_at,
            error=_format_avatar_fetch_error(exc),
        )


def apply_avatar_hash_result(
    group_id: str,
    previous_state: dict[str, Any] | None,
    fetch_result: AvatarHashFetchResult,
    protect_baseline: bool,
) -> AvatarHashTransition:
    previous_state = previous_state or {}
    next_state = dict(previous_state)
    next_state["group_id"] = group_id
    next_state["storage_mode"] = "baseline_hash_plus_single_image"
    next_state["last_checked_at"] = fetch_result.checked_at

    if not fetch_result.ok:
        next_state["last_fetch_ok"] = False
        next_state["last_error"] = fetch_result.error
        return AvatarHashTransition(
            group_id=group_id,
            status=AvatarHashStatus.FETCH_FAILED,
            checked_at=fetch_result.checked_at,
            state=next_state,
            error=fetch_result.error,
            rollback_enabled=protect_baseline,
        )

    baseline_hash = str(
        previous_state.get("baseline_hash") or previous_state.get("last_hash") or ""
    ).strip()

    next_state["last_fetch_ok"] = True
    next_state["last_error"] = ""
    next_state["last_observed_hash"] = fetch_result.hash_value
    next_state["last_observed_source_url"] = fetch_result.source_url
    next_state["last_observed_byte_size"] = fetch_result.byte_size
    next_state["last_observed_content_type"] = fetch_result.content_type
    next_state["first_baseline_at"] = str(
        previous_state.get("first_baseline_at", "") or fetch_result.checked_at
    )
    next_state["change_count"] = int(previous_state.get("change_count", 0) or 0)

    transition = AvatarHashTransition(
        group_id=group_id,
        status=AvatarHashStatus.UNCHANGED,
        checked_at=fetch_result.checked_at,
        state=next_state,
        observed_hash=fetch_result.hash_value,
        baseline_hash=baseline_hash,
        previous_hash=baseline_hash,
        source_url=fetch_result.source_url,
        byte_size=fetch_result.byte_size,
        content_type=fetch_result.content_type,
        baseline_image_path=str(previous_state.get("baseline_image_path", "")).strip(),
        rollback_enabled=protect_baseline,
    )

    if not baseline_hash:
        next_state["baseline_hash"] = fetch_result.hash_value
        next_state["last_hash"] = fetch_result.hash_value
        next_state["baseline_updated_at"] = fetch_result.checked_at
        transition.status = AvatarHashStatus.BASELINE_CREATED
        transition.baseline_created = True
        transition.baseline_hash = fetch_result.hash_value
        transition.previous_hash = ""
        return transition

    if baseline_hash == fetch_result.hash_value:
        next_state["last_hash"] = baseline_hash
        transition.baseline_hash = baseline_hash
        return transition

    next_state["last_previous_hash"] = baseline_hash
    next_state["last_changed_at"] = fetch_result.checked_at
    next_state["change_count"] = int(previous_state.get("change_count", 0) or 0) + 1
    transition.changed = True

    if protect_baseline:
        next_state["last_hash"] = baseline_hash
        transition.status = AvatarHashStatus.CHANGED
        transition.baseline_hash = baseline_hash
        return transition

    next_state["baseline_hash"] = fetch_result.hash_value
    next_state["last_hash"] = fetch_result.hash_value
    next_state["baseline_updated_at"] = fetch_result.checked_at
    transition.status = AvatarHashStatus.CHANGED_ADOPTED
    transition.adopted_new_baseline = True
    transition.baseline_hash = fetch_result.hash_value
    return transition


def summarize_avatar_hash_transition(
    transition: AvatarHashTransition,
    sent_push_groups: list[str] | None = None,
) -> list[str]:
    lines = [
        "avatar hash check",
        f"group_id: {transition.group_id}",
        f"status: {transition.status}",
        f"checked_at: {transition.checked_at}",
        f"rollback_enabled: {transition.rollback_enabled}",
    ]

    if transition.observed_hash:
        lines.append(f"observed_hash: {_short_hash(transition.observed_hash)}")
    if transition.baseline_hash:
        lines.append(f"baseline_hash: {_short_hash(transition.baseline_hash)}")
    if transition.previous_hash:
        lines.append(f"previous_hash: {_short_hash(transition.previous_hash)}")
    if transition.byte_size:
        lines.append(f"byte_size: {transition.byte_size}")
    if transition.content_type:
        lines.append(f"content_type: {transition.content_type}")
    if transition.source_url:
        lines.append(f"source_url: {transition.source_url}")
    if transition.baseline_image_path:
        lines.append(f"baseline_image_path: {transition.baseline_image_path}")
    if transition.rollback_attempted:
        lines.append(
            f"rollback_result: {'success' if transition.rollback_succeeded else 'failed'}"
        )
    if transition.rollback_failure_reason:
        lines.append(f"rollback_failure_reason: {transition.rollback_failure_reason}")
    if transition.rollback_applied_input:
        lines.append(f"rollback_applied_input: {transition.rollback_applied_input}")
    if transition.rollback_attempted_inputs:
        lines.append(
            "rollback_attempted_inputs: " + ", ".join(transition.rollback_attempted_inputs)
        )
    if transition.rollback_error:
        lines.append(f"rollback_error: {transition.rollback_error}")
    if transition.error:
        lines.append(f"error: {transition.error}")

    if sent_push_groups is not None:
        lines.append(
            "logs_sent_to: " + (", ".join(sent_push_groups) if sent_push_groups else "-")
        )

    return lines


def summarize_avatar_hash_state(state: dict[str, Any]) -> list[str]:
    lines = [
        "avatar hash state",
        f"group_id: {state.get('group_id', '-')}",
        f"storage_mode: {state.get('storage_mode', 'baseline_hash_plus_single_image')}",
        f"last_fetch_ok: {state.get('last_fetch_ok', False)}",
        f"last_checked_at: {state.get('last_checked_at', '-')}",
        f"first_baseline_at: {state.get('first_baseline_at', '-')}",
        f"baseline_updated_at: {state.get('baseline_updated_at', '-')}",
        f"last_changed_at: {state.get('last_changed_at', '-')}",
        f"change_count: {state.get('change_count', 0)}",
    ]

    baseline_hash = str(state.get("baseline_hash") or state.get("last_hash") or "").strip()
    observed_hash = str(state.get("last_observed_hash", "")).strip()
    previous_hash = str(state.get("last_previous_hash", "")).strip()
    if baseline_hash:
        lines.append(f"baseline_hash: {_short_hash(baseline_hash)}")
    if observed_hash:
        lines.append(f"last_observed_hash: {_short_hash(observed_hash)}")
    if previous_hash:
        lines.append(f"last_previous_hash: {_short_hash(previous_hash)}")

    if state.get("baseline_image_path"):
        lines.append(f"baseline_image_path: {state['baseline_image_path']}")
    if state.get("last_observed_byte_size"):
        lines.append(f"last_observed_byte_size: {state['last_observed_byte_size']}")
    if state.get("last_observed_content_type"):
        lines.append(f"last_observed_content_type: {state['last_observed_content_type']}")
    if state.get("last_observed_source_url"):
        lines.append(f"last_observed_source_url: {state['last_observed_source_url']}")
    if state.get("last_rollback_at"):
        lines.append(f"last_rollback_at: {state['last_rollback_at']}")
    if state.get("last_rollback_result"):
        lines.append(f"last_rollback_result: {state['last_rollback_result']}")
    if state.get("last_rollback_failure_reason"):
        lines.append(
            f"last_rollback_failure_reason: {state['last_rollback_failure_reason']}"
        )
    if state.get("last_rollback_applied_input"):
        lines.append(f"last_rollback_applied_input: {state['last_rollback_applied_input']}")
    attempted_inputs = state.get("last_rollback_attempted_inputs")
    if isinstance(attempted_inputs, list) and attempted_inputs:
        lines.append("last_rollback_attempted_inputs: " + ", ".join(attempted_inputs))
    if state.get("last_rollback_error"):
        lines.append(f"last_rollback_error: {state['last_rollback_error']}")
    if state.get("last_error"):
        lines.append(f"last_error: {state['last_error']}")

    return lines


def _build_group_avatar_urls(group_id: str) -> list[str]:
    return [
        f"https://p.qlogo.cn/gh/{group_id}/{group_id}/640",
        f"https://p.qlogo.cn/gh/{group_id}/{group_id}/0",
        f"http://p.qlogo.cn/gh/{group_id}/{group_id}/640",
        f"http://p.qlogo.cn/gh/{group_id}/{group_id}/0",
    ]


def _looks_like_image(content_type: str, data: bytes) -> bool:
    lowered = content_type.lower()
    if "image/" in lowered:
        return True

    signatures = (
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"GIF87a",
        b"GIF89a",
        b"RIFF",
    )
    return any(data.startswith(signature) for signature in signatures)


def _guess_file_suffix(content_type: str, data: bytes) -> str:
    lowered = content_type.lower()
    if "png" in lowered or data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if "jpeg" in lowered or "jpg" in lowered or data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if "gif" in lowered or data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if "webp" in lowered or data.startswith(b"RIFF"):
        return ".webp"
    return ".img"


def _short_hash(value: str) -> str:
    return value[:12] if value else "-"


async def _fetch_group_avatar_hash_with_session(
    group_id: str,
    checked_at: str,
    session: Any,
) -> AvatarHashFetchResult:
    last_error = "no avatar source available"

    for source_url in _build_group_avatar_urls(group_id):
        request_url = f"{source_url}?_={int(time.time())}"
        try:
            async with session.get(request_url) as response:
                if int(getattr(response, "status", 200) or 200) >= 400:
                    last_error = f"http status {response.status}"
                    continue

                content_type = str(response.headers.get("Content-Type", ""))
                data = await response.read()

            if not data:
                last_error = "empty avatar response"
                continue

            if not _looks_like_image(content_type, data):
                last_error = f"non-image avatar response: {content_type or 'unknown'}"
                continue

            return AvatarHashFetchResult(
                ok=True,
                group_id=group_id,
                checked_at=checked_at,
                hash_value=hashlib.sha256(data).hexdigest(),
                source_url=source_url,
                byte_size=len(data),
                content_type=content_type,
                file_suffix=_guess_file_suffix(content_type, data),
                image_bytes=data,
            )
        except Exception as exc:
            last_error = _format_avatar_fetch_error(exc)

    return AvatarHashFetchResult(
        ok=False,
        group_id=group_id,
        checked_at=checked_at,
        error=last_error,
    )


def _create_avatar_http_session(timeout_seconds: int) -> Any:
    aiohttp = _load_aiohttp()
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    return aiohttp.ClientSession(
        timeout=timeout,
        headers=AVATAR_FETCH_REQUEST_HEADERS,
    )


def _load_aiohttp() -> Any:
    try:
        return importlib.import_module("aiohttp")
    except ImportError as exc:
        raise RuntimeError("aiohttp dependency not installed") from exc


def _format_avatar_fetch_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__
