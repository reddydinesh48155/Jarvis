"""Authenticated memory management endpoints for Part 7 memory system."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.memory.long_term import LongTermMemory


router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content: str
    category: str
    source_session_id: str | None
    created_at: str
    last_accessed_at: str | None


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    memory_enabled: bool


class MemorySettingsRequest(BaseModel):
    memory_enabled: bool


class MemorySettingsResponse(BaseModel):
    memory_enabled: bool


def _get_long_term_memory() -> LongTermMemory:
    """Dependency hook kept separate so tests can inject providers."""
    return LongTermMemory()


def _format_memory(mem: object) -> MemoryResponse:
    """Convert a UserMemory ORM instance to a response model."""
    return MemoryResponse(
        id=mem.id,  # type: ignore[attr-defined]
        content=mem.content,  # type: ignore[attr-defined]
        category=mem.category,  # type: ignore[attr-defined]
        source_session_id=mem.source_session_id,  # type: ignore[attr-defined]
        created_at=mem.created_at.isoformat() if mem.created_at else "",  # type: ignore[attr-defined]
        last_accessed_at=(
            mem.last_accessed_at.isoformat()  # type: ignore[attr-defined]
            if mem.last_accessed_at  # type: ignore[attr-defined]
            else None
        ),
    )


@router.get("", response_model=MemoryListResponse, status_code=status.HTTP_200_OK)
async def list_memories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ltm: LongTermMemory = Depends(_get_long_term_memory),
) -> MemoryListResponse:
    """List all long-term memories for the authenticated user."""
    memories = await ltm.list_all(db, current_user.id)
    enabled = await ltm.get_settings(db, current_user.id)
    return MemoryListResponse(
        memories=[_format_memory(m) for m in memories],
        memory_enabled=enabled,
    )


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_memory(
    memory_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ltm: LongTermMemory = Depends(_get_long_term_memory),
) -> None:
    """Delete a specific memory entry. Verifies ownership."""
    deleted = await ltm.delete_one(db, current_user.id, memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found or not owned by the current user.",
        )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_memories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ltm: LongTermMemory = Depends(_get_long_term_memory),
) -> None:
    """Delete all memories for the authenticated user."""
    await ltm.delete_all(db, current_user.id)


@router.patch(
    "/settings",
    response_model=MemorySettingsResponse,
    status_code=status.HTTP_200_OK,
)
async def update_memory_settings(
    body: MemorySettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ltm: LongTermMemory = Depends(_get_long_term_memory),
) -> MemorySettingsResponse:
    """Toggle the memory system on or off for the authenticated user."""
    row = await ltm.update_settings(db, current_user.id, body.memory_enabled)
    return MemorySettingsResponse(memory_enabled=row.memory_enabled)

