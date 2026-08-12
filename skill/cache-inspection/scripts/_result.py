"""Privacy-bounded result envelope for cache inspection tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict

from dcc_mcp_core.skill import skill_error, skill_success


def safe_cache_result(message: str, operation: Callable[[], Dict[str, Any]]):
    try:
        return skill_success(message, **operation())
    except Exception as error:
        return skill_error(
            "Cache inspection failed.",
            type(error).__name__,
            error_type=type(error).__name__,
            prompt="Verify the local cache path, format, dependency, and configured size limits.",
        )
