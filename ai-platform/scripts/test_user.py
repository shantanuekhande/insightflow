"""Create and print the first AI Platform domain object."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.enums import Platform, UserTier  # noqa: E402
from app.domain.user import User  # noqa: E402


def main() -> None:
    user = User(
        name="Shantanu",
        tier=UserTier.PREMIUM,
        country="India",
        platform=Platform.WEB,
    )
    print(user.model_dump_json(indent=4))


if __name__ == "__main__":
    main()
