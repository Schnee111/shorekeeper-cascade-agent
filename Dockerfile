# syntax=docker/dockerfile:1
# Shorekeeper Cascade Agent — Production Multi-Stage Dockerfile
# Optimized for 3.6GB RAM VPS with glibc-based slim Debian bookworm (manylinux compatible)

ARG PYTHON_VERSION=3.11
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/app/.cache/huggingface \
    TORCH_HOME=/app/.cache/torch

# --- Build stage: resolve & install dependencies ---
FROM base AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    libasound2-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache dependency layer
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Cache pre-downloaded LiveKit model weights in Docker layer
RUN uv run --module livekit.agents download-files || true

# Copy application source code
COPY . .
RUN uv sync --locked --no-dev

# --- Production stage: lean runtime image without compiler toolchains ---
FROM base AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 \
    curl \
  && rm -rf /var/lib/apt/lists/*

ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

WORKDIR /app

# Copy application and virtualenv from build stage
COPY --from=build --chown=appuser:appuser /app /app

USER appuser

EXPOSE 8081 8082

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://127.0.0.1:8081/ || exit 1

CMD ["uv", "run", "src/agent.py", "start"]
