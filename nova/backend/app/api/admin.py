"""Admin-only API endpoints for audit logs and user management."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_admin
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.tools.audit import audit_logger


router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Response Schemas ────────────────────────────────────────────────


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tool_name: str
    permission_level: str
    user_id: str | None
    success: bool
    error_message: str | None
    requires_confirmation: bool
    confirmed: bool
    execution_time_ms: float | None
    created_at: datetime | None = None
    timestamp: datetime | None = None


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogResponse]
    total: int


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


# ─── Endpoints ───────────────────────────────────────────────────────


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tool_name: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> AuditLogListResponse:
    """Return audit logs. Tries DB first, falls back to in-memory logs."""
    try:
        query = select(AuditLog).order_by(AuditLog.created_at.desc())
        count_query = select(func.count()).select_from(AuditLog)

        if tool_name:
            query = query.where(AuditLog.tool_name == tool_name)
            count_query = count_query.where(AuditLog.tool_name == tool_name)
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
            count_query = count_query.where(AuditLog.user_id == user_id)

        total = await db.scalar(count_query) or 0
        results = (await db.execute(query.offset(offset).limit(limit))).scalars().all()

        logs = [
            AuditLogResponse(
                id=str(r.id),
                tool_name=r.tool_name,
                permission_level=r.permission_level,
                user_id=r.user_id,
                success=r.success,
                error_message=r.error_message,
                requires_confirmation=r.requires_confirmation,
                confirmed=r.confirmed,
                execution_time_ms=r.execution_time_ms,
                created_at=r.created_at,
            )
            for r in results
        ]
        return AuditLogListResponse(logs=logs, total=total)
    except Exception:
        # Fall back to in-memory logs if DB table doesn't exist
        memory_logs = audit_logger.get_recent_logs(limit=limit + offset)

        filtered = memory_logs
        if tool_name:
            filtered = [l for l in filtered if l.tool_name == tool_name]
        if user_id:
            filtered = [l for l in filtered if l.user_id == user_id]

        total = len(filtered)
        page = filtered[offset : offset + limit]
        logs = [
            AuditLogResponse(
                id=l.id,
                tool_name=l.tool_name,
                permission_level=l.permission_level,
                user_id=l.user_id,
                success=l.success,
                error_message=l.error_message,
                requires_confirmation=l.requires_confirmation,
                confirmed=l.confirmed,
                execution_time_ms=l.execution_time_ms,
                timestamp=l.timestamp,
            )
            for l in page
        ]
        return AuditLogListResponse(logs=logs, total=total)


@router.get("/users", response_model=UserListResponse)
async def list_users(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """List all registered users (admin only)."""
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    results = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    users = [UserResponse.model_validate(u) for u in results]
    return UserListResponse(users=users, total=total)

