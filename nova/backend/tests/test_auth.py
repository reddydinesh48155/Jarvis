def register_user(client, email="ada@example.com", password="correct-horse-battery"):
    return client.post("/auth/register", json={"email": email, "password": password})


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_returns_access_token_and_http_only_refresh_cookie(client):
    response = register_user(client)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "ada@example.com"
    assert "hashed_password" not in body

    set_cookie = response.headers["set-cookie"]
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie


def test_login_and_me_require_and_accept_access_token(client):
    register_user(client, "grace@example.com")
    response = client.post(
        "/auth/login",
        json={"email": "GRACE@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 200
    access_token = response.json()["access_token"]

    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "grace@example.com"


def test_duplicate_registration_and_bad_login_are_rejected(client):
    register_user(client, "linus@example.com")

    duplicate = register_user(client, "LINUS@example.com")
    assert duplicate.status_code == 409

    bad_login = client.post(
        "/auth/login",
        json={"email": "linus@example.com", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401


def test_logout_revokes_refresh_token(client):
    register_user(client, "margaret@example.com")
    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 200
    active_refresh_token = refresh_response.cookies.get("refresh_token")
    assert active_refresh_token

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 204
    client.cookies.set("refresh_token", active_refresh_token)
    assert client.post("/auth/refresh").status_code == 401
