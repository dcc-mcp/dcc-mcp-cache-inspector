"""Bounded, Houdini-free inspection of SideFX ``.geo``/``.bgeo`` caches.

The implementation deliberately returns structural metadata only.  It never
publishes the free-form ``info`` block because that block may contain machine,
user, or source-path metadata written by the producing application.
"""

from __future__ import annotations

import json
import math
import struct
import sys
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Optional, Sequence, Union

import blosc

MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_DECODED_BYTES = 512 * 1024 * 1024
MAX_STRING_BYTES = 16 * 1024 * 1024
MAX_STRUCTURAL_ITEMS = 2_000_000
MAX_UNIFORM_ITEMS = 100_000_000
MAX_DEPTH = 256

# Backward-compatible public constant from 0.1.0.
MAX_JSON_HEADER_BYTES = MAX_FILE_BYTES


class BgeoParseError(ValueError):
    """Raised when a cache is malformed or cannot be decoded safely."""


class UnsupportedFormatError(BgeoParseError):
    """Raised when input is not a supported SideFX geometry representation."""


class ResourceLimitError(BgeoParseError):
    """Raised before an input can exceed a configured resource boundary."""


@dataclass(frozen=True)
class AttributeSummary:
    owner: str
    name: str
    data_type: Optional[str]
    scope: Optional[str]
    tuple_size: Optional[int]
    storage: Optional[str]
    element_count: Optional[int]


@dataclass(frozen=True)
class CacheInspection:
    format: str
    compressed: bool
    file_size_bytes: int
    decoded_size_bytes: int
    file_version: Optional[str]
    point_count: int
    vertex_count: int
    primitive_count: int
    attributes: tuple[AttributeSummary, ...]
    primitive_types: tuple[str, ...]
    bounds: Optional[tuple[tuple[float, float, float], tuple[float, float, float]]]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "compressed": self.compressed,
            "file_size_bytes": self.file_size_bytes,
            "decoded_size_bytes": self.decoded_size_bytes,
            "file_version": self.file_version,
            "point_count": self.point_count,
            "vertex_count": self.vertex_count,
            "primitive_count": self.primitive_count,
            "attributes": [asdict(attribute) for attribute in self.attributes],
            "primitive_types": list(self.primitive_types),
            "bounds": [list(bound) for bound in self.bounds] if self.bounds is not None else None,
            "warnings": list(self.warnings),
        }


_JID_NULL = 0x00
_JID_MAP_BEGIN = 0x7B
_JID_MAP_END = 0x7D
_JID_ARRAY_BEGIN = 0x5B
_JID_ARRAY_END = 0x5D
_JID_BOOL = 0x10
_JID_INT8 = 0x11
_JID_INT16 = 0x12
_JID_INT32 = 0x13
_JID_INT64 = 0x14
_JID_REAL16 = 0x18
_JID_REAL32 = 0x19
_JID_REAL64 = 0x1A
_JID_UINT8 = 0x21
_JID_UINT16 = 0x22
_JID_STRING = 0x27
_JID_FALSE = 0x30
_JID_TRUE = 0x31
_JID_TOKENDEF = 0x2B
_JID_TOKENREF = 0x26
_JID_TOKENUNDEF = 0x2D
_JID_UNIFORM_ARRAY = 0x40
_JID_MAGIC = 0x7F

_BINARY_MAGIC = 0x624A534E
_BINARY_MAGIC_SWAPPED = 0x4E534A62

_SCF_MAGIC = b"scf1"
_SCF_FOOTER_MAGIC = b"1fcs"
_BLOSC_HEADER_BYTES = 16


class _BinaryJsonReader:
    """Original bounded recursive-descent reader for SideFX binary JSON."""

    def __init__(self, payload: bytes) -> None:
        self._payload = memoryview(payload)
        self._offset = 0
        self._endian = "<"
        self._tokens: dict[int, str] = {}
        self._structural_items = 0

    def parse(self) -> Any:
        if self._read_u8() != _JID_MAGIC:
            raise UnsupportedFormatError("Missing SideFX binary JSON magic")
        raw_magic = self._read_exact(4)
        little = int.from_bytes(raw_magic, "little")
        if little == _BINARY_MAGIC:
            self._endian = "<"
        elif little == _BINARY_MAGIC_SWAPPED:
            self._endian = ">"
        else:
            raise UnsupportedFormatError("Invalid SideFX binary JSON magic")

        result = self._parse_value(depth=0)
        if self._offset != len(self._payload):
            raise BgeoParseError("Trailing bytes after binary JSON root at offset {}".format(self._offset))
        return result

    def _parse_value(self, depth: int, token: Optional[int] = None) -> Any:
        if depth > MAX_DEPTH:
            raise ResourceLimitError("Binary JSON nesting exceeds {}".format(MAX_DEPTH))
        token = self._next_token() if token is None else token

        if token == _JID_NULL:
            return None
        if token == _JID_FALSE:
            return False
        if token == _JID_TRUE:
            return True
        if token == _JID_BOOL:
            return self._read_u8() != 0
        if token == _JID_INT8:
            return self._unpack("b")
        if token == _JID_INT16:
            return self._unpack("h")
        if token == _JID_INT32:
            return self._unpack("i")
        if token == _JID_INT64:
            return self._unpack("q")
        if token == _JID_UINT8:
            return self._read_u8()
        if token == _JID_UINT16:
            return self._unpack("H")
        if token == _JID_REAL16:
            return self._unpack("e")
        if token == _JID_REAL32:
            return self._unpack("f")
        if token == _JID_REAL64:
            return self._unpack("d")
        if token == _JID_STRING:
            return self._read_string()
        if token == _JID_TOKENREF:
            token_id = self._read_length()
            try:
                return self._tokens[token_id]
            except KeyError as exc:
                raise BgeoParseError("Unknown binary JSON string token {}".format(token_id)) from exc
        if token == _JID_UNIFORM_ARRAY:
            value_type = self._read_u8()
            length = self._read_length()
            return self._read_uniform_array(value_type, length)
        if token == _JID_ARRAY_BEGIN:
            values: list[Any] = []
            while True:
                child_token = self._next_token()
                if child_token == _JID_ARRAY_END:
                    return values
                self._count_structural_item()
                values.append(self._parse_value(depth + 1, child_token))
        if token == _JID_MAP_BEGIN:
            values: dict[str, Any] = {}
            while True:
                key_token = self._next_token()
                if key_token == _JID_MAP_END:
                    return values
                if key_token not in {_JID_STRING, _JID_TOKENREF}:
                    raise BgeoParseError("Binary JSON map key is not a string")
                key = self._parse_value(depth + 1, key_token)
                self._count_structural_item()
                values[key] = self._parse_value(depth + 1)

        raise BgeoParseError("Unsupported binary JSON token 0x{:02x}".format(token))

    def _next_token(self) -> int:
        while True:
            token = self._read_u8()
            if token == _JID_TOKENDEF:
                token_id = self._read_length()
                if len(self._tokens) >= MAX_STRUCTURAL_ITEMS and token_id not in self._tokens:
                    raise ResourceLimitError("Binary JSON token table is too large")
                self._tokens[token_id] = self._read_string()
                continue
            if token == _JID_TOKENUNDEF:
                self._tokens.pop(self._read_length(), None)
                continue
            return token

    def _read_uniform_array(self, value_type: int, length: int) -> Any:
        if length > MAX_UNIFORM_ITEMS:
            raise ResourceLimitError("Uniform array length {} exceeds {}".format(length, MAX_UNIFORM_ITEMS))
        if value_type in {_JID_BOOL, _JID_STRING, _JID_TOKENREF} and length > MAX_STRUCTURAL_ITEMS:
            raise ResourceLimitError("Expanded uniform array length {} exceeds {}".format(length, MAX_STRUCTURAL_ITEMS))
        if value_type == _JID_BOOL:
            values: list[bool] = []
            while len(values) < length:
                bits = self._unpack("I")
                remaining = min(32, length - len(values))
                values.extend(bool(bits & (1 << bit)) for bit in range(remaining))
            return values
        if value_type == _JID_STRING:
            return [self._read_string() for _ in range(length)]
        if value_type == _JID_TOKENREF:
            values = []
            for _ in range(length):
                token_id = self._read_length()
                if token_id not in self._tokens:
                    raise BgeoParseError("Unknown uniform string token {}".format(token_id))
                values.append(self._tokens[token_id])
            return values

        type_codes = {
            _JID_INT8: ("b", 1),
            _JID_INT16: ("h", 2),
            _JID_INT32: ("i", 4),
            _JID_INT64: ("q", 8),
            _JID_UINT8: ("B", 1),
            _JID_UINT16: ("H", 2),
            _JID_REAL32: ("f", 4),
            _JID_REAL64: ("d", 8),
        }
        if value_type == _JID_REAL16:
            return [self._unpack("e") for _ in range(length)]
        if value_type not in type_codes:
            raise BgeoParseError("Unsupported uniform array token 0x{:02x}".format(value_type))

        type_code, item_size = type_codes[value_type]
        byte_count = length * item_size
        raw = self._read_exact(byte_count)
        values = array(type_code)
        values.frombytes(raw)
        file_is_little = self._endian == "<"
        if item_size > 1 and file_is_little != (sys.byteorder == "little"):
            values.byteswap()
        return values

    def _read_length(self) -> int:
        lead = self._read_u8()
        if lead < 0xF1:
            value = lead
        elif lead == 0xF2:
            value = self._unpack("H")
        elif lead == 0xF4:
            value = self._unpack("I")
        elif lead == 0xF8:
            value = self._unpack("q")
        else:
            raise BgeoParseError("Invalid binary JSON length prefix 0x{:02x}".format(lead))
        if value < 0:
            raise BgeoParseError("Negative binary JSON length")
        return int(value)

    def _read_string(self) -> str:
        length = self._read_length()
        if length > MAX_STRING_BYTES:
            raise ResourceLimitError("String length {} exceeds {}".format(length, MAX_STRING_BYTES))
        raw = self._read_exact(length)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BgeoParseError("Binary JSON string is not valid UTF-8") from exc

    def _count_structural_item(self) -> None:
        self._structural_items += 1
        if self._structural_items > MAX_STRUCTURAL_ITEMS:
            raise ResourceLimitError("Binary JSON structure is too large")

    def _read_u8(self) -> int:
        return self._read_exact(1)[0]

    def _unpack(self, code: str) -> Any:
        size = struct.calcsize(code)
        return struct.unpack(self._endian + code, self._read_exact(size))[0]

    def _read_exact(self, size: int) -> bytes:
        if size < 0 or self._offset + size > len(self._payload):
            raise BgeoParseError("Unexpected end of binary JSON at offset {}".format(self._offset))
        start = self._offset
        self._offset += size
        return self._payload[start : start + size].tobytes()


def _decompress_scf(payload: bytes, max_decoded_bytes: int) -> bytes:
    if len(payload) < 12 + _BLOSC_HEADER_BYTES + len(_SCF_FOOTER_MAGIC):
        raise BgeoParseError("SCF container is truncated")
    if not payload.startswith(_SCF_MAGIC) or not payload.endswith(_SCF_FOOTER_MAGIC):
        raise BgeoParseError("Invalid SCF container boundary")

    position = 12
    decoded: list[bytes] = []
    decoded_size = 0
    block_count = 0

    while position + _BLOSC_HEADER_BYTES <= len(payload) - len(_SCF_FOOTER_MAGIC):
        header = payload[position : position + _BLOSC_HEADER_BYTES]
        version = header[0]
        uncompressed_size = int.from_bytes(header[4:8], "little")
        compressed_size = int.from_bytes(header[12:16], "little")
        if version not in {1, 2, 3} or uncompressed_size <= 0:
            break
        if compressed_size < _BLOSC_HEADER_BYTES or position + compressed_size > len(payload):
            raise BgeoParseError("Invalid Blosc block size in SCF container")
        if decoded_size + uncompressed_size > max_decoded_bytes:
            raise ResourceLimitError("SCF decoded size exceeds {} bytes".format(max_decoded_bytes))
        try:
            block = blosc.decompress(payload[position : position + compressed_size])
        except Exception as exc:
            raise BgeoParseError("Invalid Blosc block in SCF container") from exc
        if len(block) != uncompressed_size:
            raise BgeoParseError("Blosc block decoded to an unexpected size")
        decoded.append(block)
        decoded_size += len(block)
        block_count += 1
        position += compressed_size

    if block_count == 0:
        raise BgeoParseError("SCF container has no decodable blocks")

    # The remaining bytes are the seek index and reversed footer magic.  Keep
    # the index opaque, but bound it and require the known terminal marker.
    footer_size = len(payload) - position
    if footer_size < len(_SCF_FOOTER_MAGIC) or footer_size > 64 * 1024 * 1024:
        raise BgeoParseError("Invalid SCF index size")
    return b"".join(decoded)


def _read_bounded_file(file_path: Path, max_file_bytes: int) -> bytes:
    if max_file_bytes <= 0 or max_file_bytes > MAX_FILE_BYTES:
        raise ValueError("max_file_bytes must be between 1 and {}".format(MAX_FILE_BYTES))
    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))
    size = file_path.stat().st_size
    if size == 0:
        raise BgeoParseError("File is empty: {}".format(file_path))
    if size > max_file_bytes:
        raise ResourceLimitError("File size {} exceeds {} bytes".format(size, max_file_bytes))
    with file_path.open("rb") as stream:
        return _read_exact_file(stream, size)


def _read_exact_file(stream: BinaryIO, size: int) -> bytes:
    payload = stream.read(size + 1)
    if len(payload) != size:
        raise BgeoParseError("File changed while it was being read")
    return payload


def _parse_document(payload: bytes, max_decoded_bytes: int) -> tuple[Any, str, bool, int]:
    compressed = payload.startswith(_SCF_MAGIC)
    if compressed:
        payload = _decompress_scf(payload, max_decoded_bytes)
    if len(payload) > max_decoded_bytes:
        raise ResourceLimitError("Decoded size {} exceeds {} bytes".format(len(payload), max_decoded_bytes))

    if payload.startswith(bytes([_JID_MAGIC])):
        return _BinaryJsonReader(payload).parse(), "bgeo.sc" if compressed else "bgeo", compressed, len(payload)

    stripped = payload.lstrip()
    if stripped.startswith((b"[", b"{")):
        try:
            document = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BgeoParseError("Invalid SideFX ASCII geometry JSON") from exc
        return document, "geo.sc" if compressed else "geo", compressed, len(payload)

    raise UnsupportedFormatError("Unsupported cache content; expected SideFX ASCII or binary geometry")


def _is_sequence(value: Any) -> bool:
    """Recognize only containers emitted by the JSON decoders on Python 3.9+."""
    return isinstance(value, (list, tuple, array))


def _pairs(value: Any, *, label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if not _is_sequence(value):
        raise BgeoParseError("{} is not a key/value sequence".format(label))
    if len(value) % 2:
        raise BgeoParseError("{} has an odd key/value length".format(label))
    result: dict[str, Any] = {}
    for index in range(0, len(value), 2):
        key = value[index]
        if not isinstance(key, str):
            raise BgeoParseError("{} contains a non-string key".format(label))
        result[key] = value[index + 1]
    return result


def _non_negative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BgeoParseError("{} is not a non-negative integer".format(label))
    return value


def _attribute_summaries(root: Mapping[str, Any]) -> tuple[AttributeSummary, ...]:
    section = root.get("attributes", [])
    if not _is_sequence(section):
        raise BgeoParseError("attributes is not a sequence")
    if len(section) % 2:
        raise BgeoParseError("attributes has an odd owner/value length")

    summaries: list[AttributeSummary] = []
    for owner_index in range(0, len(section), 2):
        owner = section[owner_index]
        entries = section[owner_index + 1]
        if not isinstance(owner, str) or not _is_sequence(entries):
            raise BgeoParseError("Invalid attribute owner block")
        for entry in entries:
            if not _is_sequence(entry) or len(entry) != 2:
                raise BgeoParseError("Invalid attribute entry")
            definition = _pairs(entry[0], label="attribute definition")
            values = _pairs(entry[1], label="attribute values")
            tuple_size = values.get("size")
            if tuple_size is not None:
                tuple_size = _non_negative_int(tuple_size, label="attribute tuple size")
            payload = values.get("values")
            element_count = _attribute_element_count(payload, tuple_size)
            summaries.append(
                AttributeSummary(
                    owner=owner,
                    name=str(definition.get("name", "")),
                    data_type=_optional_string(definition.get("type")),
                    scope=_optional_string(definition.get("scope")),
                    tuple_size=tuple_size,
                    storage=_optional_string(values.get("storage")),
                    element_count=element_count,
                )
            )
    return tuple(summaries)


def _attribute_element_count(payload: Any, tuple_size: Optional[int]) -> Optional[int]:
    if payload is None:
        return None
    values = _pairs(payload, label="attribute payload")
    payload_size = values.get("size", tuple_size)
    if not isinstance(payload_size, int) or payload_size <= 0:
        return None
    for key in ("rawpagedata", "tuples"):
        data = values.get(key)
        if _is_sequence(data):
            if key == "tuples" and data and _is_sequence(data[0]):
                return len(data)
            return len(data) // payload_size
    data = values.get("arrays")
    if _is_sequence(data):
        return len(data)
    return None


def _optional_string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _primitive_types(root: Mapping[str, Any]) -> tuple[str, ...]:
    primitives = root.get("primitives", [])
    if not _is_sequence(primitives):
        raise BgeoParseError("primitives is not a sequence")
    names: set[str] = set()
    for entry in primitives:
        if not _is_sequence(entry) or not entry:
            continue
        try:
            definition = _pairs(entry[0], label="primitive definition")
        except BgeoParseError:
            continue
        primitive_type = definition.get("type")
        if isinstance(primitive_type, str) and primitive_type:
            names.add(primitive_type)
        if len(names) > 1024:
            raise ResourceLimitError("Too many primitive types")
    return tuple(sorted(names))


def _position_bounds(
    root: Mapping[str, Any],
) -> tuple[
    Optional[tuple[tuple[float, float, float], tuple[float, float, float]]],
    Optional[str],
]:
    section = root.get("attributes", [])
    if not _is_sequence(section):
        return None, None
    for owner_index in range(0, len(section) - 1, 2):
        if section[owner_index] != "pointattributes":
            continue
        entries = section[owner_index + 1]
        if not _is_sequence(entries):
            continue
        for entry in entries:
            if not _is_sequence(entry) or len(entry) != 2:
                continue
            definition = _pairs(entry[0], label="position definition")
            if definition.get("name") != "P":
                continue
            values = _pairs(entry[1], label="position values")
            payload = _pairs(values.get("values", []), label="position payload")
            tuple_size = payload.get("size", values.get("size"))
            if not isinstance(tuple_size, int) or tuple_size < 3:
                return None, "Position attribute has an invalid tuple size"
            if payload.get("constantpageflags") is not None:
                return None, "Position bounds omitted for constant-page encoded data"

            tuples = payload.get("tuples")
            if _is_sequence(tuples):
                return _bounds_from_tuples(tuples)

            raw = payload.get("rawpagedata")
            if not _is_sequence(raw):
                return None, "Position attribute has no supported value payload"
            point_count = _non_negative_int(root.get("pointcount", 0), label="pointcount")
            return _bounds_from_paged_values(
                raw,
                tuple_size=tuple_size,
                element_count=point_count,
                page_size=payload.get("pagesize", point_count or 1),
                packing=payload.get("packing"),
            )
    return None, None


def _bounds_from_tuples(
    values: Sequence[Any],
) -> tuple[
    Optional[tuple[tuple[float, float, float], tuple[float, float, float]]],
    Optional[str],
]:
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    for value in values:
        if not _is_sequence(value) or len(value) < 3:
            raise BgeoParseError("Position tuple has fewer than three components")
        for component in range(3):
            item = value[component]
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise BgeoParseError("Position payload contains a non-numeric value")
            number = float(item)
            if not math.isfinite(number):
                return None, "Position bounds omitted for non-finite data"
            minimum[component] = min(minimum[component], number)
            maximum[component] = max(maximum[component], number)
    if not values:
        return None, None
    return (tuple(minimum), tuple(maximum)), None


def _bounds_from_paged_values(
    raw: Sequence[Any],
    *,
    tuple_size: int,
    element_count: int,
    page_size: Any,
    packing: Any,
) -> tuple[
    Optional[tuple[tuple[float, float, float], tuple[float, float, float]]],
    Optional[str],
]:
    if not isinstance(page_size, int) or page_size <= 0:
        raise BgeoParseError("Invalid attribute page size")
    if packing is None:
        packing_values = [tuple_size]
    elif _is_sequence(packing):
        packing_values = list(packing)
    else:
        raise BgeoParseError("Invalid attribute packing")
    if (
        not packing_values
        or any(not isinstance(item, int) or item <= 0 for item in packing_values)
        or sum(packing_values) != tuple_size
    ):
        raise BgeoParseError("Attribute packing does not match tuple size")
    expected = element_count * tuple_size
    if len(raw) != expected:
        raise BgeoParseError("Attribute payload length {} does not match expected {}".format(len(raw), expected))

    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    source_index = 0
    remaining = element_count
    while remaining:
        page_count = min(page_size, remaining)
        component_start = 0
        for group_size in packing_values:
            for _item_index in range(page_count):
                for component in range(group_size):
                    value = raw[source_index]
                    source_index += 1
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise BgeoParseError("Position payload contains a non-numeric value")
                    component_index = component_start + component
                    if component_index < 3:
                        number = float(value)
                        if not math.isfinite(number):
                            return None, "Position bounds omitted for non-finite data"
                        minimum[component_index] = min(minimum[component_index], number)
                        maximum[component_index] = max(maximum[component_index], number)
            component_start += group_size
        remaining -= page_count
    if element_count == 0:
        return None, None
    return (tuple(minimum), tuple(maximum)), None


def inspect_cache(
    file_path: Union[Path, str],
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_decoded_bytes: int = MAX_DECODED_BYTES,
) -> dict[str, Any]:
    """Inspect a SideFX geometry cache without requiring Houdini.

    The result is intentionally bounded and excludes the cache's free-form
    ``info`` block to avoid returning hostnames, usernames, or source paths.
    """
    path = Path(file_path).expanduser().resolve()
    payload = _read_bounded_file(path, max_file_bytes)
    document, format_name, compressed, decoded_size = _parse_document(payload, max_decoded_bytes)
    root = _pairs(document, label="geometry root")
    bounds, bounds_warning = _position_bounds(root)
    warnings = tuple(item for item in (bounds_warning,) if item)
    inspection = CacheInspection(
        format=format_name,
        compressed=compressed,
        file_size_bytes=len(payload),
        decoded_size_bytes=decoded_size,
        file_version=_optional_string(root.get("fileversion")),
        point_count=_non_negative_int(root.get("pointcount", 0), label="pointcount"),
        vertex_count=_non_negative_int(root.get("vertexcount", 0), label="vertexcount"),
        primitive_count=_non_negative_int(root.get("primitivecount", 0), label="primitivecount"),
        attributes=_attribute_summaries(root),
        primitive_types=_primitive_types(root),
        bounds=bounds,
        warnings=warnings,
    )
    return inspection.to_dict()


def parse_bgeo_header(
    file_path: Union[Path, str],
    max_header_bytes: int = MAX_JSON_HEADER_BYTES,
) -> dict[str, Any]:
    """Backward-compatible entry point returning real cache metadata."""
    return inspect_cache(file_path, max_file_bytes=max_header_bytes)


def list_cache_attributes(
    file_path: Union[Path, str],
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_decoded_bytes: int = MAX_DECODED_BYTES,
) -> list[dict[str, Any]]:
    """Return only the bounded attribute definitions for a cache."""
    result = inspect_cache(
        file_path,
        max_file_bytes=max_file_bytes,
        max_decoded_bytes=max_decoded_bytes,
    )
    return list(result["attributes"])
