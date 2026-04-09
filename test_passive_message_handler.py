import unittest
from types import SimpleNamespace

from models import PluginConfig, PushGroupConfig, SourceGroupConfig
from passive_message_handler import PassiveMessageHandler


class FakeMessageRecallService:
    def __init__(self) -> None:
        self.cache_calls: list[dict[str, object]] = []

    def cache_message(
        self,
        payload,
        recall_message_enabled: bool,
        fallback_message_str: str = "",
        fallback_message_id: str = "",
    ) -> None:
        self.cache_calls.append(
            {
                "payload": payload,
                "recall_message_enabled": recall_message_enabled,
                "fallback_message_str": fallback_message_str,
                "fallback_message_id": fallback_message_id,
            }
        )


class PassiveMessageHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_group_message_routes_cache_and_profile_update(self) -> None:
        config = PluginConfig(
            monitored_groups={
                "10001": SourceGroupConfig(
                    enabled=True,
                    push_group_ids=["30001"],
                    recall_message_enabled=True,
                )
            },
            push_groups={"30001": PushGroupConfig(enabled=True)},
        )
        recall_service = FakeMessageRecallService()
        member_profile_calls: list[dict[str, object]] = []

        async def handle_passive_member_profile(
            group_id: str,
            user_id: str,
            card: str | None,
            nickname: str | None,
            push_group_ids: list[str],
        ) -> None:
            member_profile_calls.append(
                {
                    "group_id": group_id,
                    "user_id": user_id,
                    "card": card,
                    "nickname": nickname,
                    "push_group_ids": list(push_group_ids),
                }
            )

        handler = PassiveMessageHandler(
            lambda: config,
            lambda event: str(event.get_group_id() or "").strip(),
            lambda source_config: list(source_config.push_group_ids),
            recall_service,
            handle_passive_member_profile,
        )
        event = SimpleNamespace(
            get_group_id=lambda: "10001",
            get_sender_id=lambda: "20001",
            message_obj=SimpleNamespace(
                raw_message={
                    "post_type": "message",
                    "message_type": "group",
                    "group_id": "10001",
                    "message_id": "50001",
                    "sender": {"card": "card-a", "nickname": "nick-a"},
                },
                message_str="hello world",
                message_id="50001",
            ),
        )

        await handler.handle_group_message(event)

        self.assertEqual(len(recall_service.cache_calls), 1)
        self.assertTrue(recall_service.cache_calls[0]["recall_message_enabled"])
        self.assertEqual(recall_service.cache_calls[0]["fallback_message_str"], "hello world")
        self.assertEqual(len(member_profile_calls), 1)
        self.assertEqual(member_profile_calls[0]["group_id"], "10001")
        self.assertEqual(member_profile_calls[0]["user_id"], "20001")
        self.assertEqual(member_profile_calls[0]["card"], "card-a")
        self.assertEqual(member_profile_calls[0]["nickname"], "nick-a")
        self.assertEqual(member_profile_calls[0]["push_group_ids"], ["30001"])

    async def test_handle_group_message_ignores_unmonitored_group(self) -> None:
        config = PluginConfig()
        recall_service = FakeMessageRecallService()
        member_profile_calls: list[dict[str, object]] = []

        async def handle_passive_member_profile(
            group_id: str,
            user_id: str,
            card: str | None,
            nickname: str | None,
            push_group_ids: list[str],
        ) -> None:
            member_profile_calls.append({"group_id": group_id})

        handler = PassiveMessageHandler(
            lambda: config,
            lambda event: str(event.get_group_id() or "").strip(),
            lambda source_config: list(source_config.push_group_ids),
            recall_service,
            handle_passive_member_profile,
        )
        event = SimpleNamespace(
            get_group_id=lambda: "10001",
            get_sender_id=lambda: "20001",
            message_obj=SimpleNamespace(
                raw_message={"post_type": "message", "message_type": "group"},
                message_str="hello world",
                message_id="50001",
            ),
        )

        await handler.handle_group_message(event)

        self.assertEqual(recall_service.cache_calls, [])
        self.assertEqual(member_profile_calls, [])
