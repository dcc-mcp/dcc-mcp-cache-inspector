# Architecture

## Contract

Cache Inspector is a standalone DCC-MCP adapter. It owns cache decoding and
privacy-safe summarization; `dcc-mcp-core` owns discovery, Skill loading, job
execution, HTTP/MCP transport, and registry integration.

```text
cache file
  -> bounded file read
  -> content detection
  -> optional bounded SCF/Blosc decode
  -> bounded ASCII or binary JSON decode
  -> privacy-safe structural projection
  -> CLI JSON or typed DCC-MCP result
```

No step launches Houdini, evaluates cache content, mutates the input, or returns
raw point/primitive data.

## Components

- `bgeo_parser.py` owns format recognition, bounded decoding, validation, and
  structural summaries.
- `skills/cache-inspection` defines the typed, read-only MCP contract.
- `server.py` composes the Skill with `DccServerBase` as a standalone instance.
- `cli.py` provides local inspection and service lifecycle commands.

The standalone server defaults `DCC_MCP_PYTHON_EXECUTABLE` to its active
interpreter so Skill subprocesses use the same installed dependencies. An
explicit operator-provided value is preserved.

## Resource model

The parser checks input size before reading, checks every SCF block before
decompression, caps decoded bytes, nesting, strings, structural entries, token
tables, and expanded uniform arrays. Truncated input, unknown tokens, invalid
UTF-8, inconsistent lengths, and non-finite bounds fail closed or omit bounds
with an explicit warning.

## Compatibility

The public package supports Python 3.9+. Runtime type annotations avoid PEP 604
unions so `typing.get_type_hints` consumers remain compatible on Python 3.9.
The server composes against `dcc-mcp-core` 0.19.91 or newer.

## Validation

Tests use an independent minimal binary-JSON fixture writer, SCF/Blosc fixtures,
adversarial truncation and allocation cases, Skill schema validation, and
standalone-server contract checks. Release acceptance additionally compares
`.bgeo` and `.bgeo.sc` summaries exported from a real Houdini host and installs
the built wheel into a clean environment.
