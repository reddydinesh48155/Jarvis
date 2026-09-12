"""Configurable, location-preserving document chunking."""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.extraction import ExtractedSection, clean_text


@dataclass(frozen=True)
class TextChunk:
    text: str
    chunk_index: int
    page_number: int | None
    section: str | None


def _next_boundary(text: str, start: int, size: int) -> int:
    end = min(len(text), start + size)
    if end == len(text):
        return end
    boundary = text.rfind(" ", start + max(1, size // 2), end)
    return boundary if boundary > start else end


def chunk_sections(
    sections: list[ExtractedSection],
    chunk_size: int,
    overlap: int,
) -> list[TextChunk]:
    """Split sections by character budget with word boundaries and overlap."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks: list[TextChunk] = []
    for section in sections:
        text = clean_text(section.text)
        start = 0
        while start < len(text):
            end = _next_boundary(text, start, chunk_size)
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        chunk_index=len(chunks),
                        page_number=section.page_number,
                        section=section.section,
                    )
                )
            if end >= len(text):
                break
            next_start = max(start + 1, end - overlap)
            start = next_start
    return chunks
