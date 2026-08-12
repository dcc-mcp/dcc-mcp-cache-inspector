#!/usr/bin/env python
"""Command line and standalone-service entry points."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path
from typing import Any, Optional, Sequence

from dcc_mcp_cache_inspector import BgeoParseError, inspect_cache, list_cache_attributes
from dcc_mcp_cache_inspector.__version__ import __version__


def _print_json(value: Any, *, stream: Any = None) -> None:
    if stream is None:
        stream = sys.stdout
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), file=stream)


def _inspect(args: argparse.Namespace) -> int:
    result = inspect_cache(
        Path(args.file),
        max_file_bytes=args.max_file_bytes,
        max_decoded_bytes=args.max_decoded_bytes,
    )
    _print_json(result)
    return 0


def _attributes(args: argparse.Namespace) -> int:
    result = list_cache_attributes(
        Path(args.file),
        max_file_bytes=args.max_file_bytes,
        max_decoded_bytes=args.max_decoded_bytes,
    )
    _print_json({"attributes": result, "count": len(result)})
    return 0


def _serve(args: argparse.Namespace) -> int:
    from dcc_mcp_cache_inspector.server import start_server, stop_server

    server = start_server(port=args.port, registry_dir=args.registry_dir)
    _print_json(
        {
            "status": "started",
            "version": __version__,
            "mcp_url": server.mcp_url,
            "instance_type": "standalone",
        }
    )
    stopped = threading.Event()

    def request_stop(_signum: int, _frame: Any) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    try:
        stopped.wait()
    finally:
        stop_server()
    return 0


def _add_limits(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=512 * 1024 * 1024,
        help="Maximum compressed/input bytes (default: 512 MiB)",
    )
    parser.add_argument(
        "--max-decoded-bytes",
        type=int,
        default=512 * 1024 * 1024,
        help="Maximum decoded bytes (default: 512 MiB)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcc-mcp-cache-inspector",
        description="Inspect SideFX .geo/.bgeo/.bgeo.sc caches without Houdini.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect cache structure")
    inspect_parser.add_argument("file", help="Path to .geo, .bgeo, or .bgeo.sc")
    _add_limits(inspect_parser)
    inspect_parser.set_defaults(handler=_inspect)

    attributes_parser = subparsers.add_parser("attributes", help="List cache attributes")
    attributes_parser.add_argument("file", help="Path to .geo, .bgeo, or .bgeo.sc")
    _add_limits(attributes_parser)
    attributes_parser.set_defaults(handler=_attributes)

    serve_parser = subparsers.add_parser("serve", help="Run the standalone MCP service")
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--registry-dir", default=None)
    serve_parser.set_defaults(handler=_serve)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (BgeoParseError, FileNotFoundError, ValueError) as exc:
        _print_json(
            {"error": str(exc), "error_type": type(exc).__name__, "success": False},
            stream=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
