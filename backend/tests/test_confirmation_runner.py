import unittest
from datetime import datetime

from app.tasks.confirmation_runner import daily_job_id, scan_job_id
from app.services.confirmation_domain import resolve_train_date


class ConfirmationRunnerHelpersTest(unittest.TestCase):
    def test_job_ids_are_namespaced(self):
        self.assertEqual(daily_job_id(12), "wecom_daily_12")
        self.assertEqual(scan_job_id(12), "wecom_scan_12")

    def test_offset_date_is_resolved_at_run_time(self):
        self.assertEqual(
            resolve_train_date(
                "2026-01-01",
                "offset",
                3,
                now=datetime(2026, 9, 14, 8, 0),
            ),
            "2026-09-17",
        )


if __name__ == "__main__":
    unittest.main()
