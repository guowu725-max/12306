import unittest
from datetime import datetime

from app.services.confirmation_domain import (
    clamp_confirmation_expiry,
    parse_daily_start_time,
    resolve_train_date,
)


class ConfirmationDomainTest(unittest.TestCase):
    def test_fixed_date_strategy_keeps_configured_date(self):
        resolved = resolve_train_date(
            "2026-10-01",
            "fixed",
            0,
            now=datetime(2026, 9, 14, 23, 30),
        )
        self.assertEqual(resolved, "2026-10-01")

    def test_offset_date_strategy_uses_china_local_date(self):
        resolved = resolve_train_date(
            "2026-10-01",
            "offset",
            2,
            now=datetime(2026, 9, 14, 23, 30),
        )
        self.assertEqual(resolved, "2026-09-16")

    def test_invalid_date_strategy_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_train_date("2026-10-01", "weekly", 0)

    def test_negative_offset_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_train_date("2026-10-01", "offset", -1)

    def test_daily_start_time_requires_zero_padded_hh_mm(self):
        self.assertEqual(parse_daily_start_time("07:05"), (7, 5))
        for value in ("7:05", "24:00", "12:60", "noon", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_daily_start_time(value)

    def test_confirmation_expiry_is_clamped_to_safe_range(self):
        self.assertEqual(clamp_confirmation_expiry(10), 15)
        self.assertEqual(clamp_confirmation_expiry(60), 60)
        self.assertEqual(clamp_confirmation_expiry(999), 300)


if __name__ == "__main__":
    unittest.main()
