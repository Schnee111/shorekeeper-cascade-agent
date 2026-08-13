"""Measure WHEN agent audio actually arrives for a tool-call turn.

Plays a tool-triggering question, captures the agent's audio stream, and
reports voiced intervals vs. submit time. If audio only arrives in one
burst at the end, playback (or TTS) is batching; if it arrives in multiple
separated intervals, streaming works and perceived silence is elsewhere.
"""
import asyncio, json, logging, math, subprocess, sys, time, urllib.request

import edge_tts
from livekit import rtc

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("probe")
logger.setLevel(logging.INFO)

USER_TEXT = "Cek jadwal film Spiderman besok di Bandung"
ROOM_NAME = f"jarvis-probe-{int(time.time()) % 100000}"
T0 = time.monotonic()


def ts():
    return f"+{time.monotonic() - T0:6.2f}s"


async def fetch_token(room):
    url = f"http://127.0.0.1:8082/token?room={room}&identity=schnee"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())["token"]


async def gen_speech(text, path):
    c = edge_tts.Communicate(text, voice="id-ID-GadisNeural", rate="-5%")
    await c.save(path)


def load_pcm(mp3, wav):
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3, "-ar", "48000", "-ac", "1", "-f", "s16le", wav],
        check=True, capture_output=True,
    )
    with open(wav, "rb") as f:
        return f.read(), 48000


async def main():
    logger.info("[%s] generating user speech", ts())
    await gen_speech(USER_TEXT, "/tmp/probe.mp3")
    pcm, sr = load_pcm("/tmp/probe.mp3", "/tmp/probe.pcm")
    token = await fetch_token(ROOM_NAME)
    room = rtc.Room()
    audio_source = rtc.AudioSource(sr, num_channels=1)
    mic = rtc.LocalAudioTrack.create_audio_track("mic", audio_source)

    audio_streams: list[rtc.AudioStream] = []
    energy = []  # (t_rel, rms) of voiced frames

    @room.on("track_subscribed")
    def on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity != "schnee":
            logger.info("[%s] agent audio track subscribed", ts())
            audio_streams.append(rtc.AudioStream(track))

    await room.connect("wss://shore-eoiag4jd.livekit.cloud", token)
    await room.local_participant.publish_track(
        mic, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )
    logger.info("[%s] connected", ts())

    async def play():
        await asyncio.sleep(13)
        logger.info("[%s] PLAYING user speech: %r", ts(), USER_TEXT)
        fb = (sr // 10) * 2
        for i in range(0, len(pcm) - fb, fb):
            await audio_source.capture_frame(rtc.AudioFrame(
                data=pcm[i : i + fb], sample_rate=sr,
                num_channels=1, samples_per_channel=sr // 10))
            await asyncio.sleep(0.05)
        logger.info("[%s] user speech done", ts())

    async def capture():
        """Record ALL agent audio (incl. silence) to WAV for offline analysis."""
        import wave as wavemod

        rec = wavemod.open("/tmp/probe_agent.wav", "wb")
        rec.setnchannels(1)
        rec.setsampwidth(2)
        rec.setframerate(48000)
        first_logged = False
        try:
            while True:
                if not audio_streams:
                    await asyncio.sleep(0.1)
                    continue
                st = audio_streams[0]
                try:
                    ev = await asyncio.wait_for(st.__anext__(), timeout=0.3)
                except asyncio.TimeoutError:
                    continue
                except StopAsyncIteration:
                    break
                frame = getattr(ev, "frame", None) or ev
                data = frame.data
                if not data:
                    continue
                rec.writeframes(bytes(data))
                import struct

                n = len(data) // 2
                samples = struct.unpack(f"<{n}h", data)
                peak = max(abs(s) for s in samples[::16]) if samples else 0
                if peak > 300:
                    if not first_logged:
                        first_logged = True
                        logger.info("[%s] *** FIRST AGENT AUDIO peak=%d ***", ts(), peak)
                    energy.append((time.monotonic() - T0, peak))
        finally:
            rec.close()
            logger.info("[%s] recording saved /tmp/probe_agent.wav", ts())

    play_task = asyncio.create_task(play())
    cap_task = asyncio.create_task(capture())

    await play_task
    await asyncio.sleep(35)
    cap_task.cancel()
    await room.disconnect()

    logger.info("=" * 62)
    if not energy:
        logger.info("NO AGENT AUDIO CAPTURED")
    else:
        logger.info("First agent audio at +%.2fs (after user speech done)", energy[0][0])
        intervals = []
        start = energy[0][0]
        last = start
        for t, _ in energy[1:]:
            if t - last > 0.5:
                intervals.append((start, last))
                start = t
            last = t
        intervals.append((start, last))
        logger.info("VOICED INTERVALS (%d):", len(intervals))
        for a, b in intervals:
            logger.info("  +%.1fs .. +%.1fs  (%.1fs voiced)", a, b, max(0.0, b - a))
        gaps = [round(intervals[i + 1][0] - intervals[i][1], 1) for i in range(len(intervals) - 1)]
        logger.info("GAPS between intervals: %s", gaps)
    logger.info("=" * 62)
    sys.exit(0)


asyncio.run(main())
