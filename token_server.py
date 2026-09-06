import json
import os

from aiohttp import web
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

VOICES = {
    "gura": "2bddc7ca0d5c4973b08aacd476ba2fae",
    "zeta": "3095f8e1d1fa4b82acaa8aca720a7f83",
    "sarah": "933563129e564b19a115bedd57b7406a",
    "adrian": "bf322df2096a46f18c579d0baa36f41d",
    "hannah": "9a9cf47702da476aa4629e2506d4a857",
    "raiden": "5ac6fb7171ba419190700620738209d8",
    "megan": "fb43143e46f44cc6ad7d06230215bab6",
    "natasha": "8c7ee2cd4d884622a0747daa25120b47",
    "tifa": "8e79322f8c064a9c965408f140c26fee",
    "emma": "41db41746b9c4bd18053c2bfc213b476",
    "furina": "bd08be872bc440918674af072944ba12",
    "luna": "22bff164a7104976ba3ade3b7ec1877c",
    "jade": "6ab4c6b0f37f4243a99046478647be94",
    "nilou": "00769d89b01942c6acc41818352d1b7f",
    "marin": "27e9d5f4f44747d994bff6981fe1673e",
    "reze": "663fa23ebab1439c8ea0c1350c1ba41b",
    "makima": "0c03219a981c4570a1b23a15b4107f30",
    "arlecchino": "99a08c573ed0481b96ee4bc866c1ea53",
    "yoimiya": "c9ffcfb699b64d5b822b89e6169a15f7",
    "jp1": "5161d41404314212af1254556477c17d",
    "jp2": "0089dce5fefb4c6ba9b9f2f0debe1ddc",
    "ano": "90de874f973541fabedbf67f00d23948",
}
DEFAULT_VOICE = "sarah"


async def voices_list(request):
    voices_data = [
        {"id": "sarah", "label": "Sarah", "desc": "EN · Voice", "default": True},
        {"id": "zeta", "label": "Zeta", "desc": "Calm · ID/EN", "default": False},
        {"id": "gura", "label": "Gura", "desc": "Energetic · EN", "default": False},
        {"id": "adrian", "label": "Adrian", "desc": "EN · Male", "default": False},
        {"id": "hannah", "label": "Hannah", "desc": "EN · Female", "default": False},
        {"id": "raiden", "label": "Raiden", "desc": "EN · Female", "default": False},
        {"id": "megan", "label": "Megan", "desc": "EN · Female", "default": False},
        {"id": "natasha", "label": "Natasha", "desc": "EN · Female", "default": False},
        {"id": "tifa", "label": "Tifa", "desc": "EN · Female", "default": False},
        {"id": "emma", "label": "Emma", "desc": "EN · Female", "default": False},
        {"id": "furina", "label": "Furina", "desc": "EN · Female", "default": False},
        {"id": "luna", "label": "Luna", "desc": "EN · Female", "default": False},
        {"id": "jade", "label": "Jade", "desc": "EN · Female", "default": False},
        {"id": "nilou", "label": "Nilou", "desc": "EN · Female", "default": False},
        {"id": "marin", "label": "Marin", "desc": "EN · Female", "default": False},
        {"id": "reze", "label": "Reze", "desc": "EN · Female", "default": False},
        {"id": "makima", "label": "Makima", "desc": "EN · Female", "default": False},
        {"id": "arlecchino", "label": "Arlecchino", "desc": "EN · Female", "default": False},
        {"id": "yoimiya", "label": "Yoimiya", "desc": "EN · Female", "default": False},
        {"id": "jp1", "label": "JP Voice 1", "desc": "JP · Female", "default": False},
        {"id": "jp2", "label": "JP Voice 2", "desc": "JP · Female", "default": False},
        {"id": "ano", "label": "Ano", "desc": "JP · Female", "default": False},
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
    web.run_app(app, port=8082, host="127.0.0.1")

