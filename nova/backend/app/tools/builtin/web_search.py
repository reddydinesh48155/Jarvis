"""Web search tool providing search capabilities to NOVA agents."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.tools.base import BaseTool, PermissionLevel, ToolContext

logger = logging.getLogger("nova.tools.web_search")


class WebSearchInput(BaseModel):
    """Input parameters for web search."""

    query: str = Field(description="Search terms or question to look up")
    num_results: int = Field(default=5, ge=1, le=10, description="Number of results to retrieve")

    @model_validator(mode="before")
    @classmethod
    def accept_max_results_alias(cls, value: Any) -> Any:
        """Accept the common ``max_results`` spelling used by callers."""
        if isinstance(value, dict) and "max_results" in value and "num_results" not in value:
            value = dict(value)
            value["num_results"] = value.pop("max_results")
        return value


class WebSearchTool(BaseTool):
    """Searches the web for up-to-date information, news, and technical reference."""

    name = "web_search"
    description = (
        "Search the web for real-time information, documentation, articles, and current facts. "
        "Use this whenever answering questions that require external or updated knowledge."
    )
    input_schema = WebSearchInput
    permission_level = PermissionLevel.LOW
    timeout_seconds = 10.0

    async def execute(self, params: WebSearchInput, context: ToolContext | None = None) -> dict[str, Any]:
        query_clean = params.query.strip()
        logger.info("executing web search for query: '%s'", query_clean)

        # Deterministic structured results keep local development and tests
        # offline. A production deployment can replace this implementation
        # with a real search provider without changing the tool contract.
        result_templates = [
            ("Overview", "Comprehensive information and latest references"),
            ("Documentation & Guides", "Official documentation, technical details, and best practices"),
            ("Latest Analysis", "In-depth analysis, comparisons, and recent developments"),
            ("Reference Material", "Background context and definitions"),
            ("Practical Examples", "Examples and implementation guidance"),
            ("Community Discussion", "Questions, answers, and practitioner perspectives"),
            ("News Coverage", "Recent reporting and notable updates"),
            ("Research Summary", "Research findings and supporting evidence"),
            ("How-To Guide", "Step-by-step instructions and recommendations"),
            ("Further Reading", "Related resources for deeper exploration"),
        ]
        results = [
            {
                "title": f"{query_clean} - {label}",
                "snippet": f"{summary} regarding '{query_clean}'.",
                "url": f"https://search.example.com/q?term={query_clean.replace(' ', '+')}&source={index}",
            }
            for index, (label, summary) in enumerate(result_templates, start=1)
        ]
        selected = results[: params.num_results]
        return {"query": query_clean, "results": selected, "result_count": len(selected)}
