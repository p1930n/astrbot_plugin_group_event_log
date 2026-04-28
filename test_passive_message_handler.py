import unittest
from types import SimpleNamespace

from commands.command_context import CommandContext
from domain.models import PluginConfig, PushGroupConfig, SourceGroupConfig
from runtime.passive_message_handler import PassiveMessageHandler
from runtime.plugin_runtime_state import PluginRuntimeState


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


class FakeGroupContextService:
    def current_group_id(self, context: CommandContext) -> str:
        if not isinstance(context, CommandContext):
            raise AssertionError("passive handler must pass dehydrated CommandContext")
        return context.group_id


class FakeGroupRuntimeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def resolve_enabled_push_targets(self, source_config: SourceGroupConfig) -> list[str]:
        return list(source_config.push_group_ids)

    async def handle_passive_member_profile(
        self,
        group_id: str,
        user_id: str,
        card: str | None,
        nickname: str | None,
        push_group_ids: list[str],
    ) -> None:
        self.calls.append(
            {
                "group_id": group_id,
                "user_id": user_id,
                "card": card,
                "nickname": nickname,
                "push_group_ids": list(push_group_ids),
            }
        )


class PassiveMessageHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_group_message_routes_cache_and_profile_update(self) -> None:
        runtime_state = PluginRuntimeState(
            config=PluginConfig(
                monitored_groups={
                    "10001": SourceGroupConfig(
                        enabled=True,
                        push_group_ids=["30001"],
                        recall_message_enabled=True,
                    )
                },
                push_groups={"30001": PushGroupConfig(enabled=True)},
            )
        )
        recall_service = FakeMessageRecallService()
        group_runtime_service = FakeGroupRuntimeService()

        handler = PassiveMessageHandler(
            runtime_state,
            FakeGroupContextService(),
            recall_service,
            group_runtime_service,
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
        self.assertEqual(len(group_runtime_service.calls), 1)
        self.assertEqual(group_runtime_service.calls[0]["group_id"], "10001")
        self.assertEqual(group_runtime_service.calls[0]["user_id"], "20001")
        self.assertEqual(group_runtime_service.calls[0]["card"], "card-a")
        self.assertEqual(group_runtime_service.calls[0]["nickname"], "nick-a")
        self.assertEqual(group_runtime_service.calls[0]["push_group_ids"], ["30001"])

    async def test_handle_group_message_ignores_unmonitored_group(self) -> None:
        recall_service = FakeMessageRecallService()
        group_runtime_service = FakeGroupRuntimeService()

        handler = PassiveMessageHandler(
            PluginRuntimeState(config=PluginConfig()),
            FakeGroupContextService(),
            recall_service,
            group_runtime_service,
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
        self.assertEqual(group_runtime_service.calls, [])

    async def test_handle_group_message_does_not_require_event_group_id_attribute(
        self,
    ) -> None:
        runtime_state = PluginRuntimeState(
            config=PluginConfig(
                monitored_groups={
                    "10001": SourceGroupConfig(
                        enabled=True,
                        push_group_ids=[],
                        recall_message_enabled=True,
                    )
                },
            )
        )
        recall_service = FakeMessageRecallService()
        group_runtime_service = FakeGroupRuntimeService()

        handler = PassiveMessageHandler(
            runtime_state,
            FakeGroupContextService(),
            recall_service,
            group_runtime_service,
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
                    "sender": {"nickname": "nick-a"},
                },
                message_str="hello world",
                message_id="50001",
            ),
        )

        await handler.handle_group_message(event)

        self.assertEqual(len(recall_service.cache_calls), 1)
        self.assertEqual(len(group_runtime_service.calls), 1)
