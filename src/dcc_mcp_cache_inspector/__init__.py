"""Houdini-free SideFX geometry cache inspection and DCC-MCP service."""

from __future__ import annotations

from dcc_mcp_cache_inspector.__version__ import __version__
from dcc_mcp_cache_inspector.bgeo_parser import (
    BgeoParseError,
    ResourceLimitError,
    UnsupportedFormatError,
    inspect_cache,
    list_cache_attributes,
    parse_bgeo_header,
)

__all__ = [
    "__version__",
    "BgeoParseError",
    "ResourceLimitError",
    "UnsupportedFormatError",
    "inspect_cache",
    "list_cache_attributes",
    "parse_bgeo_header",
]
