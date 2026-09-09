"""Secure sandboxed document reader tool."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, PermissionLevel, SecurityError, ToolContext
from app.tools.builtin.file_search import get_allowed_dir, validate_sandboxed_path

logger = logging.getLogger("nova.tools.document_reader")

ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml"}


class DocumentReaderInput(BaseModel):
    """Input parameters for reading document contents."""

    file_path: str = Field(description="Relative path of the document inside the allowed sandbox directory")
    max_characters: int = Field(default=8000, ge=100, le=50000, description="Maximum characters to read")


class DocumentReaderTool(BaseTool):
    """Reads the textual content of a document within the authorized sandbox directory."""

    name = "document_reader"
    description = (
        "Read the text content of a supported document (.txt, .md, .json, .csv) inside the authorized sandbox. "
        "Strictly sandboxed against path traversal outside the storage boundary."
    )
    input_schema = DocumentReaderInput
    permission_level = PermissionLevel.LOW
    timeout_seconds = 10.0

    async def execute(self, params: DocumentReaderInput, context: ToolContext | None = None) -> dict[str, Any]:
        allowed_root = get_allowed_dir()
        target_file = allowed_root / params.file_path
        safe_file = validate_sandboxed_path(target_file, allowed_root)

        if not safe_file.exists():
            raise FileNotFoundError(f"File '{params.file_path}' does not exist in the authorized directory.")

        if not safe_file.is_file():
            raise IsADirectoryError(f"Target '{params.file_path}' is a directory, not a readable document.")

        if safe_file.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise SecurityError(
                f"Unsupported file format '{safe_file.suffix}'. "
                f"Supported types: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
            )

        content = safe_file.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > params.max_characters
        extracted_text = content[: params.max_characters]

        return {
            "file_name": safe_file.name,
            "path": safe_file.relative_to(allowed_root).as_posix(),
            "character_count": len(extracted_text),
            "total_length": len(content),
            "is_truncated": truncated,
            "content": extracted_text,
        }
