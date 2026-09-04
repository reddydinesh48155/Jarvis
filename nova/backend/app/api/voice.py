from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import UserResponse, get_current_user
from app.core.config import settings
from app.db.models import User
from app.services.voice import LiveKitConfigurationError, create_user_voice_token


router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceTokenResponse(UserResponse):
    """Authenticated browser session details for connecting to LiveKit."""

    server_url: str
    room_name: str
    participant_identity: str
    participant_token: str
    expires_in: int


@router.post("/token", response_model=VoiceTokenResponse)
async def voice_token(current_user: User = Depends(get_current_user)) -> VoiceTokenResponse:
    try:
        server_url, room_name, identity, participant_token = create_user_voice_token(
            current_user.id, current_user.email
        )
    except LiveKitConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return VoiceTokenResponse(
        id=current_user.id,
        email=current_user.email,
        created_at=current_user.created_at,
        server_url=server_url,
        room_name=room_name,
        participant_identity=identity,
        participant_token=participant_token,
        expires_in=settings.livekit_token_ttl_seconds,
    )
