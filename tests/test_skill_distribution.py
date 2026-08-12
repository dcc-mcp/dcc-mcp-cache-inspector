"""Distribution-boundary tests for the host-neutral Cache Inspection Skill."""

from __future__ import annotations

from pathlib import Path

import yaml
from dcc_mcp_core import validate_skill

ROOT = Path(__file__).parents[1]
SKILL = ROOT / "skill" / "cache-inspection"


def test_distribution_is_a_self_contained_host_neutral_skill() -> None:
    assert (SKILL / "SKILL.md").is_file()
    assert (SKILL / "tools.yaml").is_file()
    assert (SKILL / "scripts" / "_bgeo_parser.py").is_file()
    assert not (ROOT / "src" / "dcc_mcp_cache_inspector" / "server.py").exists()

    metadata = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "dcc: any" in metadata
    assert "dcc: cache-inspector" not in metadata


def test_required_blosc_runtime_is_declared() -> None:
    metadata = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "type: python_package" in metadata
    assert "module: blosc" in metadata
    assert "optional: false" in metadata


def test_skill_validates_without_warnings() -> None:
    report = validate_skill(str(SKILL))
    assert not report.has_errors
    assert not report.issues


def test_tools_remain_read_only_and_closed_schema() -> None:
    tools = yaml.safe_load((SKILL / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    assert [tool["name"] for tool in tools] == ["inspect_cache", "list_attributes"]
    for tool in tools:
        assert tool["annotations"]["read_only_hint"] is True
        assert tool["annotations"]["destructive_hint"] is False
        assert tool["input_schema"]["additionalProperties"] is False


def test_repository_has_no_adapter_cli_or_pypi_release_contract() -> None:
    assert not (ROOT / "src" / "dcc_mcp_cache_inspector" / "server.py").exists()
    assert not (ROOT / "src" / "dcc_mcp_cache_inspector" / "cli.py").exists()
    assert not (ROOT / ".github" / "workflows" / "release.yml").exists()

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "dcc_mcp.adapters" not in pyproject
    assert "project.scripts" not in pyproject
