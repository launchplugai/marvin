"""CLI entrypoint for Marvin orchestration."""

from __future__ import annotations

import argparse
import json

from marvin.system import MarvinSystem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Marvin orchestration flow")
    parser.add_argument("message", help="User message to orchestrate")
    parser.add_argument("--project", default=".", help="Project context (path or name)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    system = MarvinSystem()
    try:
        result = system.handle(args.message, project=args.project)
        print(json.dumps(result, indent=2))
    finally:
        system.close()


if __name__ == "__main__":
    main()
