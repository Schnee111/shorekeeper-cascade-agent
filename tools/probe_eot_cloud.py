"""Probe the LiveKit Cloud EOT detector — exact production code path.

Instantiates the SAME TurnDetector(version='v1') the agent uses, streams
~2s of framed audio, then flush + predict, measuring the real round trip.
Verifies: (1) gateway reachability, (2) LIVEKIT_API_KEY auth,
(3) prediction latency vs the SDK's 1.0s timeout.

Usage: .venv/bin/python tools/probe_eot_cloud.py
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents.inference.eot import TurnDetector

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

SAMPLE_RATE = 16000


def make_frame(seconds: float, freq: float = 220.0) -> rtc.AudioFrame:
    n = int(SAMPLE_RATE * seconds)
    t = np.arange(n) / SAMPLE_RATE
    data = (4000 * np.sin(2 * np.pi * freq * t)).astype(np.int16).tobytes()
    return rtc.AudioFrame(
        data=data, sample_rate=SAMPLE_RATE, num_channels=1, samples_per_channel=n
    )


async def main() -> int:
    # Outside the agent worker the plugin has no shared http session —
    # open one explicitly so the CLOUD transport (not local fallback) is used.
    from livekit.agents.utils import http_context

    async with http_context.open():
        detector = TurnDetector(version="v1")
        stream = detector.stream()
        t_start = time.time()

        async def push_audio():
            for _ in range(33):  # ~2s of framed audio
                stream.push_audio(make_frame(0.06))
                await asyncio.sleep(0.06)
            stream.flush()  # end of speech — mirrors audio_recognition flush

        fut = stream.predict()
        push_task = asyncio.create_task(push_audio())

        try:
            ev = await asyncio.wait_for(fut, timeout=8.0)
            dt = time.time() - t_start
            degraded = getattr(stream, "is_fallback", False) or getattr(
                stream, "is_degraded", False
            )
            print(f"RESULT: prediction received in {dt:.2f}s (SDK timeout: 1.0s)")
            print(f"  end_of_turn_probability: {ev.end_of_turn_probability:.3f}")
            print(f"  type: {ev.type}")
            print(f"  transport: {'LOCAL FALLBACK' if degraded else 'CLOUD v1'}")
            ok = dt < 1.0
            print(
                f"  within SDK timeout: {'YES' if ok else 'NO — timeout causes VAD-only commits'}"
            )
            return 0 if ok else 2
        except asyncio.TimeoutError:
            print(
                "RESULT: NO prediction within 8s — cloud path broken (fallback/degraded)"
            )
            return 1
        finally:
            push_task.cancel()
            await stream.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
