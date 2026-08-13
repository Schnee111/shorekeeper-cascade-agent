import json

from aiohttp import web
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

# Voice registry (Fish Audio voice IDs). The client picks one via
# ?voice=<key>; it rides into the JWT as a participant attribute and the
# agent reads it at session start (hot-swap mid-session isn't available in
# livekit-agents 1.6.9, so switching voices reconnects the room).
VOICES = {
    "gura": "2bddc7ca0d5c4973b08aacd476ba2fae",  # youthful/energetic, native EN
    "gura2": "5f28a45844e84e2297e6750db226a44d",  # Gawr Gura clone
    "zeta": "3095f8e1d1fa4b82acaa8aca720a7f83",  # previous default
}
DEFAULT_VOICE = "gura"


async def voices_list(request):
    return web.Response(
        text=json.dumps(
            {
                "voices": [
                    {"id": "gura", "label": "Gura", "default": True},
                    {"id": "gura2", "label": "Gura (alt)", "default": False},
                    {"id": "zeta", "label": "Zeta", "default": False},
                ]
            }
        ),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def get_token(request):
    room_name = request.query.get("room", "test-room")
    identity = request.query.get("identity", "schnee")
    voice_key = request.query.get("voice", DEFAULT_VOICE)
    voice_id = VOICES.get(voice_key, VOICES[DEFAULT_VOICE])

    # Create room config with agent dispatch
    room_config = api.RoomConfiguration(
        agents=[api.RoomAgentDispatch(agent_name="jarvis")]
    )

    token = (
        api.AccessToken()
        .with_identity(identity)
        .with_name(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
            )
        )
        .with_attributes({"voice": voice_id})
        .with_room_config(room_config)
        .to_jwt()
    )

    return web.Response(
        text=json.dumps({"token": token}),
        content_type="application/json",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type",
        },
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
