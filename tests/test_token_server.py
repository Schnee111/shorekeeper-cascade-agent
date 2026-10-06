import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

# Ensure root dir is in sys.path so token_server can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))
from token_server import create_app


@pytest.mark.asyncio
async def test_valid_token_request_default_params(monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret01234567890123456789012345678901")

    async with TestClient(TestServer(create_app())) as client:
        resp = await client.get("/token")
        assert resp.status == 200
        data = await resp.json()
        assert "token" in data
        assert "voice_id" in data


@pytest.mark.asyncio
async def test_valid_token_request_custom_params(monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret01234567890123456789012345678901")

    async with TestClient(TestServer(create_app())) as client:
        resp = await client.get(
            "/token?identity=user_123-abc&room=room_456-xyz&voice=zeta"
        )
        assert resp.status == 200
        data = await resp.json()
        assert "token" in data
        assert data["voice_id"] == "3095f8e1d1fa4b82acaa8aca720a7f83"


@pytest.mark.asyncio
async def test_invalid_identity_cases():
    async with TestClient(TestServer(create_app())) as client:
        invalid_identities = [
            "",  # empty (handled if query param passed as empty string)
            "user@domain",  # special char @
            "user.name",  # dot not allowed
            "user/name",  # slash not allowed
            "user name",  # space not allowed
            "a" * 33,  # exceeds 32 chars
            "../../root",  # path traversal
            "<script>alert(1)</script>",  # XSS
        ]
        for identity in invalid_identities:
            resp = await client.get(
                "/token", params={"identity": identity, "room": "valid-room"}
            )
            assert resp.status == 400
            data = await resp.json()
            assert data["error"] == "INVALID_IDENTITY"
            assert "Identity must match" in data["message"]


@pytest.mark.asyncio
async def test_invalid_room_cases():
    async with TestClient(TestServer(create_app())) as client:
        invalid_rooms = [
            "",  # empty (handled if query param passed as empty string)
            "room.name",  # dot not allowed
            "room/name",  # slash not allowed
            "room name",  # space not allowed
            "r" * 65,  # exceeds 64 chars
            "room?query",  # query delimiter
            "room#tag",  # hash not allowed (if url encoded or without hash cutting)
            "room@domain",  # special char @
            "room$admin",  # special char $
        ]
        for room in invalid_rooms:
            resp = await client.get(
                "/token", params={"identity": "valid_user", "room": room}
            )
            assert resp.status == 400
            data = await resp.json()
            assert data["error"] == "INVALID_ROOM"
            assert "Room must match" in data["message"]


@pytest.mark.asyncio
async def test_voices_endpoint():
    async with TestClient(TestServer(create_app())) as client:
        resp = await client.get("/voices")
        assert resp.status == 200
        data = await resp.json()
        assert "voices" in data
        assert len(data["voices"]) > 0
