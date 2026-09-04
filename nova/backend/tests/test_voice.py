from unittest.mock import MagicMock, patch


def register_and_get_access_token(client, email="voice@example.com"):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_voice_token_requires_authentication(client):
    response = client.post("/voice/token")

    assert response.status_code == 401


def test_voice_token_returns_livekit_connection_details(client):
    access_token = register_and_get_access_token(client)
    token_builder = MagicMock()
    token_builder.with_identity.return_value = token_builder
    token_builder.with_name.return_value = token_builder
    token_builder.with_ttl.return_value = token_builder
    token_builder.with_grants.return_value = token_builder
    token_builder.with_room_config.return_value = token_builder
    token_builder.to_jwt.return_value = "header.payload.signature"

    with patch("app.services.voice.api.AccessToken", return_value=token_builder) as access_token_factory:
        response = client.post(
            "/voice/token",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["server_url"] == "wss://test.livekit.cloud"
    assert body["room_name"].startswith("nova-user-")
    assert body["participant_identity"] == body["room_name"]
    assert body["participant_token"] == "header.payload.signature"
    assert body["expires_in"] == 3600

    access_token_factory.assert_called_once_with("test-livekit-api-key", "test-livekit-api-secret")
    grants = token_builder.with_grants.call_args.args[0]
    assert grants.room_join is True
    assert grants.can_publish is True
    assert grants.can_subscribe is True
    assert grants.can_publish_data is True
    assert token_builder.with_room_config.call_args.args[0].agents[0].agent_name == "nova-voice"
