"""Development and course-acceptance entrypoint for Aegis Review."""

from __future__ import annotations

import argparse

from aegis_review import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Aegis Review workstation")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7880)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    create_app().run(host=args.host, port=args.port, debug=args.debug)
