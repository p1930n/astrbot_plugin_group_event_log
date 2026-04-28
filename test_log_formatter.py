import unittest

from formatting.log_formatter import format_group_recall_log
from domain.message_cache import CachedGroupMessage
from domain.notice_adapter import GroupNoticeEvent


class LogFormatterTests(unittest.TestCase):
    def test_group_recall_log_omits_redundant_message_text(self) -> None:
        notice = GroupNoticeEvent(
            event_key="group_recall",
            notice_type="group_recall",
            sub_type="",
            group_id="10001",
            user_id="20001",
            operator_id="20002",
            details={"message_id": "50001", "time_raw": "1713960000"},
        )
        cached_message = CachedGroupMessage(
            message_id="50001",
            group_id="10001",
            user_id="20001",
            sender_nickname="tester",
            message_text="hello",
            message_content="hello",
            sent_at="1713960000",
        )

        log_text = format_group_recall_log(
            notice,
            trace_id="trace-1",
            cached_message=cached_message,
            show_message_content=True,
        )

        self.assertNotIn("message_text:", log_text)
        self.assertIn("message_content: hello", log_text)

    def test_group_recall_cache_miss_omits_redundant_message_text(self) -> None:
        notice = GroupNoticeEvent(
            event_key="group_recall",
            notice_type="group_recall",
            sub_type="",
            group_id="10001",
            details={"message_id": "50001"},
        )

        log_text = format_group_recall_log(
            notice,
            trace_id="trace-1",
            cached_message=None,
            show_message_content=True,
        )

        self.assertNotIn("message_text:", log_text)
        self.assertIn("message_content: cache_miss", log_text)
