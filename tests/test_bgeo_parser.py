"""Regression tests for real SideFX binary JSON and SCF cache inspection."""

from __future__ import annotations

import importlib.util
import json
import os
import struct
import subprocess
import sys
import tracemalloc
from array import array
from pathlib import Path
from typing import Any

import blosc
import pytest

_PARSER_PATH = Path(__file__).parents[1] / "skill" / "cache-inspection" / "scripts" / "_bgeo_parser.py"
_SPEC = importlib.util.spec_from_file_location("_cache_inspection_test_parser", _PARSER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_PARSER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _PARSER
_SPEC.loader.exec_module(_PARSER)

BgeoParseError = _PARSER.BgeoParseError
ResourceLimitError = _PARSER.ResourceLimitError
UnsupportedFormatError = _PARSER.UnsupportedFormatError
inspect_cache = _PARSER.inspect_cache
list_cache_attributes = _PARSER.list_cache_attributes
parse_bgeo_header = _PARSER.parse_bgeo_header
_bounds_from_paged_values = _PARSER._bounds_from_paged_values

_BINARY_MAGIC = 0x624A534E


def _length(value: int) -> bytes:
    if value < 0xF1:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xf2" + struct.pack("<H", value)
    return b"\xf4" + struct.pack("<I", value)


def _value(value: Any) -> bytes:
    if value is None:
        return b"\x00"
    if value is False:
        return b"\x30"
    if value is True:
        return b"\x31"
    if isinstance(value, int):
        if -128 <= value < 128:
            return b"\x11" + struct.pack("<b", value)
        return b"\x13" + struct.pack("<i", value)
    if isinstance(value, float):
        return b"\x19" + struct.pack("<f", value)
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return b"\x27" + _length(len(encoded)) + encoded
    if isinstance(value, list):
        return b"[" + b"".join(_value(item) for item in value) + b"]"
    if isinstance(value, dict):
        return b"{" + b"".join(_value(key) + _value(item) for key, item in value.items()) + b"}"
    raise TypeError(type(value).__name__)


def _uniform_f32(values: list[float]) -> bytes:
    return b"\x40\x19" + _length(len(values)) + struct.pack("<{}f".format(len(values)), *values)


def _fixture_document() -> list[Any]:
    return [
        "fileversion",
        "22.0.368",
        "hasindex",
        True,
        "pointcount",
        2,
        "vertexcount",
        2,
        "primitivecount",
        1,
        "info",
        ["hostname", "PRIVATE-MACHINE", "source", "C:/private/cache.hip"],
        "attributes",
        [
            "pointattributes",
            [
                [
                    ["scope", "public", "type", "numeric", "name", "P"],
                    [
                        "size",
                        3,
                        "storage",
                        "fpreal32",
                        "values",
                        [
                            "size",
                            3,
                            "storage",
                            "fpreal32",
                            "pagesize",
                            1024,
                            "rawpagedata",
                            [-1.0, 2.0, 3.0, 4.0, -5.0, 6.0],
                        ],
                    ],
                ]
            ],
        ],
        "primitives",
        [
            [
                ["type", "Polygon_run"],
                ["startvertex", 0, "nprimitives", 1, "nvertices_rle", [2, 1]],
            ]
        ],
    ]


def _binary_fixture() -> bytes:
    document = _fixture_document()
    encoded = _value(document)
    # Replace only the P raw page with a true binary uniform array.
    marker = _value([-1.0, 2.0, 3.0, 4.0, -5.0, 6.0])
    encoded = encoded.replace(marker, _uniform_f32([-1.0, 2.0, 3.0, 4.0, -5.0, 6.0]), 1)
    return b"\x7f" + struct.pack("<I", _BINARY_MAGIC) + encoded


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def test_binary_bgeo_inspection_returns_structural_metadata(tmp_path: Path) -> None:
    cache = _write(tmp_path / "fixture.bgeo", _binary_fixture())

    result = inspect_cache(cache)

    assert result["format"] == "bgeo"
    assert result["compressed"] is False
    assert result["file_version"] == "22.0.368"
    assert result["point_count"] == 2
    assert result["vertex_count"] == 2
    assert result["primitive_count"] == 1
    assert result["primitive_types"] == ["Polygon_run"]
    assert result["bounds"] == [[-1.0, -5.0, 3.0], [4.0, 2.0, 6.0]]
    assert result["attributes"] == [
        {
            "owner": "pointattributes",
            "name": "P",
            "data_type": "numeric",
            "scope": "public",
            "tuple_size": 3,
            "storage": "fpreal32",
            "element_count": 2,
        }
    ]
    assert "PRIVATE-MACHINE" not in json.dumps(result)
    assert "private/cache.hip" not in json.dumps(result)


def test_scf_blosc_cache_is_decompressed_without_houdini(tmp_path: Path) -> None:
    binary = _binary_fixture()
    compressed = blosc.compress(binary, typesize=1, clevel=5)
    cache = _write(
        tmp_path / "fixture.bgeo.sc",
        b"scf1" + (b"\x00" * 8) + compressed + (b"\x00" * 24) + b"1fcs",
    )

    result = inspect_cache(cache)

    assert result["format"] == "bgeo.sc"
    assert result["compressed"] is True
    assert result["decoded_size_bytes"] == len(binary)
    assert result["point_count"] == 2


def test_ascii_geo_is_supported(tmp_path: Path) -> None:
    cache = tmp_path / "fixture.geo"
    cache.write_text(json.dumps(_fixture_document()), encoding="utf-8")

    result = parse_bgeo_header(cache)

    assert result["format"] == "geo"
    assert result["bounds"] == [[-1.0, -5.0, 3.0], [4.0, 2.0, 6.0]]


def test_attribute_only_api_omits_geometry_payload(tmp_path: Path) -> None:
    cache = _write(tmp_path / "fixture.bgeo", _binary_fixture())

    attributes = list_cache_attributes(cache)

    assert attributes[0]["name"] == "P"
    assert "rawpagedata" not in json.dumps(attributes)


def test_missing_empty_and_unknown_files_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        inspect_cache(tmp_path / "missing.bgeo")

    empty = tmp_path / "empty.bgeo"
    empty.touch()
    with pytest.raises(BgeoParseError, match="empty"):
        inspect_cache(empty)

    unknown = _write(tmp_path / "unknown.bgeo", b"not-sidefx")
    with pytest.raises(UnsupportedFormatError, match="expected SideFX"):
        inspect_cache(unknown)


def test_resource_limits_apply_before_decode(tmp_path: Path) -> None:
    cache = _write(tmp_path / "fixture.bgeo", _binary_fixture())
    with pytest.raises(ResourceLimitError, match="File size"):
        inspect_cache(cache, max_file_bytes=8)

    binary = _binary_fixture()
    compressed = blosc.compress(binary, typesize=1, clevel=5)
    scf = _write(
        tmp_path / "fixture.bgeo.sc",
        b"scf1" + (b"\x00" * 8) + compressed + (b"\x00" * 24) + b"1fcs",
    )
    with pytest.raises(ResourceLimitError, match="decoded size"):
        inspect_cache(scf, max_decoded_bytes=8)


def test_expanded_uniform_arrays_are_bounded_before_allocation(tmp_path: Path) -> None:
    payload = b"\x7f" + struct.pack("<I", _BINARY_MAGIC) + b"[\x40\x27" + _length(2_000_001)
    cache = _write(tmp_path / "uniform-strings.bgeo", payload)

    with pytest.raises(ResourceLimitError, match="Expanded uniform array"):
        inspect_cache(cache)


def test_position_bounds_are_streamed_without_per_point_expansion() -> None:
    point_count = 20_000
    raw = array("f", (float(index % 3) for index in range(point_count * 3)))
    tracemalloc.start()
    try:
        bounds, warning = _bounds_from_paged_values(
            raw,
            tuple_size=3,
            element_count=point_count,
            page_size=1024,
            packing=None,
        )
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert warning is None
    assert bounds == ((0.0, 1.0, 2.0), (0.0, 1.0, 2.0))
    assert peak_bytes < 500_000


def test_truncated_binary_and_scf_are_rejected(tmp_path: Path) -> None:
    binary = _write(tmp_path / "truncated.bgeo", _binary_fixture()[:-1])
    with pytest.raises(BgeoParseError, match="Unexpected end"):
        inspect_cache(binary)

    scf = _write(tmp_path / "truncated.bgeo.sc", b"scf1" + b"\x00" * 20)
    with pytest.raises(BgeoParseError, match="truncated|boundary"):
        inspect_cache(scf)


def test_skill_subprocess_uses_its_matching_package_and_emits_results(tmp_path: Path) -> None:
    cache = _write(tmp_path / "fixture.bgeo", _binary_fixture())
    shadow = tmp_path / "shadow" / "dcc_mcp_cache_inspector"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text(
        'raise RuntimeError("ambient package must not be imported")\n',
        encoding="utf-8",
    )
    scripts = Path(__file__).parents[1] / "skill" / "cache-inspection" / "scripts"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(shadow.parent)
    request = json.dumps({"file_path": str(cache)})

    inspection = subprocess.run(
        [sys.executable, str(scripts / "inspect_cache.py")],
        input=request,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    inspection_result = json.loads(inspection.stdout)
    assert inspection_result["success"] is True
    assert inspection_result["context"]["inspection"]["point_count"] == 2

    attributes = subprocess.run(
        [sys.executable, str(scripts / "list_attributes.py")],
        input=request,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    attributes_result = json.loads(attributes.stdout)
    assert attributes_result["success"] is True
    assert attributes_result["context"]["count"] == 1


def test_skill_failure_omits_local_path_and_traceback(tmp_path: Path) -> None:
    scripts = Path(__file__).parents[1] / "skill" / "cache-inspection" / "scripts"
    missing = tmp_path / "private" / "missing.bgeo"
    request = json.dumps({"file_path": str(missing)})

    completed = subprocess.run(
        [sys.executable, str(scripts / "inspect_cache.py")],
        input=request,
        text=True,
        capture_output=True,
        check=False,
    )
    result = json.loads(completed.stdout)
    serialized = json.dumps(result)
    assert completed.returncode == 1
    assert result["success"] is False
    assert result["error"] == "FileNotFoundError"
    assert str(tmp_path) not in serialized
    assert "Traceback" not in serialized
