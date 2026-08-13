"""Probe the raw Hermes gateway WS frames for a fresh-session submit.

Question answered: what exactly arrives between prompt.submit's RPC ack and
the turn's real events — and where does the early `message.complete` come
from? Prints every frame with a timestamp so ordering is provable.
"""

import asyncio
import json
import os
import time

import websockets
from dotenv import load_dotenv

load_dotenv(".env.local")

URL = "ws://127.0.0.1:9119/api/ws?token=" + os.environ.get("HERMES_WS_TOKEN", "")


async def main() -> None:
    t0 = time.monotonic()

    def ts() -> str:
        return f"+{time.monotonic() - t0:7.3f}s"

    async with websockets.connect(URL, ping_interval=None) as ws:
        print(f"{ts()} connected")

        # gateway.ready
        async for raw in ws:
            data = json.loads(raw)
            if data.get("method") == "event" and data.get("params", {}).get(
                "type"
            ) == "gateway.ready":
                print(f"{ts()} gateway.ready")
                break
            print(f"{ts()} FRAME: {raw[:200]}")

        # session.create
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "session.create",
            "params": {"title": f"probe-{int(time.time())}"},
        }))
        sid = None
        async for raw in ws:
            data = json.loads(raw)
            print(f"{ts()} FRAME: {raw[:300]}")
            if data.get("id") == 1:
                sid = data["result"]["session_id"]
                break

        # session.activate
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "session.activate",
            "params": {"session_id": sid},
        }))
        async for raw in ws:
            data = json.loads(raw)
            print(f"{ts()} FRAME: {raw[:300]}")
            if data.get("id") == 2:
                break

        # prompt.submit
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": 3, "method": "prompt.submit",
            "params": {"session_id": sid, "text": "Jam berapa sekarang? Jawab singkat."},
        }))
        print(f"{ts()} submitted prompt")

        async for raw in ws:
            data = json.loads(raw)
            t = data.get("params", {}).get("type", "") if data.get("method") == "event" else f"rpc id={data.get('id')}"
            extra = ""
            if t == "message.delta":
                extra = " TEXT=" + json.dumps(data["params"]["payload"].get("text", "")[:60])
            elif t == "message.complete":
                extra = " PAYLOAD=" + str(data["params"].get("payload", {}))[:250]
            print(f"{ts()} EVENT {t}{extra}")
            if t == "message.complete":
                # keep reading a bit to see what follows the terminator
                try:
                    while True:
                        raw2 = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        d2 = json.loads(raw2)
                        t2 = d2.get("params", {}).get("type", "") if d2.get("method") == "event" else f"rpc id={d2.get('id')}"
                        print(f"{ts()} AFTER-COMPLETE EVENT {t2}: {raw2[:250]}")
                except asyncio.TimeoutError:
                    pass
                break


asyncio.run(main())
