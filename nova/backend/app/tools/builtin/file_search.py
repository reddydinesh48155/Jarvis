"""Secure sandboxed file search tool."""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.tools.base import BaseTool, PermissionLevel, SecurityError, ToolContext

logger = logging.getLogger("nova.tools.file_search")


class FileSearchInput(BaseModel):
    """Input parameters for file searching."""

    pattern: str = Field(description="Glob pattern to search for (e.g. '*.txt', '*report*', '*.py')")
    subfolder: str = Field(default="", description="Optional relative subfolder within the allowed sandbox")


def get_allowed_dir() -> Path:
    """Resolve and ensure the allowed sandbox directory exists."""
    allowed_path = Path(settings.allowed_tools_dir).resolve()
    allowed_path.mkdir(parents=True, exist_ok=True)
    return allowed_path


def validate_sandboxed_path(target_path: Path, allowed_root: Path) -> Path:
    """Ensure target path is strictly within the allowed root directory."""
    resolved_target = target_path.resolve()
    try:
        resolved_target.relative_to(allowed_root)
    except ValueError:
        raise SecurityError(
            f"Access denied: '{target_path}' is outside the authorized sandbox directory '{allowed_root}'."
        )
    return resolved_target


class FileSearchTool(BaseTool):
    """Searches for files matching a pattern within the secure allowed directory."""

    name = "file_search"
    description = (
        "Search for files by pattern within the secure allowed storage directory. "
        "Strictly sandboxed to prevent unauthorized filesystem access."
    )
    input_schema = FileSearchInput
    permission_level = PermissionLevel.LOW
    timeout_seconds = 10.0

    async def execute(self, params: FileSearchInput, context: ToolContext | None = None) -> list[dict[str, Any]]:
        allowed_root = get_allowed_dir()
        target_dir = allowed_root / params.subfolder
        safe_dir = validate_sandboxed_path(target_dir, allowed_root)

        if not safe_dir.exists() or not safe_dir.is_dir():
            return []

        pattern = params.pattern.strip() or "*"
        matches: list[dict[str, Any]] = []

        for root, _, filenames in os.walk(safe_dir):
            for filename in filenames:
                if fnmatch.fnmatch(filename, pattern):
                    full_path = Path(root) / filename
                    # Do not expose metadata for a symlink that points beyond
                    # the sandbox, even though os.walk does not follow it.
                    if full_path.is_symlink():
                        continue
                    rel_path = full_path.relative_to(allowed_root).as_posix()
                    matches.append({
                        "name": filename,
                        "path": rel_path,
                        "size_bytes": full_path.stat().st_size,
                        "extension": full_path.suffix.lower(),
                    })
                    if len(matches) >= 50:
                        break
            if len(matches) >= 50:
                break

        return matches
