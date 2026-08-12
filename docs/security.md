# Security

Cache files are untrusted input. Cache Inspector provides a read-only structural
view, not a general-purpose geometry deserializer.

## Guarantees

- no cache-controlled code evaluation, imports, subprocesses, or DCC launches;
  Skill entry points load only their own fixed packaged parser file
- no cache mutation or output-file creation
- no symlink traversal performed beyond the caller-selected resolved path
- bounded input, decompression, nesting, strings, token tables, structures, and
  expanded arrays
- strict UTF-8 and token/length validation
- no free-form `info` data or raw geometry values in results
- structured, non-traceback Skill errors for expected invalid inputs

## Privacy boundary

The `info` section may contain producer metadata such as a machine name, user,
or HIP/source path. The parser never projects that section into public results.
Attribute names and schema are returned because they are part of the requested
geometry contract; callers should still treat custom attribute names as project
metadata.

## Limits

Input and decoded ceilings default to 512 MiB and cannot be raised above that
value through the public API or typed tools. Large studio caches should be
inspected with a trusted native indexing workflow rather than weakening these
limits.

## Reporting

Report security issues privately to the repository maintainers. Do not attach
proprietary cache files to public issues.
