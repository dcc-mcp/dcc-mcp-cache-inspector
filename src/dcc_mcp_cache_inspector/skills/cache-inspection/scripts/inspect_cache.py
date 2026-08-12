"""Typed entry point for structural cache inspection."""

from __future__ import annotations

from _cache_api import inspect_cache
from dcc_mcp_core.skill import run_main, skill_entry, skill_success


@skill_entry
def main(
    file_path: str,
    max_file_bytes: int = 512 * 1024 * 1024,
    max_decoded_bytes: int = 512 * 1024 * 1024,
) -> dict:
    inspection = inspect_cache(
        file_path,
        max_file_bytes=max_file_bytes,
        max_decoded_bytes=max_decoded_bytes,
    )
    return skill_success("Cache inspected.", inspection=inspection)


if __name__ == "__main__":
    run_main(main)
