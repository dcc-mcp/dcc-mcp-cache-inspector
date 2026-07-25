"""Read-only bgeo/bgeo.sc cache inspector — no Houdini required.

Parses Houdini geometry cache files (.bgeo, .bgeo.sc) to extract
metadata without loading geometry data into memory or executing any
Houdini code.

Supports:
- .bgeo (uncompressed JSON+binary geometry)
- .bgeo.sc (blosc-compressed geometry, requires optional ``blosc2``)

Format references:
- Houdini Geometry Format (JSON+binary)
- blosc compression (https://www.blosc.org/)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Magic identifiers
BGEO_MAGIC = b"bgeo"
BGEO_SC_MAGIC = b"bgeo.sc"

# Known Houdini storage types → human-readable descriptions
STORAGE_TYPE_MAP: Dict[str, Dict[str, str]] = {
    "fpreal16": {"kind": "float", "bytes": "2", "desc": "16-bit float"},
    "fpreal32": {"kind": "float", "bytes": "4", "desc": "32-bit float"},
    "fpreal64": {"kind": "float", "bytes": "8", "desc": "64-bit float"},
    "int8": {"kind": "int", "bytes": "1", "desc": "8-bit signed integer"},
    "int16": {"kind": "int", "bytes": "2", "desc": "16-bit signed integer"},
    "int32": {"kind": "int", "bytes": "4", "desc": "32-bit signed integer"},
    "int64": {"kind": "int", "bytes": "8", "desc": "64-bit signed integer"},
    "string": {"kind": "string", "bytes": "var", "desc": "Variable-length string"},
    "dict": {"kind": "dict", "bytes": "var", "desc": "Dictionary / array attribute"},
}

# Geo format version patterns we recognize
KNOWN_VERSIONS = frozenset({
    "15.0", "15.5", "16.0", "16.5",
    "17.0", "17.5", "18.0", "18.5",
    "19.0", "19.5", "20.0", "20.5",
})

# Maximum JSON header size to attempt (safety limit for corrupted files)
MAX_JSON_HEADER_BYTES = 256 * 1024 * 1024  # 256 MB


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class BgeoInfo:
    """Parsed bgeo cache metadata (read-only snapshot)."""

    def __init__(self, raw: Dict[str, Any], file_path: Optional[Path] = None) -> None:
        self._raw = raw
        self.file_path = file_path

    # -- counts --

    @property
    def point_count(self) -> int:
        """Number of points in the geometry."""
        return self._raw.get("pointcount", 0)

    @property
    def vertex_count(self) -> int:
        """Number of vertices in the geometry."""
        return self._raw.get("vertexcount", 0)

    @property
    def primitive_count(self) -> int:
        """Number of primitives in the geometry."""
        return self._raw.get("primitivecount", 0)

    @property
    def detail_count(self) -> int:
        """Detail (whole-geometry) element count (normally 1)."""
        return 1 if self._raw.get("detailcount") is None else self._raw["detailcount"]

    # -- version --

    @property
    def file_version(self) -> Optional[str]:
        """Houdini geometry file version string (e.g. '20.0')."""
        return self._raw.get("fileversion")

    @property
    def has_index(self) -> bool:
        """Whether the file includes an index section."""
        return bool(self._raw.get("hasindex", False))

    # -- time --

    @property
    def time(self) -> Optional[float]:
        """Frame time stored in the cache (None if absent)."""
        return self._raw.get("time")

    # -- bounding box --

    @property
    def bounding_box(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        """(xmin, ymin, zmin, xmax, ymax, zmax) from the detail 'P' or
        from the ``pointattributes`` bounding box, if available."""
        # Try explicit bbox key first
        bbox = self._raw.get("bbox")
        if bbox and len(bbox) == 6:
            return tuple(float(v) for v in bbox)

        # Try detail attributes
        detail = self._raw.get("detailattributes")
        if isinstance(detail, list):
            for attr in detail:
                if attr.get("name") == "bbox" and "defaults" in attr:
                    b = attr["defaults"].get("value")
                    if isinstance(b, (list, tuple)) and len(b) == 6:
                        return tuple(float(v) for v in b)
                    if isinstance(b, dict) and "min" in b and "max" in b:
                        mn, mx = b["min"], b["max"]
                        if len(mn) == 3 and len(mx) == 3:
                            return (float(mn[0]), float(mn[1]), float(mn[2]),
                                    float(mx[0]), float(mx[1]), float(mx[2]))
        return None

    # -- topology --

    @property
    def topology(self) -> Optional[str]:
        """Topology type string (e.g. 'Poly', 'PolySoup', 'Mesh')."""
        raw = self._raw.get("topology")
        if isinstance(raw, str):
            return raw
        # Sometimes topology is an object with a 'type' field
        if isinstance(raw, dict):
            return raw.get("type")
        return None

    @property
    def primitive_types(self) -> List[str]:
        """List of primitive types found in the cache."""
        prims = self._raw.get("primitives")
        if not isinstance(prims, list):
            return []
        types: List[str] = []
        for p in prims:
            if isinstance(p, dict):
                t = p.get("type")
                if t:
                    types.append(str(t))
        return types

    # -- attributes --

    @property
    def point_attributes(self) -> List[Dict[str, Any]]:
        """List of point attribute descriptors (name, storage, size, type)."""
        return self._normalize_attrs(self._raw.get("pointattributes", []))

    @property
    def vertex_attributes(self) -> List[Dict[str, Any]]:
        """List of vertex attribute descriptors."""
        return self._normalize_attrs(self._raw.get("vertexattributes", []))

    @property
    def primitive_attributes(self) -> List[Dict[str, Any]]:
        """List of primitive attribute descriptors."""
        return self._normalize_attrs(self._raw.get("primitiveattributes", []))

    @property
    def detail_attributes(self) -> List[Dict[str, Any]]:
        """List of detail attribute descriptors."""
        return self._normalize_attrs(self._raw.get("detailattributes", []))

    @property
    def all_attribute_names(self) -> List[str]:
        """Flat list of all unique attribute names across all domains."""
        seen: Dict[str, bool] = {}
        for domain in ("point", "vertex", "primitive", "detail"):
            for attr in getattr(self, f"{domain}_attributes"):
                name = attr.get("name")
                if name and name not in seen:
                    seen[name] = True
        return list(seen.keys())

    # -- compatibility --

    @property
    def is_compatible_with(self) -> List[str]:
        """Return a list of compatible Houdini versions based on file version."""
        version = self.file_version
        if not version:
            return ["unknown"]
        # Simple heuristic: major.minor version forward-compatible
        # within same major series
        try:
            parts = version.split(".")
            major = int(parts[0])
            return [
                f"Houdini {major}.x",
                f"Houdini {major + 1}.x+",
                f"geo format >= {version}",
            ]
        except (ValueError, IndexError):
            return [f"geo format {version}"]

    # -- raw access --

    @property
    def raw_header(self) -> Dict[str, Any]:
        """The parsed JSON header dictionary."""
        return dict(self._raw)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all parsed metadata to a plain dictionary."""
        return {
            "file_path": str(self.file_path) if self.file_path else None,
            "file_version": self.file_version,
            "has_index": self.has_index,
            "topology": self.topology,
            "time": self.time,
            "point_count": self.point_count,
            "vertex_count": self.vertex_count,
            "primitive_count": self.primitive_count,
            "bounding_box": list(self.bounding_box) if self.bounding_box else None,
            "point_attributes": self.point_attributes,
            "vertex_attributes": self.vertex_attributes,
            "primitive_attributes": self.primitive_attributes,
            "detail_attributes": self.detail_attributes,
            "compatible_with": self.is_compatible_with,
        }

    @staticmethod
    def _normalize_attrs(attrs: Any) -> List[Dict[str, Any]]:
        """Ensure attribute descriptors have name/storage/size/type fields."""
        if not isinstance(attrs, list):
            return []
        out: List[Dict[str, Any]] = []
        for a in attrs:
            if not isinstance(a, dict):
                continue
            entry: Dict[str, Any] = {
                "name": a.get("name", "?"),
                "storage": a.get("storage", a.get("type", "?")),
                "size": a.get("size", 1),
                "domain": a.get("type", "?"),
            }
            storage_meta = STORAGE_TYPE_MAP.get(entry["storage"], {})
            entry["storage_kind"] = storage_meta.get("kind", "?")
            entry["storage_bytes"] = storage_meta.get("bytes", "?")
            # If there is a default value, show it
            defaults = a.get("defaults")
            if defaults is not None:
                if isinstance(defaults, dict):
                    entry["default"] = defaults.get("value")
                else:
                    entry["default"] = defaults
            out.append(entry)
        return out


# ---------------------------------------------------------------------------
# File format detection & JSON extraction
# ---------------------------------------------------------------------------

def _detect_format(raw: bytes) -> Tuple[str, int]:
    """Detect bgeo format from the first bytes.

    Returns (format_name, json_start_offset).
    """
    if raw.startswith(BGEO_SC_MAGIC):
        return "bgeo.sc", len(BGEO_SC_MAGIC)
    if raw.startswith(BGEO_MAGIC):
        return "bgeo", len(BGEO_MAGIC)
    # Fallback: some files start directly with JSON
    stripped = raw.lstrip(b"\x00\x01\x02\x03 ")  # strip leading control chars
    if stripped.startswith(b"{"):
        return "bgeo (raw JSON)", len(raw) - len(stripped)
    raise ValueError(
        "Unrecognized file format: magic bytes do not match 'bgeo' or 'bgeo.sc'. "
        "First 32 bytes: {}".format(raw[:32].hex(" "))
    )


def _find_json_boundary(raw: bytes, start: int) -> int:
    """Find the end of the JSON portion by bracket counting.

    Returns the offset *after* the closing brace of the top-level JSON object.
    """
    depth = 0
    in_string = False
    escape = False
    i = start
    n = len(raw)

    while i < n:
        ch = raw[i : i + 1]
        if escape:
            escape = False
            i += 1
            continue
        if in_string:
            if ch == b"\\":
                escape = True
            elif ch == b'"':
                in_string = False
            i += 1
            continue
        if ch == b'"':
            in_string = True
        elif ch == b"{":
            depth += 1
        elif ch == b"}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1

    raise ValueError(
        "Unterminated JSON object: reached end of data ({:,d} bytes) "
        "with depth={:d}. File may be truncated or corrupted.".format(n, depth)
    )


def _decompress_blosc(raw: bytes) -> bytes:
    """Decompress blosc-compressed data.

    Tries ``blosc2`` first, falls back to legacy ``blosc``.
    """
    try:
        import blosc2
        return blosc2.decompress(raw)
    except ImportError:
        pass
    try:
        import blosc
        return blosc.decompress(raw)
    except ImportError:
        raise ImportError(
            "blosc2 (or legacy blosc) is required to read .bgeo.sc files. "
            "Install with: pip install blosc2"
        ) from None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_bgeo_header(file_path: Path, max_header_bytes: int = MAX_JSON_HEADER_BYTES) -> BgeoInfo:
    """Parse a .bgeo or .bgeo.sc file and return its header metadata.

    This is a **read-only** operation: only the JSON header is parsed.
    Binary geometry data sections are never decompressed or loaded.

    Args:
        file_path: Path to the .bgeo or .bgeo.sc file.
        max_header_bytes: Safety limit on JSON header size (default 256 MB).

    Returns:
        BgeoInfo with parsed metadata.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is not recognized or the JSON is malformed.
        ImportError: If the file is .bgeo.sc and ``blosc2`` is not installed.
    """
    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))

    file_size = file_path.stat().st_size

    # Read enough to detect format and find JSON
    with open(file_path, "rb") as fh:
        peek = fh.read(4096)

    if not peek:
        raise ValueError("File is empty: {}".format(file_path))

    fmt, json_start = _detect_format(peek)

    if fmt == "bgeo.sc":
        # Read entire file (compressed) and decompress
        with open(file_path, "rb") as fh:
            compressed = fh.read()
        if len(compressed) > max_header_bytes * 2:  # generous but safe
            raise ValueError(
                "Compressed file too large for header-only inspection "
                "({:,d} bytes > {:,d} bytes limit)".format(len(compressed), max_header_bytes * 2)
            )
        try:
            raw_json_bytes = _decompress_blosc(compressed[json_start:])
        except Exception as exc:
            raise ValueError(
                "Failed to decompress blosc data from {}: {}".format(file_path.name, exc)
            ) from exc
        if not raw_json_bytes.lstrip().startswith(b"{"):
            raise ValueError(
                "Decompressed bgeo.sc data does not start with JSON object. "
                "First 64 bytes: {}".format(raw_json_bytes[:64].hex(" "))
            )
        json_end = _find_json_boundary(raw_json_bytes, 0)
        json_bytes = raw_json_bytes[:json_end]
        json_text = json_bytes.decode("utf-8")
    elif fmt == "bgeo (raw JSON)":
        with open(file_path, "rb") as fh:
            raw = fh.read(min(file_size, max_header_bytes))
        json_end = _find_json_boundary(raw, json_start)
        json_bytes = raw[json_start:json_end]
        json_text = json_bytes.decode("utf-8")
    else:
        # Standard .bgeo: JSON header follows the magic bytes
        # Read up to max_header_bytes to find the JSON ending
        with open(file_path, "rb") as fh:
            raw = fh.read(min(file_size, max_header_bytes + json_start))

        # Search for JSON start in the peek area
        json_start_actual = raw.find(b"{", json_start)
        if json_start_actual < 0:
            raise ValueError(
                "Cannot find JSON object start in {} after magic bytes".format(file_path.name)
            )

        json_end = _find_json_boundary(raw, json_start_actual)
        json_bytes = raw[json_start_actual:json_end]
        json_text = json_bytes.decode("utf-8")

    # Parse JSON
    try:
        header = json.loads(json_text)
    except json.JSONDecodeError:
        # Try json5 for lenient parsing
        try:
            import json5
            header = json5.loads(json_text)
        except ImportError:
            raise ValueError(
                "Malformed JSON in geometry header of {}. "
                "Install json5 for more lenient parsing: pip install json5".format(file_path.name)
            ) from None

    if not isinstance(header, dict):
        raise ValueError(
            "Expected JSON object at top level of {}, got {}".format(
                file_path.name, type(header).__name__
            )
        )

    return BgeoInfo(header, file_path=file_path)


def inspect_cache(file_path: Path) -> Dict[str, Any]:
    """Convenience wrapper: parse and return a dictionary.

    Args:
        file_path: Path to the .bgeo or .bgeo.sc file.

    Returns:
        Dictionary with all parsed metadata.
    """
    return parse_bgeo_header(file_path).to_dict()


# ---------------------------------------------------------------------------
# Sample file generator (for testing)
# ---------------------------------------------------------------------------

def generate_sample_bgeo_content(
    point_count: int = 8,
    vertex_count: int = 24,
    primitive_count: int = 6,
    file_version: str = "20.0",
    time: Optional[float] = 1.0,
    topology: str = "Poly",
) -> bytes:
    """Generate a minimal valid .bgeo file content for testing.

    This creates a JSON header for a simple geometry (e.g. a cube)
    without actual binary data sections, suitable for parser testing.
    """
    header: Dict[str, Any] = {
        "fileversion": file_version,
        "hasindex": False,
        "pointcount": point_count,
        "vertexcount": vertex_count,
        "primitivecount": primitive_count,
        "topology": topology,
        "pointattributes": [
            {"name": "P", "type": "point", "storage": "fpreal32", "size": 3,
             "defaults": {"value": [0.0, 0.0, 0.0], "size": 3, "storage": "fpreal32"}},
            {"name": "N", "type": "point", "storage": "fpreal32", "size": 3,
             "defaults": {"value": [0.0, 1.0, 0.0], "size": 3, "storage": "fpreal32"}},
            {"name": "uv", "type": "point", "storage": "fpreal32", "size": 3,
             "defaults": {"value": [0.0, 0.0, 0.0], "size": 3, "storage": "fpreal32"}},
            {"name": "Cd", "type": "point", "storage": "fpreal32", "size": 3,
             "defaults": {"value": [1.0, 1.0, 1.0], "size": 3, "storage": "fpreal32"}},
        ],
        "vertexattributes": [
            {"name": "uv", "type": "vertex", "storage": "fpreal32", "size": 3,
             "defaults": {"value": [0.0, 0.0, 0.0], "size": 3, "storage": "fpreal32"}},
        ],
        "primitiveattributes": [],
        "detailattributes": [
            {"name": "bbox", "type": "detail", "storage": "fpreal32", "size": 6,
             "defaults": {"value": [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0],
                          "size": 6, "storage": "fpreal32"}},
        ],
    }
    if time is not None:
        header["time"] = time

    json_text = json.dumps(header, separators=(",", ":"), ensure_ascii=False)
    return BGEO_MAGIC + json_text.encode("utf-8")


def generate_sample_bgeo_sc_content() -> bytes:
    """Generate a minimal valid .bgeo.sc file content for testing.

    Requires ``blosc2`` to compress.
    """
    import blosc2 as _blosc2  # local import so it's optional at module level

    header: Dict[str, Any] = {
        "fileversion": "20.5",
        "hasindex": False,
        "pointcount": 4,
        "vertexcount": 12,
        "primitivecount": 2,
        "topology": "Poly",
        "time": 2.0,
        "pointattributes": [
            {"name": "P", "type": "point", "storage": "fpreal32", "size": 3},
        ],
        "vertexattributes": [],
        "primitiveattributes": [],
        "detailattributes": [],
    }
    json_text = json.dumps(header, separators=(",", ":"), ensure_ascii=False)
    compressed = _blosc2.compress(json_text.encode("utf-8"), typesize=1)
    return BGEO_SC_MAGIC + compressed
