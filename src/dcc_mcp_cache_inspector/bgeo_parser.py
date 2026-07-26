"""Fail-closed boundary for Houdini geometry caches."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

MAX_JSON_HEADER_BYTES = 256 * 1024 * 1024


class UnsupportedFormatError(ValueError):
    """Raised when a cache requires an unimplemented SideFX decoder."""


def parse_bgeo_header(
    file_path: Path,
    max_header_bytes: int = MAX_JSON_HEADER_BYTES,
) -> NoReturn:
    """Reject bgeo input until SideFX binary JSON and HSC are implemented.

    ``max_header_bytes`` remains in the signature for API compatibility with
    version 0.1.0. No cache bytes are decoded.
    """
    del max_header_bytes

    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))
    if file_path.stat().st_size == 0:
        raise ValueError("File is empty: {}".format(file_path))

    raise UnsupportedFormatError(
        "Unsupported Houdini cache format: SideFX .bgeo binary JSON and "
        ".bgeo.sc HSC decoding are not implemented. Use a Houdini-native "
        "reader such as ginfo."
    )


def inspect_cache(file_path: Path) -> NoReturn:
    """Reject unsupported bgeo input without returning fabricated metadata."""
    parse_bgeo_header(file_path)
