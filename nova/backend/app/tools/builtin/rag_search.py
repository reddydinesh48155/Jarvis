"""Native LOW-risk tool for user-scoped document retrieval."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.db import session as db_session
from app.rag.service import RAGService
from app.tools.base import BaseTool, PermissionLevel, SecurityError, ToolContext


class RAGSearchInput(BaseModel):
    query: str = Field(min_length=1, description="Question or search query for indexed documents")
    top_k: int = Field(default=4, ge=1, le=10, description="Maximum number of source chunks")
    filename: str | None = Field(default=None, description="Optional filename filter")


class RAGSearchTool(BaseTool):
    """Search indexed user documents using hybrid vector and keyword ranking."""

    name = "RAG_search"
    description = (
        "Search the authenticated user's uploaded documents and return grounded source passages. "
        "Use for questions about personal files, policies, notes, or indexed knowledge."
    )
    input_schema = RAGSearchInput
    permission_level = PermissionLevel.LOW
    timeout_seconds = 20.0

    def __init__(self, rag_service: RAGService | None = None) -> None:
        self.rag_service = rag_service or RAGService()

    async def execute(self, params: RAGSearchInput, context: ToolContext | None = None) -> dict[str, Any]:
        if context is None or not context.user_id:
            raise SecurityError("RAG search requires an authenticated user context")
        # Validate the identifier before opening a database session so an agent
        # cannot turn this tool into an unscoped query.
        owner_id = UUID(str(context.user_id))
        hits = await self.rag_service.search_for_user(
            user_id=owner_id,
            query=params.query,
            top_k=params.top_k,
            filename=params.filename,
        )
        sources = [hit.to_dict() for hit in hits]
        return {
            "query": params.query,
            "source_count": len(sources),
            "sources": sources,
            "results": sources,
        }
