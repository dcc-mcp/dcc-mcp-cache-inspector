---
name: cache-inspection
description: Inspect SideFX .geo, .bgeo, and .bgeo.sc geometry caches offline with bounded read-only tools. Use for cache counts, bounds, primitive families, and attribute definitions when Houdini is unavailable. Never exposes the cache info block, embedded hostnames, users, or source paths.
metadata:
  dcc-mcp:
    dcc: cache-inspector
    layer: infrastructure
    compatibility: "Python 3.9+, dcc-mcp-core 0.19.91+"
    version: "0.2.0" # x-release-please-version
    tags: [pipeline, read-only, houdini, cache]
    search-hint: "offline Houdini bgeo bgeo.sc geo cache inspect point primitive vertex counts bounds attributes read-only no Houdini"
    tools: tools.yaml
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

Inputs default to a 512 MiB file and decoded-data ceiling. Raise neither limit
beyond the schema maximum; split a production cache or use a studio-native
indexing workflow when a file exceeds the bounded inspection contract.
