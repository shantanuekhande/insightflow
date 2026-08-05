"""Convenience script to generate synthetic event data.

Usage (run from project root E:\\Scalar_Academy\\insightflow\\):
    python src/scripts/generate_45days.py          # 45 days, ~60000 events
    python src/scripts/generate_45days.py --days 7 --events 5000
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure project root is on sys.path so `from src.xxx` works
# regardless of where you run the script from.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulator.config import SimulatorConfig
from src.simulator.generator import generate_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate multi-day synthetic event data")
    parser.add_argument("--days", type=int, default=45, help="Number of days to generate (default: 45)")
    parser.add_argument("--events", type=int, default=60000, help="Total events across all days (default: 60000)")
    args = parser.parse_args()

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days - 1)

    config = SimulatorConfig(
        target_date=start_date,
        date_range_days=args.days,
        total_events=args.events,
        schema_version="2.0",
    )

    print(f"Generating {args.events} events across {args.days} days ({start_date} to {end_date})")
    print(f"~{args.events // args.days} events/day (with weekday/weekend variation)")
    print()

    count = generate_events(config)
    print(f"\nDone! {count} events written to data/landing/")
    print(f"  Schema version: 2.0")
    print(f"  Date range: {start_date} to {end_date}")
    print(f"  Next step:  python -m src.etl.ingest   (Landing -> Bronze)")
    print(f"  Then:       python -m src.etl.transform (Bronze -> Silver)")
    print(f"  Then:       python -m src.etl.gold      (Silver -> Gold)")


if __name__ == "__main__":
    main()
