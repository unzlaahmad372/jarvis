"""Plugin system — discover and load drop-in Python tool plugins.

Plugins are .py files dropped into data/plugins/.
Each must define a class inheriting BaseTool and expose it as `plugin_tool`.

GET  /api/v1/plugins          — list discovered plugins
POST /api/v1/plugins/reload   — rescan and reload plugins
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])
logger = get_logger(__name__)


class PluginOut(BaseModel):
    name: str
    description: str
    risk_level: str
    file: str
    loaded: bool
    error: str | None = None


def _scan_plugins(plugins_dir: Path) -> list[PluginOut]:
    plugins_dir.mkdir(parents=True, exist_ok=True)
    results: list[PluginOut] = []

    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{path.stem}", path)
            if spec is None or spec.loader is None:
                raise ValueError("Cannot load spec")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)  # noqa: PGH003

            tool = getattr(mod, "plugin_tool", None)
            if tool is None:
                raise ValueError("No 'plugin_tool' attribute found")

            # Register into tool registry
            from app.tools.registry import get_registry
            get_registry().register(tool)

            results.append(PluginOut(
                name=tool.name,
                description=tool.description,
                risk_level=tool.risk_level,
                file=path.name,
                loaded=True,
            ))
            logger.info("plugin_loaded", name=tool.name, file=path.name)
        except Exception as exc:  # noqa: BLE001
            results.append(PluginOut(
                name=path.stem,
                description="",
                risk_level="UNKNOWN",
                file=path.name,
                loaded=False,
                error=str(exc),
            ))
            logger.warning("plugin_load_failed", file=path.name, error=str(exc))

    return results


@router.get("", response_model=list[PluginOut])
async def list_plugins() -> list[PluginOut]:
    settings = get_settings()
    return _scan_plugins(settings.data_dir / "plugins")


@router.post("/reload", response_model=list[PluginOut])
async def reload_plugins() -> list[PluginOut]:
    settings = get_settings()
    # Remove previously loaded plugin modules so they reload fresh
    to_remove = [k for k in sys.modules if k.startswith("jarvis_plugin_")]
    for k in to_remove:
        del sys.modules[k]
    return _scan_plugins(settings.data_dir / "plugins")
