import json
import os

from aiohttp import web
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

VOICES = {
    "gura": "2bddc7ca0d5c4973b08aacd476ba2fae",
    "gura2": "5f28a45844e84e2297e6750db226a44d",
    "zeta": "3095f8e1d1fa4b82acaa8aca720a7f83",
    "v1": "4513226cdae34746b4dedf0b4dfa099e",
    "v2": "52e0660e03fe4f9a8d2336f67cab5440",
    "v3": "500db7775ebb4610b8a40a42dea2901a",
    "v4": "e35d38a3597a417d8d204ff2c19f233f",
    "v5": "8d21b053e2804e2a890e1cf62f267b6f",
    "v6": "e9ff03738cde487d854deb9b1f17099c",
    "v7": "265105e4556b4c0f906b0f426de988da",
    "v8": "396cad318c7146c59ab3f4476bb504bc",
    "v9": "d75c270eaee14c8aa1e9e980cc37cf1b",
    "v10": "1165af9072f14e7a87715e9589e5c5c4",
    "v11": "28fdcc7e03fd41f5aaf940d4c271ae50",
    "v12": "35e3afc40fff4b4aa7e0ec8715cd2367",
    "v13": "1f9d2a217c2940a59a3a28767f780a21",
    "v14": "90e65eaaf50e4470b8e6d43ee6afd7d5",
    "v15": "5d3e36762ccb4c1d8c6385e9baed695e",
    "v16": "7918bdf2c819412294e883d27747eef7",
    "v17": "461d972bd74442b4a06be63d34228cff",
    "v18": "b46d22d922224e54a77cd6afbb58c0bf",
    "v19": "6870b314685d4a309569ab3386f11cb4",
    "v20": "26c7a15d793a49feaf4faaa2c257439c",
}
DEFAULT_VOICE = "gura"


async def voices_list(request):
    voices_data = [
        {"id": "gura", "label": "Gura", "desc": "Energetic · EN", "default": True},
        {"id": "gura2", "label": "Gura (alt)", "desc": "Alt clone · EN", "default": False},
        {"id": "zeta", "label": "Zeta", "desc": "Calm · ID/EN", "default": False},
    ]
    for i in range(1, 21):
        voices_data.append({"id": f"v{i}", "label": f"Voice {i}", "desc": f"Fish Audio Model {i}", "default": False})

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

if __name__ == "__main__":
    # 8082: nginx proxies /jarvis-livekit/{token,voices} here. Do NOT move to
    # 8081 — that is the LiveKit agent worker's HTTP health port. The JWT
    # attribute MUST stay keyed "voice" (agent.py reads attributes["voice"]),
    # and routes MUST stay /token + /voices for the deployed client.
    web.run_app(app, port=8082)
