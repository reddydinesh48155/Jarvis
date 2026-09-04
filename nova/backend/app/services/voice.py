from datetime import timedelta
from uuid import UUID

from livekit import api

from app.core.config import settings


class LiveKitConfigurationError(RuntimeError):
    """Raised when the LiveKit server credentials are not configured."""


def user_room_name(user_id: UUID) -> str:
    """Return a private, deterministic room for one NOVA user."""
    return f"nova-user-{user_id.hex}"


def user_participant_identity(user_id: UUID) -> str:
    return f"nova-user-{user_id.hex}"


def create_user_voice_token(user_id: UUID, display_name: str) -> tuple[str, str, str, int]:
    if not all((settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret)):
        raise LiveKitConfigurationError("LiveKit credentials are not configured")

    room_name = user_room_name(user_id)
    identity = user_participant_identity(user_id)
    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
        can_update_own_metadata=True,
    )
    room_config = api.RoomConfiguration(
        agents=[api.RoomAgentDispatch(agent_name=settings.livekit_agent_name)]
    )
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(display_name)
        .with_ttl(timedelta(seconds=settings.livekit_token_ttl_seconds))
        .with_grants(grants)
        .with_room_config(room_config)
        .to_jwt()
    )
    return settings.livekit_url, room_name, identity, token
