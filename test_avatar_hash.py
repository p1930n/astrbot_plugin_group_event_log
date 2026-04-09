import hashlib
import unittest
from unittest.mock import patch

from avatar_hash import fetch_group_avatar_hash


class FakeAvatarHttpResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        data: bytes = b"",
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._data = data

    async def __aenter__(self) -> "FakeAvatarHttpResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def read(self) -> bytes:
        return self._data


class FakeAvatarHttpSession:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.requested_urls: list[str] = []

    async def __aenter__(self) -> "FakeAvatarHttpSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, url: str) -> FakeAvatarHttpResponse:
        self.requested_urls.append(url)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AvatarHashFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_group_avatar_hash_uses_next_source_after_http_error(self) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\navatar"
        fake_session = FakeAvatarHttpSession(
            [
                FakeAvatarHttpResponse(status=503),
                FakeAvatarHttpResponse(
                    status=200,
                    headers={"Content-Type": "image/png"},
                    data=image_bytes,
                ),
            ]
        )

        with patch("avatar_hash._create_avatar_http_session", return_value=fake_session):
            result = await fetch_group_avatar_hash("10001", timeout_seconds=5)

        self.assertTrue(result.ok)
        self.assertEqual(result.group_id, "10001")
        self.assertEqual(
            result.hash_value,
            hashlib.sha256(image_bytes).hexdigest(),
        )
        self.assertEqual(result.source_url, "https://p.qlogo.cn/gh/10001/10001/0")
        self.assertEqual(result.file_suffix, ".png")
        self.assertEqual(len(fake_session.requested_urls), 2)

    async def test_fetch_group_avatar_hash_returns_error_when_aiohttp_missing(self) -> None:
        with patch(
            "avatar_hash._create_avatar_http_session",
            side_effect=RuntimeError("aiohttp dependency not installed"),
        ):
            result = await fetch_group_avatar_hash("10001")

        self.assertFalse(result.ok)
        self.assertEqual(result.group_id, "10001")
        self.assertIn("aiohttp dependency not installed", result.error)
