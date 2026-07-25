"""dcc-mcp-cache-inspector — Read-only bgeo/bgeo.sc cache inspection.

Parse Houdini geometry caches without Houdini or any DCC runtime.
Extract metadata, attributes, bounding boxes, and version compatibility
from the JSON header of .bgeo and .bgeo.sc files.
"""

from __future__ import annotations

from dcc_mcp_cache_inspector.__version__ import __version__
from dcc_mcp_cache_inspector.bgeo_parser import BgeoInfo, inspect_cache, parse_bgeo_header

__all__ = [
    "__version__",
    "BgeoInfo",
    "inspect_cache",
    "parse_bgeo_header",
]
