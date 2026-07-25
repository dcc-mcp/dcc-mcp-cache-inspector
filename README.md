# dcc-mcp-cache-inspector

Read-only bgeo/bgeo.sc offline cache inspection — no Houdini required.

Extract metadata, attribute lists, bounding boxes, topology info, and
version compatibility from Houdini geometry caches on any machine with
Python 3.8+.

## Quick Start

```bash
pip install dcc-mcp-cache-inspector

# CLI
dcc-mcp-cache-inspector inspect my_cache.bgeo

# Python
python -c "
from dcc_mcp_cache_inspector import parse_bgeo_header
from pathlib import Path
info = parse_bgeo_header(Path('my_cache.bgeo'))
print(info.point_count, info.file_version)
"
```

## .bgeo.sc Support

Install the optional blosc dependency:

```bash
pip install dcc-mcp-cache-inspector[blosc]
```

## Format Support

| Format    | Extension   | Required Deps      |
|-----------|-------------|--------------------|
| bgeo      | `.bgeo`     | None (stdlib only) |
| bgeo.sc   | `.bgeo.sc`  | `blosc2` (optional) |

## License

MIT. See [LICENSE](LICENSE).
