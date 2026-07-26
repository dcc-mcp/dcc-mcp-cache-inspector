"""Fail-closed boundary for unsupported Houdini cache inspection."""

from __future__ import annotations

from dcc_mcp_cache_inspector.__version__ import __version__
from dcc_mcp_cache_inspector.bgeo_parser import UnsupportedFormatError, inspect_cache, parse_bgeo_header

__all__ = [
    "__version__",
    "UnsupportedFormatError",
    "inspect_cache",
    "parse_bgeo_header",
]
