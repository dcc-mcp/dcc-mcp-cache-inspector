"""Tests for bgeo cache parser — read-only header inspection."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from dcc_mcp_cache_inspector.bgeo_parser import (
    BGEO_MAGIC,
    MAX_JSON_HEADER_BYTES,
    _decompress_blosc,
    _detect_format,
    _find_json_boundary,
    generate_sample_bgeo_content,
    generate_sample_bgeo_sc_content,
    inspect_cache,
    parse_bgeo_header,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp(data: bytes, suffix: str = ".bgeo") -> Path:
    """Write bytes to a named temporary file and return its Path."""
    fh = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        fh.write(data)
        fh.flush()
        return Path(fh.name)
    finally:
        fh.close()


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def test_detect_bgeo_format():
    """bgeo magic bytes are recognized."""
    raw = b"bgeo" + b'{"fileversion":"20.0"}'
    fmt, offset = _detect_format(raw)
    assert fmt == "bgeo"
    assert offset == 4


def test_detect_bgeo_sc_format():
    """bgeo.sc magic bytes are recognized."""
    raw = b"bgeo.sc" + b"compressed-data"
    fmt, offset = _detect_format(raw)
    assert fmt == "bgeo.sc"
    assert offset == 7


def test_detect_raw_json():
    """Files starting with '{' are detected as raw JSON bgeo."""
    raw = b'{"fileversion":"17.0"}'
    fmt, offset = _detect_format(raw)
    assert fmt == "bgeo (raw JSON)"


def test_detect_unrecognized_raises():
    """Non-bgeo bytes raise ValueError."""
    with pytest.raises(ValueError, match="Unrecognized"):
        _detect_format(b"\x00\x00\x00\x00garbage")


# ---------------------------------------------------------------------------
# JSON boundary finder
# ---------------------------------------------------------------------------

def test_find_json_boundary_simple():
    raw = b'{"a":1,"b":[2,3]}trailing-binary'
    end = _find_json_boundary(raw, 0)
    assert raw[:end] == b'{"a":1,"b":[2,3]}'


def test_find_json_boundary_nested():
    raw = b'{"outer":{"inner":[1,{"deep":true}]}}END'
    end = _find_json_boundary(raw, 0)
    assert raw[:end] == b'{"outer":{"inner":[1,{"deep":true}]}}'


def test_find_json_boundary_with_strings():
    raw = b'{"name":"val}ue","escaped":"\\\\\\""}AFTER'
    end = _find_json_boundary(raw, 0)
    assert raw[:end] == b'{"name":"val}ue","escaped":"\\\\\\""}'


def test_find_json_boundary_unterminated_raises():
    with pytest.raises(ValueError, match="Unterminated"):
        _find_json_boundary(b'{"a":1', 0)


# ---------------------------------------------------------------------------
# Sample file generation
# ---------------------------------------------------------------------------

def test_generate_sample_bgeo():
    content = generate_sample_bgeo_content(point_count=8)
    assert content.startswith(BGEO_MAGIC)
    # Parse it back
    fmt, offset = _detect_format(content)
    assert fmt == "bgeo"
    assert offset == 4
    json_start = content.find(b"{", offset)
    json_end = _find_json_boundary(content, json_start)
    header = json.loads(content[json_start:json_end])
    assert header["pointcount"] == 8
    assert header["vertexcount"] == 24
    assert header["primitivecount"] == 6


def test_generate_sample_bgeo_sc():
    """Generate and verify a sample .bgeo.sc file (needs blosc2)."""
    try:
        import blosc2  # noqa: F401
    except ImportError:
        pytest.skip("blosc2 not installed")
    content = generate_sample_bgeo_sc_content()
    assert content.startswith(b"bgeo.sc")
    # Decompress and verify
    decompressed = _decompress_blosc(content[7:])
    header = json.loads(decompressed)
    assert header["pointcount"] == 4
    assert header["fileversion"] == "20.5"


# ---------------------------------------------------------------------------
# Full parse — .bgeo
# ---------------------------------------------------------------------------

def test_parse_bgeo_basic():
    content = generate_sample_bgeo_content(point_count=8, file_version="20.0", time=1.0)
    tmp = _write_temp(content, suffix=".bgeo")
    try:
        info = parse_bgeo_header(tmp)
        assert info.point_count == 8
        assert info.vertex_count == 24
        assert info.primitive_count == 6
        assert info.file_version == "20.0"
        assert info.time == 1.0
        assert info.topology == "Poly"
    finally:
        tmp.unlink(missing_ok=True)


def test_parse_bgeo_attributes():
    content = generate_sample_bgeo_content()
    tmp = _write_temp(content, suffix=".bgeo")
    try:
        info = parse_bgeo_header(tmp)
        # Point attributes
        pattrs = info.point_attributes
        assert len(pattrs) >= 3
        names = {a["name"] for a in pattrs}
        assert "P" in names
        assert "N" in names
        assert "Cd" in names

        # Vertex attributes
        vattrs = info.vertex_attributes
        assert any(a["name"] == "uv" for a in vattrs)

        # Detail attributes
        dattrs = info.detail_attributes
        assert any(a["name"] == "bbox" for a in dattrs)
    finally:
        tmp.unlink(missing_ok=True)


def test_parse_bgeo_bounding_box():
    content = generate_sample_bgeo_content()
    tmp = _write_temp(content, suffix=".bgeo")
    try:
        info = parse_bgeo_header(tmp)
        bbox = info.bounding_box
        assert bbox is not None
        assert bbox == (-1.0, -1.0, -1.0, 1.0, 1.0, 1.0)
    finally:
        tmp.unlink(missing_ok=True)


def test_parse_bgeo_compatibility():
    content = generate_sample_bgeo_content(file_version="20.0")
    tmp = _write_temp(content, suffix=".bgeo")
    try:
        info = parse_bgeo_header(tmp)
        compat = info.is_compatible_with
        assert any("20" in c for c in compat)
    finally:
        tmp.unlink(missing_ok=True)


def test_parse_bgeo_all_attribute_names():
    content = generate_sample_bgeo_content()
    tmp = _write_temp(content, suffix=".bgeo")
    try:
        info = parse_bgeo_header(tmp)
        names = info.all_attribute_names
        assert "P" in names
        assert "Cd" in names
        assert "uv" in names
        assert "N" in names
        assert "bbox" in names
    finally:
        tmp.unlink(missing_ok=True)


def test_parse_bgeo_to_dict():
    content = generate_sample_bgeo_content()
    tmp = _write_temp(content, suffix=".bgeo")
    try:
        d = inspect_cache(tmp)
        assert d["point_count"] == 8
        assert d["file_version"] == "20.0"
        assert isinstance(d["point_attributes"], list)
        assert d["bounding_box"] == [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0]
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Full parse — .bgeo.sc
# ---------------------------------------------------------------------------

def test_parse_bgeo_sc_basic():
    try:
        import blosc2  # noqa: F401
    except ImportError:
        pytest.skip("blosc2 not installed")
    content = generate_sample_bgeo_sc_content()
    tmp = _write_temp(content, suffix=".bgeo.sc")
    try:
        info = parse_bgeo_header(tmp)
        assert info.point_count == 4
        assert info.vertex_count == 12
        assert info.primitive_count == 2
        assert info.file_version == "20.5"
        assert info.time == 2.0
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_parse_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        parse_bgeo_header(Path("/nonexistent/path/to/cache.bgeo"))


def test_parse_empty_file():
    tmp = _write_temp(b"", suffix=".bgeo")
    try:
        with pytest.raises(ValueError, match="empty"):
            parse_bgeo_header(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def test_parse_garbage_file():
    tmp = _write_temp(b"\x00\x01\x02" * 100, suffix=".bgeo")
    try:
        with pytest.raises(ValueError, match="Unrecognized"):
            parse_bgeo_header(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# BgeoInfo raw access
# ---------------------------------------------------------------------------

def test_bgeo_info_raw_header():
    content = generate_sample_bgeo_content()
    tmp = _write_temp(content, suffix=".bgeo")
    try:
        info = parse_bgeo_header(tmp)
        raw = info.raw_header
        assert raw["fileversion"] == "20.0"
        assert isinstance(raw["pointattributes"], list)
    finally:
        tmp.unlink(missing_ok=True)


def test_bgeo_info_has_index():
    content = generate_sample_bgeo_content()
    tmp = _write_temp(content, suffix=".bgeo")
    try:
        info = parse_bgeo_header(tmp)
        assert info.has_index is False
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Blosc detection (import error path)
# ---------------------------------------------------------------------------

def test_decompress_blosc_no_library(monkeypatch):
    """_decompress_blosc raises ImportError when blosc is absent."""
    # Simulate neither blosc2 nor blosc being available
    import builtins
    original_import = builtins.__import__

    def block_blosc(name, *args, **kwargs):
        if name in ("blosc2", "blosc"):
            raise ImportError("No module named '{}'".format(name))
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_blosc)
    with pytest.raises(ImportError, match="blosc2"):
        _decompress_blosc(b"fake-data")


# ---------------------------------------------------------------------------
# MAX_JSON_HEADER_BYTES is reasonable
# ---------------------------------------------------------------------------

def test_max_header_bytes_limit():
    """Sanity check: the safety limit is a reasonable power of 2."""
    import math
    log2 = math.log2(MAX_JSON_HEADER_BYTES)
    assert log2 == int(log2), "MAX_JSON_HEADER_BYTES should be a power of 2"
