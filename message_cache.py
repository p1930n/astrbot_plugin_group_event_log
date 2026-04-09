from __future__ import annotations

import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Any


DEFAULT_MESSAGE_CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MESSAGE_CACHE_PER_GROUP_LIMIT = 1000


@dataclass(slots=True)
class CachedGroupMessage:
    message_id: str
    group_id: str
    user_id: str
    sender_nickname: str = ""
    sender_card: str = ""
    message_text: str = ""
    message_content: str = ""
    sent_at: str = ""


def build_cached_group_message(
    payload: dict[str, Any] | None,
    fallback_message_str: str = "",
    fallback_message_id: str = "",
) -> CachedGroupMessage | None:
    if not isinstance(payload, dict):
        return None
    if _to_text(payload.get("post_type")) != "message":
        return None
    if _to_text(payload.get("message_type")) != "group":
        return None

    group_id = _to_text(payload.get("group_id"))
    message_id = _to_text(payload.get("message_id")) or _to_text(fallback_message_id)
    if not group_id or not message_id:
        return None

    sender = payload.get("sender")
    if not isinstance(sender, dict):
        sender = {}

    raw_message = _to_text(payload.get("raw_message"))
    serialized_message = _serialize_message(payload.get("message"))
    message_text = _to_text(fallback_message_str)
    message_content = raw_message or serialized_message or message_text

    return CachedGroupMessage(
        message_id=message_id,
        group_id=group_id,
        user_id=_to_text(sender.get("user_id")) or _to_text(payload.get("user_id")),
        sender_nickname=_to_text(sender.get("nickname")),
        sender_card=_to_text(sender.get("card")),
        message_text=message_text,
        message_content=message_content,
        sent_at=_to_text(payload.get("time")) or str(int(time.time())),
    )


class GroupMessageCache:
    def __init__(
        self,
        ttl_seconds: int = DEFAULT_MESSAGE_CACHE_TTL_SECONDS,
        per_group_limit: int = DEFAULT_MESSAGE_CACHE_PER_GROUP_LIMIT,
    ) -> None:
        self._ttl_seconds = max(300, int(ttl_seconds or DEFAULT_MESSAGE_CACHE_TTL_SECONDS))
        self._per_group_limit = max(
            100,
            int(per_group_limit or DEFAULT_MESSAGE_CACHE_PER_GROUP_LIMIT),
        )
        self._groups: dict[str, OrderedDict[str, CachedGroupMessage]] = {}

    def store(self, message: CachedGroupMessage) -> None:
        group_cache = self._groups.setdefault(message.group_id, OrderedDict())
        now_ts = int(time.time())
        self._cleanup_group_cache(group_cache, now_ts)

        group_cache.pop(message.message_id, None)
        group_cache[message.message_id] = message

        while len(group_cache) > self._per_group_limit:
            group_cache.popitem(last=False)

    def pop(self, group_id: str, message_id: str) -> CachedGroupMessage | None:
        group_id = _to_text(group_id)
        message_id = _to_text(message_id)
        if not group_id or not message_id:
            return None

        group_cache = self._groups.get(group_id)
        if not group_cache:
            return None

        self._cleanup_group_cache(group_cache, int(time.time()))
        message = group_cache.pop(message_id, None)
        if not group_cache:
            self._groups.pop(group_id, None)
        return message

    def clear_group(self, group_id: str) -> None:
        group_id = _to_text(group_id)
        if not group_id:
            return
        self._groups.pop(group_id, None)

    def _cleanup_group_cache(
        self,
        group_cache: OrderedDict[str, CachedGroupMessage],
        now_ts: int,
    ) -> None:
        expired_keys = [
            message_id
            for message_id, message in group_cache.items()
            if now_ts - _parse_timestamp(message.sent_at, now_ts) > self._ttl_seconds
        ]
        for message_id in expired_keys:
            group_cache.pop(message_id, None)


def _serialize_message(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()

    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return str(value).strip()


def _parse_timestamp(value: str, fallback: int) -> int:
    text = _to_text(value)
    if not text:
        return fallback

    try:
        return int(float(text))
    except (TypeError, ValueError):
        try:
            return int(datetime.fromisoformat(text).timestamp())
        except (TypeError, ValueError):
            return fallback


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
