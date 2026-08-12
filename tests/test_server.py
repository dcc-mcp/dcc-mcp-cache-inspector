"""Standalone composition and Skill contract tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dcc_mcp_core import validate_skill

from dcc_mcp_cache_inspector.server import CacheInspectorMcpServer, _configure_skill_python


def test_skill_python_defaults_to_the_active_environment(monkeypatch) -> None:
    monkeypatch.delenv("DCC_MCP_PYTHON_EXECUTABLE", raising=False)

    _configure_skill_python()

    assert os.environ["DCC_MCP_PYTHON_EXECUTABLE"] == sys.executable


def test_explicit_skill_python_is_preserved(monkeypatch) -> None:
    monkeypatch.setenv("DCC_MCP_PYTHON_EXECUTABLE", "C:/explicit/python.exe")

    _configure_skill_python()

    assert os.environ["DCC_MCP_PYTHON_EXECUTABLE"] == "C:/explicit/python.exe"


def test_server_is_standalone_and_uses_dynamic_port(tmp_path: Path) -> None:
    server = CacheInspectorMcpServer(
        port=0,
        registry_dir=str(tmp_path / "registry"),
        enable_gateway_failover=False,
        enable_file_logging=False,
        enable_telemetry=False,
    )

    assert server._options.instance_type == "standalone"
    assert server._options.dcc_name == "cache-inspector"
    assert server._options.port == 0
    assert server._options.diagnostics.dcc_pid is None


def test_bundled_skill_validates_without_issues() -> None:
    skill = Path(__file__).parents[1] / "src" / "dcc_mcp_cache_inspector" / "skills" / "cache-inspection"

    report = validate_skill(str(skill))

    assert not report.has_errors
    assert not report.issues
