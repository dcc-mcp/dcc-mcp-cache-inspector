"""Typed entry point for structural cache inspection."""

from __future__ import annotations

from _cache_api import inspect_cache
from _result import safe_cache_result
from dcc_mcp_core.skill import run_main, skill_entry


@skill_entry
def main(
    file_path: str,
    max_file_bytes: int = 512 * 1024 * 1024,
    max_decoded_bytes: int = 512 * 1024 * 1024,
) -> dict:
    return safe_cache_result(
        "Cache inspected.",
        lambda: {
            "inspection": inspect_cache(
                file_path,
                max_file_bytes=max_file_bytes,
                max_decoded_bytes=max_decoded_bytes,
            )
        },
    )


if __name__ == "__main__":
    run_main(main)
