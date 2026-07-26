"""Regression tests for fail-closed cache inspection."""

from __future__ import annotations

from pathlib import Path

import pytest

from dcc_mcp_cache_inspector import UnsupportedFormatError, inspect_cache, parse_bgeo_header
from dcc_mcp_cache_inspector.cli import main


def test_sidefx_binary_json_is_rejected(tmp_path: Path) -> None:
    cache = tmp_path / "cache.bgeo"
    # SideFX UT_JSONDefines.h: 0x7f plus the binary JSON magic "NSJb".
    cache.write_bytes(b"\x7fNSJb\x00\x00\x00")

    with pytest.raises(UnsupportedFormatError, match="binary JSON.*HSC"):
        parse_bgeo_header(cache)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("synthetic.bgeo", b'bgeo{"pointcount":8}'),
        ("synthetic.bgeo.sc", b"bgeo.sc-not-an-hsc-container"),
    ],
)
def test_previous_synthetic_formats_are_rejected(tmp_path: Path, name: str, content: bytes) -> None:
    cache = tmp_path / name
    cache.write_bytes(content)

    with pytest.raises(UnsupportedFormatError):
        inspect_cache(cache)


def test_missing_file_still_reports_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_bgeo_header(tmp_path / "missing.bgeo")


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    cache = tmp_path / "empty.bgeo"
    cache.touch()

    with pytest.raises(ValueError, match="empty"):
        parse_bgeo_header(cache)


def test_cli_fails_without_printing_metadata(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cache = tmp_path / "cache.bgeo"
    cache.write_bytes(b"\x7fNSJb\x00")

    assert main(["inspect", str(cache), "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unsupported Houdini cache format" in captured.err
