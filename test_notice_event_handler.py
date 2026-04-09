import unittest

from models import PluginConfig, PushGroupConfig, SourceGroupConfig
from notice_event_handler import NoticeEventHandler


class FakeLogDispatcher:
    def __init__(self) -> None:
        self.notice_calls: list[dict[str, object]] = []

    async def dispatch_notice_logs(self, event, notice, push_group_ids: list[str]) -> None:
        self.notice_calls.append(
            {
                "event": event,
                "notice": notice,
                "push_group_ids": list(push_group_ids),
            }
        )


class FakeMessageRecallService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def handle_group_recall(
        self,
        event,
        notice,
        push_group_ids: list[str],
        show_message_content: bool,
    ) -> None:
        self.calls.append(
            {
                "event": event,
                "notice": notice,
                "push_group_ids": list(push_group_ids),
                "show_message_content": show_message_content,
            }
        )


class NoticeEventHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_recall_routes_to_recall_service_only(self) -> None:
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
        log_dispatcher = FakeLogDispatcher()
        recall_service = FakeMessageRecallService()
        rollback_calls: list[tuple[str, list[str]]] = []

        async def handle_group_name_rollback(notice, push_group_ids: list[str]) -> None:
            rollback_calls.append((notice.group_id, list(push_group_ids)))

        handler = NoticeEventHandler(
            lambda: config,
            lambda source_config: list(source_config.push_group_ids),
            log_dispatcher,
            recall_service,
            handle_group_name_rollback,
        )
        payload = {
            "post_type": "notice",
            "notice_type": "group_recall",
            "group_id": "10001",
            "message_id": "50001",
        }

        await handler.handle_raw_notice(object(), payload)

        self.assertEqual(len(recall_service.calls), 1)
        self.assertEqual(recall_service.calls[0]["push_group_ids"], ["30001"])
        self.assertTrue(recall_service.calls[0]["show_message_content"])
        self.assertEqual(log_dispatcher.notice_calls, [])
        self.assertEqual(rollback_calls, [])

    async def test_group_name_notice_dispatches_log_and_rollback(self) -> None:
        config = PluginConfig(
            monitored_groups={
                "10001": SourceGroupConfig(
                    enabled=True,
                    push_group_ids=["30001"],
                    group_name_rollback_enabled=True,
                )
            },
            push_groups={"30001": PushGroupConfig(enabled=True)},
        )
        log_dispatcher = FakeLogDispatcher()
        recall_service = FakeMessageRecallService()
        rollback_calls: list[tuple[str, list[str]]] = []

        async def handle_group_name_rollback(notice, push_group_ids: list[str]) -> None:
            rollback_calls.append((notice.group_id, list(push_group_ids)))

        handler = NoticeEventHandler(
            lambda: config,
            lambda source_config: list(source_config.push_group_ids),
            log_dispatcher,
            recall_service,
            handle_group_name_rollback,
        )
        payload = {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "group_name",
            "group_id": "10001",
            "name_new": "mutated-name",
        }

        await handler.handle_raw_notice(object(), payload)

        self.assertEqual(len(log_dispatcher.notice_calls), 1)
        self.assertEqual(log_dispatcher.notice_calls[0]["push_group_ids"], ["30001"])
        self.assertEqual(len(recall_service.calls), 0)
        self.assertEqual(rollback_calls, [("10001", ["30001"])])
