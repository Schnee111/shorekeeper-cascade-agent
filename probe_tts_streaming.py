"""Isolate the TTS question: does fishaudio/s2.1-pro-free stream audio
progressively, or does it batch until end-of-input?

Push sentence A, measure time-to-first-audio. After 5s push sentence B,
close, measure. If A's audio arrives before B is pushed → real streaming.
If all audio arrives only after close() → the hosted endpoint batches,
which fully explains 'fillers glued to the final answer'."""
import asyncio
import sys
import time

sys.path.insert(0, "src")
from dotenv import load_dotenv

load_dotenv(".env.local")

from livekit.agents import inference  # noqa: E402
from livekit.agents.utils import http_context  # noqa: E402

VOICE = "2bddc7ca0d5c4973b08aacd476ba2fae"  # gura
SENT_A = "Let me check on that real quick."
SENT_B = "It is currently three fifteen in the afternoon."


async def main():
    t0 = time.monotonic()

    def ts():
        return f"+{time.monotonic() - t0:6.2f}s"

    tts = inference.TTS(model="fishaudio/s2.1-pro-free", voice=VOICE)

    async with http_context.open():
        stream = tts.stream()
        first_audio = {}
        total_frames = [0]
        done = asyncio.Event()

        async def recv():
            async for ev in stream:
                frame = getattr(ev, "frame", None)
                if frame is not None:
                    total_frames[0] += 1
                    label = "A" if total_frames[0] == 1 else None
                    # mark first frame overall, and first frame after B
                    if "first" not in first_audio:
                        first_audio["first"] = time.monotonic() - t0
                        print(f"[{ts()}] FIRST AUDIO FRAME (after push A only)")
                    if "after_B" in first_audio and first_audio["after_B"] is True:
                        first_audio["after_B"] = time.monotonic() - t0
                        print(f"[{ts()}] first audio frame AFTER push B")

        recv_task = asyncio.create_task(recv())

        print(f"[{ts()}] push_text(A): {SENT_A!r}")
        stream.push_text(SENT_A)
        await asyncio.sleep(5.0)

        print(f"[{ts()}] push_text(B): {SENT_B!r}")
        if "after_B" not in first_audio:
            first_audio["after_B"] = True
        stream.push_text(SENT_B)
        await asyncio.sleep(0.5)

        print(f"[{ts()}] end_input()")
        stream.end_input()
        await asyncio.wait_for(recv_task, timeout=30)
        await stream.aclose()

    print("=" * 60)
    if "first" not in first_audio:
        print("NO AUDIO AT ALL")
    else:
        print(f"first audio:        {first_audio['first']:.2f}s after start")
        if isinstance(first_audio.get("after_B"), float):
            print(f"audio after B push: {first_audio['after_B']:.2f}s")
        print(f"total frames:       {total_frames[0]}")
        if first_audio["first"] < 5.0:
            print("VERDICT: TRUE STREAMING (A's audio arrived before B was pushed)")
        else:
            print("VERDICT: BATCHED (audio only arrived after B/end — TTS waits)")


asyncio.run(main())
