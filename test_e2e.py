"""Headless E2E verification (plan ui-integration.md §7.6).

Connects to a fresh LiveKit room as identity `schnee`, plays pre-generated
Indonesian speech via a LocalAudioTrack, and verifies:
  1. agent joins (auto-dispatch) and greets
  2. user STT transcribes the injected audio
  3. agent replies (full turn complete)

Audio generation: uv run --with edge-tts python test_e2e.py
"""

import asyncio
import json
import logging
import sys
import time
import urllib.request

import edge_tts
from livekit import rtc

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("e2e")
logger.setLevel(logging.INFO)

USER_TEXT = "halo JARVIS, apa kabar hari ini"
ROOM_NAME = f"jarvis-test-{int(time.time()) % 100000}"
TIMEOUT_TOTAL = 90.0


async def fetch_token(room: str) -> str:
    url = f"http://127.0.0.1:8082/token?room={room}&identity=schnee"
    with urllib.request.urlopen(url, timeout=10) as res:
        return json.loads(res.read())["token"]


async def gen_speech(text: str, path: str) -> None:
    """Generate 48kHz-capable speech with edge-tts (mp3 → decoded by caller)."""
    communicate = edge_tts.Communicate(text, voice="id-ID-GadisNeural", rate="-5%")
    await communicate.save(path)


def load_pcm(mp3_path: str, wav_path: str) -> tuple[bytes, int]:
    """mp3 → raw PCM via ffmpeg; returns (pcm_bytes, sample_rate)."""
    import subprocess

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", mp3_path,
            "-ar", "48000", "-ac", "1", "-f", "s16le", wav_path,
        ],
        check=True,
        capture_output=True,
    )
    with open(wav_path, "rb") as f:
        return f.read(), 48000


async def main() -> None:
    results = {"greeting": False, "user_stt": False, "agent_reply": False}
    transcript_lines: list[str] = []

    logger.info("Generating speech: %r", USER_TEXT)
    await gen_speech(USER_TEXT, "/tmp/e2e_speech.mp3")
    pcm, sample_rate = load_pcm("/tmp/e2e_speech.mp3", "/tmp/e2e_speech.pcm")
    logger.info("PCM ready: %d bytes @ %dHz (%.1fs)", len(pcm), sample_rate, len(pcm) / 2 / sample_rate)

    token = await fetch_token(ROOM_NAME)
    logger.info("Token fetched, room=%s", ROOM_NAME)

    room = rtc.Room()
    audio_source = rtc.AudioSource(sample_rate, num_channels=1)
    mic_track = rtc.LocalAudioTrack.create_audio_track("mic", audio_source)
    opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info("Agent audio track subscribed from %s", participant.identity)

    @room.on("transcription_received")
    def on_transcription(segments, participant, publication=None):
        owner_identity = participant.identity if participant else "agent"
        for seg in segments:
            owner = "AGENT" if owner_identity != "schnee" else "USER(STT)"
            logger.info("[%s] %s (final=%s)", owner, seg.text, seg.final)
            transcript_lines.append(f"{owner}: {seg.text}")
            if owner_identity != "schnee" and seg.text:
                if not results["greeting"] and len(seg.text) > 5:
                    results["greeting"] = True
                elif results["user_stt"] and seg.final:
                    results["agent_reply"] = True
            else:
                if seg.final and seg.text:
                    results["user_stt"] = True

    @room.on("participant_connected")
    def on_participant(participant):
        logger.info("Participant joined: %s", participant.identity)

    await room.connect("wss://shore-eoiag4jd.livekit.cloud", token)
    logger.info("Connected to room")
    await room.local_participant.publish_track(mic_track, opts)
    logger.info("Mic track published")

    t0 = time.monotonic()

    # Wait a moment for the agent to join and greet, then play speech.
    async def play_speech_later():
        await asyncio.sleep(12)  # allow agent join + greeting TTS to start
        logger.info("Playing user speech...")
        frame_samples = sample_rate // 10  # 100ms frames
        frame_bytes = frame_samples * 2
        for i in range(0, len(pcm) - frame_bytes, frame_bytes):
            frame = rtc.AudioFrame(
                data=pcm[i : i + frame_bytes],
                sample_rate=sample_rate,
                num_channels=1,
                samples_per_channel=frame_samples,
            )
            await audio_source.capture_frame(frame)
            await asyncio.sleep(0.05)  # slight pace to not overflow
        logger.info("Speech playback done")

    play_task = asyncio.create_task(play_speech_later())

    # Wait until all verified or timeout.
    while time.monotonic() - t0 < TIMEOUT_TOTAL:
        if all(results.values()):
            break
        await asyncio.sleep(1)

    await play_task
    await room.disconnect()

    logger.info("=" * 50)
    logger.info("RESULTS: greeting=%s user_stt=%s agent_reply=%s",
                results["greeting"], results["user_stt"], results["agent_reply"])
    logger.info("=" * 50)
    for line in transcript_lines:
        logger.info("  %s", line)
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    asyncio.run(main())
