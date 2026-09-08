"""
Auto-discovering tool registry.

Any module dropped anywhere under app/tools/ (including subfolders like
app/tools/finance/) that exports:
    MANIFEST = {"name": ..., "description": ..., "input_schema": {...}}
    async def <name-matching-MANIFEST>(...) -> ...
is picked up automatically at import time. No edits needed here,
in schemas/planner.py, or in prompts/planner_prompt.py — those two now
read from TOOLS / TOOL_MANIFESTS instead of hardcoding tool names.

A malformed tool module (missing MANIFEST, missing matching function,
import error) is skipped with a logged warning rather than crashing
the whole app at startup.
"""

import importlib
import logging
import pkgutil

import app.tools as tools_pkg

logger = logging.getLogger(__name__)

TOOLS: dict = {}
TOOL_MANIFESTS: dict = {}


def _walk_modules(package):
    """Recursively yield full dotted module names under `package`,
    so tools can live directly in app/tools/ or in subfolders like
    app/tools/finance/."""
    for module_info in pkgutil.walk_packages(package.__path__, prefix=package.__name__ + "."):
        yield module_info.name


def _discover():
    for module_name in _walk_modules(tools_pkg):
        if module_name.endswith(".registry"):
            continue
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            logger.warning("Skipping tool module '%s' — import failed: %s", module_name, e)
            continue

        manifest = getattr(module, "MANIFEST", None)
        if manifest is None:
            continue  # not a tool module (e.g. __init__.py, a helper file)

        name = manifest.get("name")
        func = getattr(module, name, None) if name else None

        if not name or func is None:
            logger.warning(
                "Skipping tool module '%s' — MANIFEST['name'] must match an "
                "async function defined in the same file.",
                module_name,
            )
            continue

        if name in TOOLS:
            logger.warning(
                "Duplicate tool name '%s' from '%s' — keeping the first one registered.",
                name, module_name,
            )
            continue

        TOOLS[name] = func
        TOOL_MANIFESTS[name] = manifest
        logger.info("Registered tool: %s (from %s)", name, module_name)


_discover()
