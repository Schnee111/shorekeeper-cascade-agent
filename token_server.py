import json
import os

from aiohttp import web
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

VOICES = {
    "gura": "2bddc7ca0d5c4973b08aacd476ba2fae",
    "zeta": "3095f8e1d1fa4b82acaa8aca720a7f83",
    "id1": "5ac6fb7171ba419190700620738209d8",
    "id2": "03931f053cb0445182f4709598f96186",
    "id3": "b8d76dc67d5843e8ab4c1160d537319e",
    "id4": "6e0772af2f614f3d9a3c318e35d720db",
    "id5": "08e53aec741c40f885fbfa870fb76881",
    "id6": "6a27b7eb22dc4006b01733d003f63018",
    "id7": "da2c0df555e542148df8450af7d459a2",
}
DEFAULT_VOICE = "zeta"


async def voices_list(request):
    voices_data = [
        {"id": "zeta", "label": "Zeta", "desc": "Calm · ID/EN", "default": True},
        {"id": "gura", "label": "Gura", "desc": "Energetic · EN", "default": False},
        {"id": "id1", "label": "Indo Voice 1", "desc": "ID · 5ac6fb71", "default": False},
        {"id": "id2", "label": "Indo Voice 2", "desc": "ID · 03931f05", "default": False},
        {"id": "id3", "label": "Indo Voice 3", "desc": "ID · b8d76dc6", "default": False},
        {"id": "id4", "label": "Indo Voice 4", "desc": "ID · 6e0772af", "default": False},
        {"id": "id5", "label": "Indo Voice 5", "desc": "ID · 08e53aec", "default": False},
        {"id": "id6", "label": "Indo Voice 6", "desc": "ID · 6a27b7eb", "default": False},
        {"id": "id7", "label": "Indo Voice 7", "desc": "ID · da2c0df5", "default": False},
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
    model = request.query.get("model", "")

    room_config = api.RoomConfiguration(
        agents=[api.RoomAgentDispatch(agent_name="jarvis")]
    )

    grant = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
    )

    attributes = {"voice": voice_id}
    if model:
        attributes["model"] = model

    token = (
        api.AccessToken(
            os.getenv("LIVEKIT_API_KEY"),
            os.getenv("LIVEKIT_API_SECRET"),
        )
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grant)
        .with_room_config(room_config)
        .with_attributes(attributes)
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

if __name__ == "__main__":
    web.run_app(app, port=8082)

