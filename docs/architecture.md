# Architecture

## Contract

Cache Inspection is a host-neutral DCC-MCP Skill. It owns cache decoding and
privacy-safe summarization; the selected concrete adapter and `dcc-mcp-core`
own discovery, Skill loading, job execution, HTTP/MCP transport, and registry
integration.

```text
cache file
  -> bounded file read
  -> content detection
  -> optional bounded SCF/Blosc decode
  -> bounded ASCII or binary JSON decode
  -> privacy-safe structural projection
  -> typed DCC-MCP result
```

No step launches Houdini, evaluates cache content, mutates the input, or returns
raw point/primitive data.

## Components

- `skill/cache-inspection/scripts/_bgeo_parser.py` owns format recognition,
  bounded decoding, validation, and
  structural summaries.
- `skill/cache-inspection` defines the typed, read-only, `dcc: any` contract.
- the marketplace installs the Skill for an explicit concrete DCC and reports
  the required `blosc` runtime without resolving it.

## Resource model

The parser checks input size before reading, checks every SCF block before
decompression, caps decoded bytes, nesting, strings, structural entries, token
tables, and expanded uniform arrays. Truncated input, unknown tokens, invalid
UTF-8, inconsistent lengths, and non-finite bounds fail closed or omit bounds
with an explicit warning.

## Compatibility

The Skill supports Python 3.9+ and `dcc-mcp-core` 0.20.3+. Runtime type
annotations avoid PEP 604 unions so `typing.get_type_hints` consumers remain
compatible on Python 3.9.

## Validation

Tests use an independent minimal binary-JSON fixture writer, SCF/Blosc fixtures,
adversarial truncation and allocation cases, strict Skill schema validation,
standalone script execution, and marketplace archive inspection. Acceptance
additionally compares `.bgeo` and `.bgeo.sc` summaries exported from a real
Houdini host.
