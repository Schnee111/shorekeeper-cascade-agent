"""Probe Hermes gateway WS streaming granularity.

Times every event from prompt.submit → message.complete and prints the
inter-arrival gap between consecutive message.delta events. If deltas are
truly streamed, gaps should be tens of ms; if we see ONE big delta after a
long silence, the gateway is buffering.
"""

import asyncio
import json
import sys
import time

import websockets
from dotenv import load_dotenv
import os

load_dotenv(".env.local")

WS_URL = "ws://127.0.0.1:9119/api/ws"
TOKEN = os.environ["HERMES_WS_TOKEN"]


async def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else "jelaskan apa itu fotosintesis dalam dua kalimat"
    async with websockets.connect(f"{WS_URL}?token={TOKEN}", ping_interval=20) as ws:
        async for raw in ws:
            d = json.loads(raw)
            if d.get("method") == "event" and d["params"].get("type") == "gateway.ready":
                break
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "session.create",
                                  "params": {"title": "latency-probe"}}))
        async for raw in ws:
            d = json.loads(raw)
            if d.get("id") == 1:
                sid = d["result"]["session_id"]; break
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "session.activate",
                                  "params": {"session_id": sid}}))
        async for raw in ws:
            d = json.loads(raw)
            if d.get("id") == 2: break

        t0 = time.monotonic()
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "prompt.submit",
                                  "params": {"session_id": sid, "text": prompt}}))
        print(f"[0.000] SUBMIT: {prompt!r}")
        last = t0
        n_deltas = 0
        total_text = ""
        async for raw in ws:
            now = time.monotonic()
            d = json.loads(raw)
            if d.get("id") == 3:
                print(f"[{now-t0:.3f}] ACK {d.get('result')} (gap {now-last:.3f})")
                last = now
                continue
            if d.get("method") != "event":
                continue
            p = d["params"]; t = p.get("type"); pl = p.get("payload", {}) or {}
            if t == "message.delta":
                n_deltas += 1
                txt = pl.get("text", "")
                total_text += txt
                gap = now - last
                if n_deltas <= 12 or gap > 0.3:
                    print(f"[{now-t0:.3f}] DELTA#{n_deltas} gap={gap:.3f}s len={len(txt)} {txt[:60]!r}")
                last = now
            elif t == "thinking.delta":
                print(f"[{now-t0:.3f}] THINKING gap={now-last:.3f}s {str(pl.get('text',''))[:40]!r}")
                last = now
            elif t in ("message.complete", "turn.complete", "session.turn_end"):
                print(f"[{now-t0:.3f}] {t} — total={now-t0:.3f}s, deltas={n_deltas}, chars={len(total_text)}")
                break

if __name__ == "__main__":
    asyncio.run(main())
