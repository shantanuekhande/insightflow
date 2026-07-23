import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.enums import Platform, UserTier  # noqa: E402
from app.domain.user import User  # noqa: E402


class UserTests(unittest.TestCase):
    def test_user_is_created_with_a_generated_id_and_timestamp(self):
        user = User(
            name="Shantanu",
            tier=UserTier.PREMIUM,
            country="India",
            platform=Platform.WEB,
        )

        self.assertTrue(user.user_id)
        self.assertIsNotNone(user.created_at.tzinfo)
        self.assertEqual(user.tier, UserTier.PREMIUM)


if __name__ == "__main__":
    unittest.main()
