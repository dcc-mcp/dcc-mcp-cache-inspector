---
name: cache-inspection
description: Inspect SideFX .geo, .bgeo, and .bgeo.sc geometry caches offline with bounded read-only tools. Use for cache counts, bounds, primitive families, and attribute definitions from any DCC workflow. Never exposes the cache info block, embedded hostnames, users, or source paths.
license: MIT
metadata:
  dcc-mcp:
    dcc: any
    layer: infrastructure
    compatibility: "Python 3.9+, dcc-mcp-core 0.20.3+"
    version: "0.3.0"
    tags: [pipeline, read-only, houdini, cache]
    search-hint: "offline Houdini bgeo bgeo.sc geo cache inspect point primitive vertex counts bounds attributes read-only no Houdini"
    tools: tools.yaml
    runtimes:
      - name: python-blosc
        type: python_package
        package: blosc
        module: blosc
        optional: false
        feature_level: scf-compression
        install_hint: "python -m pip install 'blosc>=1.11.2,<2'"
---

# Cache Inspection

Use this Skill for bounded, read-only inspection of SideFX geometry caches.
It recognizes ASCII geometry JSON, SideFX binary JSON, and SCF/Blosc
compression by content rather than trusting a filename extension.

Start with `inspect_cache`. Use `list_attributes` when only attribute owner,
name, storage, tuple size, and element counts are needed.

The tools intentionally omit the free-form cache `info` block because it can
contain producer hostnames, usernames, and source paths. They never evaluate
code, mutate a cache, or require a Houdini installation.

This is a host-neutral `dcc: any` Skill, not a DCC adapter. Install it from the
DCC-MCP marketplace and load it into the concrete adapter that owns the current
workflow. The marketplace reports the required `blosc` Python runtime but does
not install dependencies automatically.

Inputs default to a 512 MiB file and decoded-data ceiling. Raise neither limit
beyond the schema maximum; split a production cache or use a studio-native
indexing workflow when a file exceeds the bounded inspection contract.
