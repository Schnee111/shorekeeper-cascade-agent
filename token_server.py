import json
import os

from aiohttp import web
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

VOICES = {
    "gura": "2bddc7ca0d5c4973b08aacd476ba2fae",
    "zeta": "3095f8e1d1fa4b82acaa8aca720a7f83",
}
DEFAULT_VOICE = "gura"


async def voices_list(request):
    voices_data = [
        {"id": "gura", "label": "Gura", "desc": "Energetic · EN", "default": True},
        {"id": "zeta", "label": "Zeta", "desc": "Calm · ID/EN", "default": False},
    ]

    return web.Response(
        text=json.dumps({"voices": voices_data}),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def get_token(request):
    room_name = request.query.get("room", "test-room")
    identity = request.query.get("identity", "schnee")
    voice_key = request.query.get("voice", DEFAULT_VOICE)
    voice_id = VOICES.get(voice_key, VOICES[DEFAULT_VOICE])

    room_config = api.RoomConfiguration(
        agents=[api.RoomAgentDispatch(agent_name="jarvis")]
    )

    grant = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
    )

    token = (
        api.AccessToken(
            os.getenv("LIVEKIT_API_KEY"),
            os.getenv("LIVEKIT_API_SECRET"),
        )
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grant)
        .with_room_config(room_config)
        .with_attributes({"voice": voice_id})
        .to_jwt()
    )

    return web.Response(
        text=json.dumps({"token": token, "voice_id": voice_id}),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


app = web.Application()
app.router.add_get("/token", get_token)
app.router.add_get("/voices", voices_list)
app.router.add_options(
    "/token",
    lambda r: web.Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    ),
)
