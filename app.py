"""Development and course-acceptance entrypoint for Aegis Review."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from aegis_review import create_app


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Aegis Review workstation")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7880)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    create_app().run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        use_reloader=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
