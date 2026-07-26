# dcc-mcp-cache-inspector

Fail-closed guard for Houdini `.bgeo` and `.bgeo.sc` cache inspection.

## Status

Cache parsing is disabled. Version 0.1.0 accepted synthetic `b"bgeo" + JSON`
and `b"bgeo.sc" + Blosc(JSON)` envelopes that are not SideFX cache formats.
Real `.bgeo` files use SideFX binary JSON, while `.bgeo.sc` files wrap that
stream in the HSC container. Returning metadata from the synthetic envelopes
could mislead automation, so the API now raises `UnsupportedFormatError` for
every non-empty cache.

Use Houdini's native `ginfo` utility (and `hsc -d` for `.sc`) until a
conforming decoder is implemented and validated against real Houdini fixtures.

```python
from pathlib import Path

from dcc_mcp_cache_inspector import UnsupportedFormatError, parse_bgeo_header

try:
    parse_bgeo_header(Path("cache.bgeo"))
except UnsupportedFormatError as exc:
    print(exc)
```

## Development

```bash
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
python -m build
twine check dist/*
```

## License

MIT. See [LICENSE](LICENSE).
