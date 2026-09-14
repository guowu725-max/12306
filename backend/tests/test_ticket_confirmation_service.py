import unittest

from app.services.ticket_confirmation_service import (
    hash_confirmation_token,
    is_seat_available,
    read_seat,
)


class TicketConfirmationHelpersTest(unittest.TestCase):
    def test_token_hash_is_stable_and_not_plaintext(self):
        digest = hash_confirmation_token("secret-token")
        self.assertEqual(digest, hash_confirmation_token("secret-token"))
        self.assertNotEqual(digest, "secret-token")
        self.assertEqual(len(digest), 64)

    def test_seat_availability_handles_count_and_you(self):
        self.assertTrue(is_seat_available("有"))
        self.assertTrue(is_seat_available("2"))
        self.assertFalse(is_seat_available("0"))
        self.assertFalse(is_seat_available("无"))
        self.assertFalse(is_seat_available("--"))

    def test_read_seat_maps_second_class(self):
        class Train:
            second_seat = "有"
        self.assertEqual(read_seat(Train(), "O"), ("二等座", "有"))


if __name__ == "__main__":
    unittest.main()
