#!/usr/bin/env python
"""CLI for the fail-closed bgeo inspection boundary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dcc_mcp_cache_inspector.bgeo_parser import parse_bgeo_header


def _reject_unsupported(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser().resolve()
    try:
        parse_bgeo_header(path)
    except Exception as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    raise RuntimeError("Parser returned without a CLI result handler")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dcc-mcp-cache-inspector",
        description="Fail-closed guard for unsupported bgeo/bgeo.sc inspection.",
    )
    sub = parser.add_subparsers(dest="command")

    for command, help_text in (
        ("inspect", "Reject unsupported cache inspection"),
        ("attributes", "Reject unsupported attribute inspection"),
    ):
        command_parser = sub.add_parser(command, help=help_text)
        command_parser.add_argument("file", help="Path to .bgeo or .bgeo.sc file")
        command_parser.add_argument("--json", action="store_true", help="Reserved for future structured output")

    args = parser.parse_args(argv)
    if args.command in {"inspect", "attributes"}:
        return _reject_unsupported(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
