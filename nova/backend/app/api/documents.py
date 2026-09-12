"""Authenticated document upload and management endpoints for Part 6 RAG."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.rag.extraction import SUPPORTED_EXTENSIONS, UnsupportedDocumentType, document_extension
from app.rag.service import DocumentSummary, RAGService


router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    uploaded_at: str
    chunk_count: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


def get_rag_service() -> RAGService:
    """Dependency hook kept separate so tests and deployments can inject providers."""
    return RAGService()


def _response(summary: DocumentSummary) -> DocumentResponse:
    return DocumentResponse(
        id=summary.id,
        filename=summary.filename,
        content_type=summary.content_type,
        size_bytes=summary.size_bytes,
        status=summary.status,
        uploaded_at=summary.uploaded_at.isoformat(),
        chunk_count=summary.chunk_count,
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rag_service: RAGService = Depends(get_rag_service),
) -> DocumentResponse:
    filename = file.filename or ""
    if document_extension(filename) not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported document types are PDF, TXT, DOCX, and Markdown.",
        )
    data = await file.read(settings.rag_max_file_size_bytes + 1)
    if len(data) > settings.rag_max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Documents must be smaller than {settings.rag_max_file_size_bytes} bytes.",
        )
    try:
        summary = await rag_service.index_document(
            db=db,
            user_id=current_user.id,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
    except (UnsupportedDocumentType, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return _response(summary)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rag_service: RAGService = Depends(get_rag_service),
) -> DocumentListResponse:
    documents = await rag_service.list_documents(db, current_user.id)
    return DocumentListResponse(documents=[_response(document) for document in documents])


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    rag_service: RAGService = Depends(get_rag_service),
) -> None:
    deleted = await rag_service.delete_document(db, current_user.id, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
