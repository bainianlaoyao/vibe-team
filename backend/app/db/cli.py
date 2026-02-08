from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.db.bootstrap import initialize_database
from app.db.migrations import upgrade_to_head


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beebeebrain-db",
        description="BeeBeeBrain database management commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create database directory, apply migrations and optionally seed data.",
    )
    init_parser.add_argument("--database-url", default=None)
    init_parser.add_argument("--skip-seed", action="store_true")

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Apply database migrations to latest revision.",
    )
    migrate_parser.add_argument("--database-url", default=None)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        initialize_database(
            database_url=args.database_url,
            seed=not args.skip_seed,
        )
        print("Database initialized.")
        return 0

    if args.command == "migrate":
        upgrade_to_head(args.database_url)
        print("Database migrations applied.")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
