from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.memory import router as memory_router
from app.api.voice import router as voice_router
from app.core.config import settings
from app.middleware.security import RateLimitMiddleware, SecureHeadersMiddleware


app = FastAPI(title=settings.app_name, version="0.1.0")

# Security middleware (outermost first — order matters)
app.add_middleware(SecureHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(documents_router)
app.include_router(memory_router)
app.include_router(voice_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
