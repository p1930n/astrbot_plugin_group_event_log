import unittest
from time import time

from message_cache import GroupMessageCache
from message_recall_service import MessageRecallService
from notice_adapter import GroupNoticeEvent


class FakeRecallLogDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch_group_recall_logs(
        self,
        event,
        notice: GroupNoticeEvent,
        push_group_ids: list[str],
        cached_message,
        show_message_content: bool,
    ) -> None:
        self.calls.append(
            {
                "event": event,
                "notice": notice,
                "push_group_ids": list(push_group_ids),
                "cached_message": cached_message,
                "show_message_content": show_message_content,
            }
        )


class MessageRecallServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_message_only_stores_when_enabled(self) -> None:
        dispatcher = FakeRecallLogDispatcher()
        service = MessageRecallService(dispatcher, GroupMessageCache())
        now_ts = str(int(time()))
        payload = {
            "post_type": "message",
            "message_type": "group",
            "group_id": "10001",
            "message_id": "50001",
            "raw_message": "hello",
            "sender": {"user_id": "20001", "nickname": "tester"},
            "time": now_ts,
        }
        notice = GroupNoticeEvent(
            event_key="group_recall",
            notice_type="group_recall",
            sub_type="",
            group_id="10001",
            details={"message_id": "50001"},
        )

        service.cache_message(payload, recall_message_enabled=False)
        await service.handle_group_recall(
            event=object(),
            notice=notice,
            push_group_ids=["30001"],
            show_message_content=False,
        )

        self.assertEqual(len(dispatcher.calls), 1)
        self.assertIsNone(dispatcher.calls[0]["cached_message"])

        service.cache_message(payload, recall_message_enabled=True)
        await service.handle_group_recall(
            event=object(),
            notice=notice,
            push_group_ids=["30001"],
            show_message_content=True,
        )

        self.assertEqual(len(dispatcher.calls), 2)
        self.assertIsNotNone(dispatcher.calls[1]["cached_message"])

    async def test_handle_group_recall_pops_cached_message_and_dispatches(self) -> None:
        dispatcher = FakeRecallLogDispatcher()
        service = MessageRecallService(dispatcher, GroupMessageCache())
        now_ts = str(int(time()))
        payload = {
            "post_type": "message",
            "message_type": "group",
            "group_id": "10001",
            "message_id": "50001",
            "raw_message": "hello",
            "sender": {"user_id": "20001", "nickname": "tester"},
            "time": now_ts,
        }
        notice = GroupNoticeEvent(
            event_key="group_recall",
            notice_type="group_recall",
            sub_type="",
            group_id="10001",
            details={"message_id": "50001"},
        )

        service.cache_message(payload, recall_message_enabled=True)
        await service.handle_group_recall(
            event=object(),
            notice=notice,
            push_group_ids=["30001"],
            show_message_content=True,
        )

        self.assertEqual(len(dispatcher.calls), 1)
        self.assertEqual(dispatcher.calls[0]["push_group_ids"], ["30001"])
        self.assertTrue(dispatcher.calls[0]["show_message_content"])
        self.assertIsNotNone(dispatcher.calls[0]["cached_message"])
