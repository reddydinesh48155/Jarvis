"""Audit logging system for all tool invocations and security checks."""

from __future__ import annotations

import json
import logging
import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.tools.base import PermissionLevel

logger = logging.getLogger("nova.tools.audit")


@dataclass
class AuditLogEntry:
    """Represents a recorded audit log event."""

    id: str
    tool_name: str
    permission_level: str
    user_id: str | None
    input_params: dict[str, Any]
    output_result: Any
    success: bool
    error_message: str | None
    requires_confirmation: bool
    confirmed: bool
    execution_time_ms: float | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


class AuditLogger:
    """Manages audit log recording and querying across memory and persistent database."""

    def __init__(self, max_memory_entries: int = 500, database_timeout_seconds: float = 0.25) -> None:
        self.max_memory_entries = max_memory_entries
        self.database_timeout_seconds = database_timeout_seconds
        self._memory_logs: list[AuditLogEntry] = []

    def clear_memory_logs(self) -> None:
        """Clear in-memory audit logs (primarily for testing)."""
        self._memory_logs.clear()

    def get_recent_logs(self, limit: int = 50) -> list[AuditLogEntry]:
        """Return the most recent audit logs."""
        if limit <= 0:
            return []
        return list(reversed(self._memory_logs[-limit:]))

    async def log_tool_call(
        self,
        tool_name: str,
        user_id: str | None,
        input_params: dict[str, Any] | None,
        output_result: Any,
        success: bool,
        error_message: str | None,
        permission_level: PermissionLevel | str,
        requires_confirmation: bool = False,
        confirmed: bool = False,
        execution_time_ms: float | None = None,
    ) -> AuditLogEntry:
        """Record a tool execution attempt."""
        entry_id = str(uuid4())
        perm_str = (
            permission_level.value
            if isinstance(permission_level, PermissionLevel)
            else str(permission_level)
        )

        entry = AuditLogEntry(
            id=entry_id,
            tool_name=tool_name,
            permission_level=perm_str,
            user_id=user_id,
            input_params=input_params or {},
            output_result=output_result,
            success=success,
            error_message=error_message,
            requires_confirmation=requires_confirmation,
            confirmed=confirmed,
            execution_time_ms=execution_time_ms,
        )

        self._memory_logs.append(entry)
        if len(self._memory_logs) > self.max_memory_entries:
            self._memory_logs.pop(0)

        logger.info(
            "AUDIT LOG: tool=%s user=%s level=%s success=%s confirmed=%s elapsed=%.2fms",
            tool_name,
            user_id or "anonymous",
            perm_str,
            success,
            confirmed,
            execution_time_ms or 0.0,
        )

        # Attempt to persist to database if available
        try:
            from app.db.models import AuditLog
            from app.db.session import SessionLocal

            # Audit persistence is best-effort and must never hold up a voice
            # turn when the optional database is offline.
            async with asyncio.timeout(self.database_timeout_seconds):
                async with SessionLocal() as db:
                    db_record = AuditLog(
                        id=uuid4(),
                        user_id=user_id,
                        tool_name=tool_name,
                        permission_level=perm_str,
                        input_params=json.dumps(input_params or {}, default=str),
                        output_result=json.dumps(output_result, default=str)
                        if output_result is not None
                        else None,
                        success=success,
                        error_message=error_message,
                        requires_confirmation=requires_confirmation,
                        confirmed=confirmed,
                        execution_time_ms=execution_time_ms,
                    )
                    db.add(db_record)
                    await db.commit()
        except Exception as exc:
            # Don't fail tool execution if database is unreachable (e.g. SQLite test without migration or offline)
            logger.debug("could not write audit log to database: %s", exc)

        return entry


# Global singleton instance
audit_logger = AuditLogger()
