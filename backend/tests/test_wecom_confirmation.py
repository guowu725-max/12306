import unittest

from app.services.wecom_confirmation import (
    build_confirmation_card,
    parse_confirmation_event,
)


class WeComConfirmationAdapterTest(unittest.TestCase):
    def test_card_contains_confirm_and_ignore_actions(self):
        card = build_confirmation_card(
            confirmation_id=42,
            raw_token="abc123",
            task_name="早班车",
            route="上海虹桥 → 杭州东",
            train_date="2026-10-01",
            train_code="G123",
            time_range="08:00 - 08:45",
            seat_name="二等座",
            seat_count="有",
            passenger_names=["张三"],
            expire_seconds=60,
        )
        self.assertEqual(card["msgtype"], "template_card")
        buttons = card["template_card"]["button_list"]
        self.assertEqual(len(buttons), 2)
        self.assertIn("ticket_confirm:confirm:42:abc123", [b["key"] for b in buttons])
        self.assertIn("ticket_confirm:ignore:42:abc123", [b["key"] for b in buttons])

    def test_parse_template_card_event(self):
        frame = {
            "body": {
                "from": {"userid": "guowu"},
                "event": {"event_key": "ticket_confirm:confirm:42:abc123"},
            }
        }
        parsed = parse_confirmation_event(frame)
        self.assertEqual(parsed, ("confirm", 42, "abc123", "guowu"))

    def test_parse_rejects_unrelated_event(self):
        self.assertIsNone(
            parse_confirmation_event(
                {"body": {"event": {"event_key": "other:confirm:42:abc"}}}
            )
        )


if __name__ == "__main__":
    unittest.main()
