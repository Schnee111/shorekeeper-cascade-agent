# JARVIS Voice — Architecture & Status

_Last updated: 2026-08-14 (session wrap-up)_

## Stack

```
Browser (Svelte, /var/www/jarvis/, https://tethys.web.id/jarvis/)
  │  WebRTC (LiveKit room)                │ REST: /jarvis-livekit/token
  ▼                                        ▼
LiveKit Cloud SFU                    token_server.py (:8082, systemd)
  │                                        voice picker, JWT mint (default: Gura)
  ▼
jarvis-agent (systemd, this repo)
  ├─ Deepgram nova-3 (STT, language=id)
  ├─ Silero VAD (min_silence_duration=0.5)
  ├─ LiveKit Turn Detector v1 (CLOUD) ← endpointing, see below
  ├─ hermes_llm.py bridge → Hermes gateway WS :9119
  │     └─ hermes-voice-gateway.service (user systemd, NOFILE=65536)
  │           └─ Hermes agent (LLM + tools)
  └─ Fish Audio s2.1-pro-free (TTS)
```

## Services

| Service | Unit | Notes |
|---|---|---|
| LiveKit agent | `jarvis-agent` (system) | `uv run python src/agent.py start` in this repo |
| Token/voice server | `token-server` (system) | port 8082 |
| Hermes gateway | `hermes-voice-gateway.service` (user) | script `~/.hermes/scripts/voice-gateway.sh`, log `~/logs/hermes-voice-gateway.log`, `LimitNOFILE=65536` |

After editing `src/*.py`: `sudo systemctl restart jarvis-agent`.

## Turn detection (the hot zone)

Current values in `src/agent.py`:

- `vad=inference.VAD(model="silero", min_silence_duration=0.5)`
- `turn_detection=inference.TurnDetector(version="v1")` — **cloud, no threshold override**
- `endpointing={"min_delay": 0.6, "max_delay": 2.0}`
- `preemptive_generation={"enabled": True}` — LLM starts during the grace wait
- `interruption={"mode": "adaptive"}`

### Why cloud v1 (commit a8bc12d)

Self-hosted agents default to the local `v1-mini` model (~108MB, CPU). On this
2-core VPS its first inference per session exceeded the SDK's hardcoded 1.0s
prediction timeout → `eot prediction timed out, committing without a prediction`
→ turns committed on silence alone → false cutoffs (log evidence: "cek statusnya
di" + "…di folder project" split into two turns).

Cloud `v1` (eot-bench SOTA, 14 languages incl. id) fixes this. Auth reuses
`LIVEKIT_API_KEY/SECRET`. `local_fallback=True` (default) keeps v1-mini as a
degraded path if the gateway is unreachable.

### Why no threshold override

Our old `unlikely_threshold={"id": 0.65, "en": 0.65}` was calibrated for an
older model; the SDK warns such overrides are suboptimal. LiveKit ships
per-language calibrated defaults (mini: id=0.345, en=0.36).

### Tuning history

1. Defaults → breath (250ms silence) split utterances.
2. VAD 0.6s + threshold 0.65 + min/max 1.0/3.0 → fewer cutoffs but slow, and
   timeouts still caused false commits (v1-mini cold start).
3. **Now:** cloud v1 + calibrated thresholds + min/max 0.6/2.0 + VAD 0.5.

## LiveKit Cloud inference quotas (self-hosted agents)

- Turn detector v1: **7,500 req/month free**, then automatic fallback to local
  v1-mini (degraded on this VPS — watch for `eot prediction timed out`).
- Adaptive interruption model: 40,000 req/month (1 req per 100ms of overlap).

Budget math: `predict()` fires per silence pause during speech (~1–4 per user
turn, avg ~3). 7,500 ÷ 3 ≈ **2,500 turns/month ≈ ~80 turns/day**. Fine for
personal use; if usage grows, monitor the fallback warning in jarvis-agent logs.

## Known issues & watchpoints

1. **SQLite fd leak** (hermes-agent issue #69678): gateway leaks ~999 fds/day
   toward its limit. Mitigated by NOFILE=65536 + Restart=always. Check:
   `ls /proc/$(pgrep -f "hermes serve")/fd | wc -l`.
2. **Barge-in stale events**: handled by two-phase drain + `seen_turn_signal`
   gate in `hermes_llm.py`. If 0.01s fake turns reappear, look for
   `Dropping stale ... before any turn signal` in logs.
3. **Error turns are announced**: gateway errors (e.g. fd exhaustion) now make
   the agent say "sorry, something failed" instead of dead silence.

## Testing

```bash
# Full voice E2E (TTS-synthesized user speech → agent audio reply)
uv run --with edge-tts python tools/test_e2e.py

# Raw gateway WS frame probe (diagnoses turn lifecycle)
uv run --with websockets,python-dotenv python tools/probe_ws_frames.py
```

## Repos

- `~/projects/jarvis-livekit` — **active**: LiveKit agent + bridge + token server
- `~/projects/shorekeeper-jarvis` — superseded bun voice prototype (server kept
  running on :3002 for `/jarvis/ws` nginx compat; state committed at d85176d4,
  node_modules purged)
- UI deploy: `rsync dist/ → /var/www/jarvis/` (client in shorekeeper-jarvis/client)
