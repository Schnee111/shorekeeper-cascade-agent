# Shorekeeper Cascade Agent

Production-ready, modular cascade voice AI agent built with **LiveKit Agents for Python**, **Groq Whisper large-v3**, **Hermes LLM**, and **Fish Audio S2.1 Pro TTS**. Optimized for low-latency conversational audio, tool reasoning, and automated containerized deployment.

---

## Overview

The `shorekeeper-cascade-agent` serves as the backend intelligence and media processing pipeline for the Shorekeeper voice ecosystem. Unlike monolithic speech-to-speech models, this architecture separates speech perception, tool execution, and vocal synthesis into modular layers, allowing granular prompt biasing, deterministic tool dispatch, and custom vocal timbre rendering.

### Key Capabilities

- **Biased Speech-to-Text**: Groq-accelerated `whisper-large-v3` with Indonesian prompt biasing to prevent phonetic hallucination, backed by Deepgram Nova-3 failover.
- **Smart Turn Detection**: Multilingual acoustic end-of-turn detector with Silero VAD calibrated at `min_silence_duration = 0.6s`.
- **Hermes LLM Reasoning**: Fast tool orchestration, conversational disfluency early acknowledgments (2.8s threshold), and continuous periodic dwell filler loops (4.0s).
- **Expressive 48kHz TTS**: Zero-latency speech synthesis via Fish Audio S2.1 Pro (`s2.1-pro-free`), locked at native 48,000 Hz to eliminate WebRTC hardware resampling crackle.
- **Standalone Token Server**: Built-in HTTP server (`127.0.0.1:8082`) issuing ephemeral JWT room tokens and voice catalog manifests.

---

## Architecture Flow

```text
  [ WebRTC Audio In ]
          │
          ▼
   [ Silero VAD + Turn Detector ]
          │
          ▼
   [ Groq Whisper large-v3 STT ] ──(Indonesian Prompt Biased)──▶ [ Text Transcript ]
                                                                       │
                                                                       ▼
   [ Fish Audio S2.1 Pro TTS ] ◀──(Natural English Speech)─── [ Hermes LLM Engine ]
          │ (Locked 48kHz Opus)                                        │
          ▼                                                            ▼
  [ WebRTC Audio Out ]                                        [ Tool Execution ]
```

---

## Getting Started

### Prerequisites

- **Python**: >= 3.11, < 3.15
- **uv**: Fast Python package installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **LiveKit Cloud or Self-Hosted LiveKit Server**

### Environment Configuration

Create a `.env.local` file with your credentials:

```bash
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# AI Providers
GROQ_API_KEY=gsk_...
DEEPGRAM_API_KEY=...
FISH_API_KEY=sk-fish...
```

### Local Development

1. Install dependencies:
   ```bash
   uv sync --locked
   ```

2. Run tests and verify code quality:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest -v tests/
   ```

3. Start the agent in development mode:
   ```bash
   uv run python src/agent.py dev
   ```

4. In a separate terminal, start the token server:
   ```bash
   uv run python token_server.py
   ```

---

## Production Deployment (Docker & Containerization)

The repository provides a multi-stage `Dockerfile` based on `python:3.11-slim-bookworm` with layer caching, weighing only **~260 MB**.

### Running via Docker Compose

```bash
# Start Agent and Token Server with strict resource limits
docker compose -f docker-compose.prod.yml up -d
```

### Resource Limits (VPS-Friendly)

- **Agent Container**: `cpus: 1.5`, `mem_limit: 600M`
- **Token Server**: `cpus: 0.5`, `mem_limit: 128M`
- **Network Mode**: `host` (bound strictly to `127.0.0.1`)

---

## CI/CD & Automated Release

- **Continuous Integration**: On every push and PR, GitHub Actions runs `ruff` linting, code formatting checks, and the `pytest` test suite.
- **Automated GHCR Deployment**: Pushes to `main` build multi-stage images and push to GitHub Container Registry (`ghcr.io/schnee111/shorekeeper-cascade-agent`) tagged by short commit SHA (`sha-<hash>`) and semantic versions.
- **Release Automation**: Powered by **Google Release Please** (`.github/workflows/release-please.yml`). Commits following [Conventional Commits](docs/SEMVER_CONVENTIONAL_COMMITS.md) automatically calculate semantic version bumps and maintain `CHANGELOG.md`.

---

## License

This project is licensed under the [MIT License](LICENSE).
