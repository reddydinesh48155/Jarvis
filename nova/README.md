# NOVA — Part 2: LiveKit Realtime Voice Integration

This directory is the isolated NOVA monorepo. Part 1 provides the FastAPI service, PostgreSQL persistence, Alembic migrations, JWT authentication, HTTP-only refresh cookies, and a small Next.js/Tailwind client. Part 2 adds LiveKit realtime transport only; LLM reasoning, tools, agents beyond the transport worker, STT, TTS, RAG, MCP, and memory remain out of scope.

## Run locally with Docker Compose

Requirements:

- Docker Desktop with Compose
- Ports `3000`, `5432`, and `8000` available
- A LiveKit Cloud project with its WebSocket URL, API key, and API secret

From this directory:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Before starting, replace the LiveKit placeholders in `.env` with credentials from your LiveKit Cloud project. The `voice-agent` service registers the `nova-voice` worker and is dispatched automatically when the authenticated browser joins its private room.

Open `http://localhost:3000/voice` for the Voice Workspace. The API is available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs` and a health check at `http://localhost:8000/health`.

The backend container runs `alembic upgrade head` before starting FastAPI. It does not create tables during application startup. PostgreSQL data is kept in the `postgres_data` named volume.

For anything beyond local development, replace all example passwords/secrets in `.env` with unique values. Set `SECURE_COOKIES=true` when the API is served over HTTPS.

## Run the backend without Docker

Use Python 3.11 (the project intentionally targets `>=3.11,<3.12`):

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Start PostgreSQL separately, then copy the template into the backend directory and change `DATABASE_URL` to use `localhost` instead of `postgres`:

```powershell
Copy-Item ..\.env.example .env
```

Edit `backend\.env` so its database URL is:

```text
postgresql+asyncpg://nova:change-me-postgres-password@localhost:5432/nova
```

Then run the migration and server from `backend`:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

In a second terminal, run the LiveKit worker if it is not running through Compose:

```powershell
python -m app.voice.worker start
```

The worker uses the LiveKit Agents `AgentServer` lifecycle and subscribes to microphone audio with `AudioStream`. It uses an RMS silence detector, replays the captured PCM through a published `AudioSource`, and sends the scripted `I heard you` acknowledgement over a reliable LiveKit data message. This intentionally avoids STT/LLM/TTS dependencies; Part 3 can replace this transport echo with spoken output.

Run the backend tests without a live database:

```powershell
python -m pytest
```

Tests inject an in-memory SQLite database. Production schema changes must be represented by a new Alembic revision.

## Authentication API

- `POST /auth/register` — create a user, return an access token, and set a refresh cookie.
- `POST /auth/login` — authenticate and issue an access token plus refresh cookie.
- `POST /auth/refresh` — rotate the refresh cookie and return a new access token.
- `POST /auth/logout` — revoke the current refresh token and clear the cookie.
- `GET /auth/me` — return the current user; requires `Authorization: Bearer <access_token>`.

## Voice API

- `POST /voice/token` — requires the authenticated access token and returns a LiveKit participant token, server URL, and private per-user room details.

The browser uses `livekit-client` to connect, publishes the microphone with `setMicrophoneEnabled`, attaches agent audio tracks, and listens for active-speaker, acknowledgement, and reconnection events. LiveKit's client SDK automatically retries brief connection interruptions; the page also requests a fresh token and retries after an unrecoverable disconnect.

Passwords are stored only as bcrypt hashes. Refresh tokens are stored server-side as SHA-256 hashes, so logout can invalidate them without persisting the raw cookie value.

## Assumptions and remaining TODOs

- Registration signs the user in immediately, matching the frontend flow.
- The access token is held in frontend session state; the browser refreshes it after a reload using the HTTP-only cookie.
- Refresh tokens rotate on refresh and are revoked on logout. Local HTTP uses `SECURE_COOKIES=false`; HTTPS deployments must enable it.
- Email verification, password reset, login throttling, CSRF hardening for broader cookie usage, account recovery, OAuth, production secret management, and observability remain TODO for later security/auth work.
- A human-spoken acknowledgement, STT, LLM, TTS, and richer turn handling remain TODO for Part 3; Part 2 intentionally publishes an audio echo plus a data acknowledgement.
