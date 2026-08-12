# dcc-mcp-cache-inspector

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/dcc-mcp-cache-inspector-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/dcc-mcp-cache-inspector.svg">
    <img src="docs/assets/dcc-mcp-cache-inspector.svg" alt="DCC-MCP · CACHE INSPECTOR" width="600">
  </picture>
</p>

Production-oriented, Houdini-free structural inspection for SideFX `.geo`,
`.bgeo`, and `.bgeo.sc` caches. This repository distributes one host-neutral,
typed DCC-MCP Skill; it is not a DCC adapter, standalone server, CLI, or PyPI
package.

![Compressed geometry cache decoded within bounded limits into privacy-safe counts, bounds, and attribute summaries](docs/images/cache-inspection-showcase.webp)

Illustrative workflow generated with OpenAI ImageGen from the retained source
in `docs/images/sources`; no third-party source assets are present. It depicts only the implemented bounded content detection,
optional SCF/Blosc decoding, structural projection, and read-only verification
path. It is not a Houdini screenshot or host-validation artifact.

## What it returns

- point, vertex, and primitive counts
- geometry format and SideFX file version
- primitive families
- attribute owner, name, storage, tuple size, and element count
- finite position bounds when the `P` payload uses a supported encoding

The result deliberately excludes the free-form `info` block because producers
may write hostnames, usernames, or source paths there. Raw geometry payloads are
never returned.

## Install

```bash
dcc-mcp-cli marketplace install dcc-mcp-cache-inspector --dcc houdini --reload
```

Choose the concrete adapter that owns the workflow; the Skill declares
`metadata.dcc-mcp.dcc: any` and can be installed for other DCCs. Python 3.9 or
newer and `blosc>=1.11.2,<2` are required. Marketplace discovery reports the
runtime requirement but never installs it automatically.

## Typed MCP tools

The bundled `cache-inspection` Skill registers two read-only tools:

- `inspect_cache` for counts, bounds, primitive types, and attribute summaries
- `list_attributes` for attribute definitions only

The Skill executes through the selected concrete DCC sidecar. It does not create
a fake `cache-inspector` DCC type and has no host PID, execution bridge, or
main-thread ownership of its own.

## Supported format boundary

The decoder recognizes content, not filename extensions:

- SideFX ASCII geometry JSON
- SideFX binary JSON used by `.bgeo`
- SCF containers with bounded Blosc blocks used by `.bgeo.sc`

Malformed, truncated, unknown, or oversized inputs fail closed. The default and
hard ceiling is 512 MiB for both input and decoded data. See
[Security](docs/security.md) for the complete trust boundary.

The implementation is original and does not bundle SideFX code. SideFX
documents the Houdini 12+ geometry representation as JSON/binary JSON and
publishes the binary JSON reference separately:

- <https://www.sidefx.com/docs/houdini/io/formats/geo.html>
- <https://www.sidefx.com/docs/hdk/_h_d_k__g_a__using.html>

## Development

```bash
python -m pip install pytest ruff pyyaml blosc dcc-mcp-core
ruff check .
ruff format --check .
pytest
dcc-mcp-cli lint skill/cache-inspection --warnings-as-errors
dcc-mcp-cli marketplace pack skill/cache-inspection --out dist/
```

Architecture and validation details are in [docs/architecture.md](docs/architecture.md).

## License

MIT. See [LICENSE](LICENSE).
