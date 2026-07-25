#!/usr/bin/env python
"""CLI for dcc-mcp-cache-inspector — inspect bgeo/bgeo.sc caches from the terminal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dcc_mcp_cache_inspector.bgeo_parser import parse_bgeo_header


def _cmd_inspect(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser().resolve()
    try:
        info = parse_bgeo_header(path)
    except Exception as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(info.to_dict(), indent=2, ensure_ascii=False, default=str))
        return 0

    # Human-readable output
    print("=== {} ===".format(path.name if path.is_file() else str(path)))
    print("  File:        {}".format(path))
    print("  Format:      {}".format(path.suffix))
    version = info.file_version or "?"
    print("  Geo version: {}".format(version))
    print("  Topology:    {}".format(info.topology or "?"))
    if info.time is not None:
        print("  Time:        {:.4f}".format(info.time))
    print()
    print("  Point count:      {:>10,d}".format(info.point_count))
    print("  Vertex count:     {:>10,d}".format(info.vertex_count))
    print("  Primitive count:  {:>10,d}".format(info.primitive_count))

    bbox = info.bounding_box
    if bbox:
        print("  Bounding box:     [{:.4f}, {:.4f}, {:.4f}] → [{:.4f}, {:.4f}, {:.4f}]".format(*bbox))

    # Attributes
    for domain_label, attrs in [
        ("Point attributes", info.point_attributes),
        ("Vertex attributes", info.vertex_attributes),
        ("Primitive attributes", info.primitive_attributes),
        ("Detail attributes", info.detail_attributes),
    ]:
        if attrs:
            print("\n  {}:".format(domain_label))
            for a in attrs:
                default_str = ""
                default = a.get("default")
                if default is not None:
                    default_str = "  default={}".format(default)
                print("    - {name}  storage={storage}({storage_kind}{storage_bytes})  "
                      "size={size}{default}".format(default=default_str, **a))

    print()
    print("  Compatible: {}".format(", ".join(info.is_compatible_with)))
    if not info.has_index and path.suffix == ".bgeo":
        print("  (no index section)")
    return 0


def _cmd_attributes(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser().resolve()
    try:
        info = parse_bgeo_header(path)
    except Exception as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1

    if args.json:
        output = {
            "point": info.point_attributes,
            "vertex": info.vertex_attributes,
            "primitive": info.primitive_attributes,
            "detail": info.detail_attributes,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
        return 0

    for label, attrs in [
        ("Point", info.point_attributes),
        ("Vertex", info.vertex_attributes),
        ("Primitive", info.primitive_attributes),
        ("Detail", info.detail_attributes),
    ]:
        if attrs:
            print("{}:".format(label))
            for a in attrs:
                print("  {}  storage={}  size={}".format(
                    a["name"], a["storage"], a["size"]))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dcc-mcp-cache-inspector",
        description="Read-only bgeo/bgeo.sc cache inspector.",
    )
    sub = parser.add_subparsers(dest="command")

    # inspect
    p_inspect = sub.add_parser("inspect", help="Full metadata report")
    p_inspect.add_argument("file", help="Path to .bgeo or .bgeo.sc file")
    p_inspect.add_argument("--json", action="store_true", help="JSON output")

    # attributes
    p_attrs = sub.add_parser("attributes", help="Attribute list only")
    p_attrs.add_argument("file", help="Path to .bgeo or .bgeo.sc file")
    p_attrs.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        return _cmd_inspect(args)
    elif args.command == "attributes":
        return _cmd_attributes(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
