"""Runtime-scoped access to the parser bundled beside this Skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the fixed parser file owned by this exact Skill package. Core executes
# Skill scripts with a shared Python runner, whose ambient environment may also
# contain an unrelated editable checkout with the same distribution name.
_MODULE_NAME = "_dcc_mcp_cache_inspector_bgeo_parser"
_MODULE_PATH = Path(__file__).resolve().parents[3] / "bgeo_parser.py"
_SPEC = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - importlib invariant
    raise ImportError("Unable to load the bundled Cache Inspector parser")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_MODULE_NAME] = _MODULE
_SPEC.loader.exec_module(_MODULE)

inspect_cache = _MODULE.inspect_cache
list_cache_attributes = _MODULE.list_cache_attributes

__all__ = ["inspect_cache", "list_cache_attributes"]
