---
name: dcc-mcp-cache-inspector
description: |-
  Inspect Houdini bgeo/bgeo.sc cache files without Houdini. Read-only: extract
  metadata, attribute lists, bounding boxes, version compatibility, and
  topology info from geometry caches.
license: MIT
allowed-tools: Bash Read
metadata:
  dcc-mcp:
    dcc: houdini
    layer: operator
    stage: inspection
    version: 0.1.0
    tags:
    - houdini
    - bgeo
    - cache
    - inspection
    - metadata
    - offline
    - read-only
---

# dcc-mcp-cache-inspector

Read-only offline inspection of Houdini geometry cache files (`.bgeo`,
`.bgeo.sc`). No Houdini license or runtime required — works on any machine
with Python 3.8+.

This is an operator/agent skill. It can be invoked as a standalone CLI tool,
imported as a Python library, or loaded as a marketplace skill.

## What it inspects

| Field                | Description                                     |
|----------------------|-------------------------------------------------|
| File version         | Houdini geometry format version (e.g. `20.0`)   |
| Topology             | Primitive topology type (Poly, Mesh, etc.)      |
| Point / Vertex / Primitive count | Element counts                     |
| Bounding box         | Axis-aligned bounding box from detail attrs     |
| Time                 | Frame time stored in the cache                  |
| Attributes           | Full list: name, storage, size, defaults        |
| Compatibility        | Estimated compatible Houdini versions           |

## Constraints

- **Pure read-only**: parses only the JSON header. Binary geometry data
  sections are never decompressed, deserialized, or executed.
- **No DCC dependency**: works on any machine with Python 3.8+. Houdini is
  *not* required.
- **Format boundary**: only `.bgeo` and `.bgeo.sc` files are supported.
  `.bgeo.sc` requires the optional `blosc2` package.
- **License**: MIT. Blosc is BSD-licensed. No GPL code is involved.

## Quick start

Install the package:

```bash
pip install dcc-mcp-cache-inspector
# For .bgeo.sc support:
pip install dcc-mcp-cache-inspector[blosc]
```

### CLI

```bash
# Full metadata report (human-readable)
dcc-mcp-cache-inspector inspect path/to/cache.bgeo

# JSON output
dcc-mcp-cache-inspector inspect path/to/cache.bgeo --json

# Attributes only
dcc-mcp-cache-inspector attributes path/to/cache.bgeo.sc --json
```

### Python API

```python
from dcc_mcp_cache_inspector import parse_bgeo_header, inspect_cache
from pathlib import Path

# Get structured info object
info = parse_bgeo_header(Path("explosion_001.bgeo.sc"))
print(info.point_count)       # 12345
print(info.file_version)      # "20.0"
print(info.bounding_box)      # (-10.0, -5.0, -3.0, 10.0, 5.0, 8.0)

for attr in info.point_attributes:
    print(f"  {attr['name']}: {attr['storage']} x{attr['size']}")

# Or get a plain dict
data = inspect_cache(Path("explosion_001.bgeo"))
```

## Usage in agents / automation

When an agent needs to inspect a cache file before deciding what tools to
call, use this skill:

1. Call `inspect_cache(path)` to get metadata.
2. Check `point_count`, `primitive_count`, `bounding_box` — choose the right
   processing strategy.
3. Check `file_version` and `is_compatible_with` to warn about version
   mismatches.
4. List `point_attributes` to know what data channels are available.

### Agent prompt template

```text
Inspect the cache at {path} using dcc-mcp-cache-inspector.
- Are there more than 1M points? If so, use the sparse reader.
- Is "Cd" in the point attributes? If so, include vertex colors.
- Is the bounding box within the expected range for this asset?
- Is the file version compatible with Houdini 20.0+?
```

## USD integration

For USD-based caches (`.usd`, `.usda`, `.usdc`), use the existing
`dcc-mcp-openusd` adapter instead. This skill only covers `.bgeo`/`.bgeo.sc`.

When a pipeline mixes USD and bgeo caches, invoke both:
1. `dcc-mcp-cache-inspector` for bgeo cache metadata.
2. `dcc-mcp-openusd` for USD stage/layer introspection.

## Dependencies

| Package      | Required? | License | Purpose                          |
|-------------|-----------|---------|----------------------------------|
| `json5`     | Yes       | Apache 2.0 | Lenient JSON fallback parsing  |
| `blosc2`    | Optional  | BSD     | `.bgeo.sc` decompression       |

`json5` is used as a fallback when the standard `json` module cannot parse
a bgeo JSON header (some older Houdini versions emit trailing commas or
comments in the header JSON).

## Sample files

The test suite includes generated sample `.bgeo` and `.bgeo.sc` files for
regression testing. These are minimal valid files with synthetic geometry
metadata.

To run tests:

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Security

This package reads file headers only. It does not:
- Execute any code from the cache file
- Load native libraries
- Decompress binary geometry data sections
- Open network connections
- Write to the filesystem

The `blosc2` library is the only native dependency (optional) and is used
exclusively to decompress the JSON header of `.bgeo.sc` files.
