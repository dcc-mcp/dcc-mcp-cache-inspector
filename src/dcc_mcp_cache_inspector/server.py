"""Standalone DCC-MCP composition root for offline cache inspection."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from dcc_mcp_core import DccServerOptions, MinimalModeConfig
from dcc_mcp_core.server_base import DccServerBase

from dcc_mcp_cache_inspector.__version__ import __version__

logger = logging.getLogger(__name__)

SERVER_NAME = "dcc-mcp-cache-inspector"
_DCC_NAME = "cache-inspector"
_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _configure_skill_python() -> None:
    """Keep Skill subprocesses inside the adapter's installed environment."""
    os.environ.setdefault("DCC_MCP_PYTHON_EXECUTABLE", sys.executable)


class CacheInspectorMcpServer(DccServerBase):
    """A standalone service with no DCC process or host-thread dependency."""

    def __init__(
        self,
        port: Optional[int] = None,
        extra_skill_paths: Optional[list[str]] = None,
        gateway_port: Optional[int] = None,
        registry_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        _configure_skill_python()
        self._extra_skill_paths = list(extra_skill_paths or [])
        options = DccServerOptions.from_env(
            _DCC_NAME,
            _BUILTIN_SKILLS_DIR,
            port=port,
            server_name=SERVER_NAME,
            server_version=__version__,
            adapter_version=__version__,
            dcc_version=__version__,
            instance_type="standalone",
            standalone_main_thread=False,
            gateway_port=gateway_port,
            registry_dir=registry_dir,
            **kwargs,
        )
        super().__init__(options=options)

    def _version_string(self) -> str:
        return __version__

    @property
    def port(self) -> int:
        if self._handle is not None:
            return int(self._handle.port)
        return int(self._options.port)

    @property
    def mcp_url(self) -> str:
        return "http://127.0.0.1:{}/mcp".format(self.port)

    def register_builtin_actions(
        self,
        extra_skill_paths: Optional[list[str]] = None,
        include_bundled: bool = True,
        minimal_mode: Optional[MinimalModeConfig] = None,
    ) -> None:
        if minimal_mode is None:
            minimal_mode = MinimalModeConfig(skills=("cache-inspection",))
        paths = list(self._extra_skill_paths)
        if extra_skill_paths:
            paths.extend(extra_skill_paths)
        super().register_builtin_actions(
            extra_skill_paths=paths,
            include_bundled=include_bundled,
            minimal_mode=minimal_mode,
        )


_server_instance: Optional[CacheInspectorMcpServer] = None


def get_server() -> Optional[CacheInspectorMcpServer]:
    return _server_instance


def start_server(
    port: Optional[int] = None,
    extra_skill_paths: Optional[list[str]] = None,
    gateway_port: Optional[int] = None,
    registry_dir: Optional[str] = None,
    **kwargs: Any,
) -> CacheInspectorMcpServer:
    """Start the process-wide standalone server instance."""
    global _server_instance
    if _server_instance is None:
        server = CacheInspectorMcpServer(
            port=port,
            extra_skill_paths=extra_skill_paths,
            gateway_port=gateway_port,
            registry_dir=registry_dir,
            **kwargs,
        )
        server.register_builtin_actions()
        server.start()
        _server_instance = server
        logger.info("Cache Inspector MCP server started")
    return _server_instance


def stop_server() -> None:
    """Stop and clear the process-wide server instance."""
    global _server_instance
    if _server_instance is not None:
        _server_instance.stop()
        _server_instance = None
