import asyncio
import contextlib
import json
from unittest.mock import patch

import pytest
from livekit.agents.llm import ChatChunk, ChatContext
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from websockets.protocol import State

from hermes_llm import HermesLLM, HermesLLMStream, _split_sentence, clean_voice_text


class MockEventChannel:
    def __init__(self):
        self.events = []
        self._closed = False

    async def send(self, event):
        self.events.append(event)

    def close(self):
        self._closed = True


class MockWebSocket:
    def __init__(self, incoming_events: list | None = None):
        self.incoming_events = list(incoming_events or [])
        self.sent_messages: list[dict] = []
        self.state = State.OPEN
        self._closed = False

    async def send(self, data: str):
        self.sent_messages.append(json.loads(data))

    async def recv(self):
        if not self.incoming_events:
            await asyncio.sleep(0.01)
            raise asyncio.TimeoutError()
        ev = self.incoming_events.pop(0)
        return json.dumps(ev)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.incoming_events:
            raise StopAsyncIteration
        ev = self.incoming_events.pop(0)
        return json.dumps(ev)

    async def close(self, code: int = 1000, reason: str = ""):
        self._closed = True
        self.state = State.CLOSED


class HangingAfterStartWebSocket(MockWebSocket):
    """Mock WebSocket that emits initial events then hangs indefinitely on iteration."""

    async def __anext__(self):
        if self.incoming_events:
            ev = self.incoming_events.pop(0)
            if isinstance(ev, BaseException):
                raise ev
            import json

            return json.dumps(ev)
        # Hang indefinitely instead of terminating iteration
        await asyncio.sleep(10.0)
        raise StopAsyncIteration


def test_clean_voice_text_markdown_links_and_bracket_cues():
    # Link should have markdown stripped to link text and not get mangled with bracket cues
    text = "Lihat [dokumentasi](https://example.com) untuk detail."
    cleaned = clean_voice_text(text)
    assert "dokumentasi" in cleaned
    assert "https://" not in cleaned
    assert "[" not in cleaned and "]" not in cleaned


def test_clean_voice_text_prosody_bracket_cues():
    text = "[warm] Halo Schnee, [soft] selamat pagi."
    cleaned = clean_voice_text(text)
    assert cleaned == "Halo Schnee, selamat pagi."


def test_clean_voice_text_codeblocks_and_inline_code():
    raw = "Berikut kode:\n```python\nprint('hello')\n```\nJalankan `uv run pytest`."
    cleaned = clean_voice_text(raw)
    assert "print('hello')" not in cleaned
    assert "uv run pytest" in cleaned


def test_split_sentence_forced_cut_punctuation():
    # Buffer exceeds 250 chars without sentence ending punctuation
    words = ["kata" for _ in range(70)]
    long_buffer = " ".join(words)
    chunk, rest = _split_sentence(long_buffer)
    assert chunk is not None
    # Must end with comma breath pause
    assert chunk.endswith(",")
    assert len(rest) > 0


def test_split_sentence_forced_cut_without_spaces_punctuation():
    # Long continuous token without spaces exceeding 250 chars
    long_buffer = "a" * 260
    chunk, rest = _split_sentence(long_buffer)
    assert chunk is not None
    assert chunk.endswith(",")
    assert rest == ""


@pytest.mark.asyncio
async def test_streaming_pipeline_applies_clean_voice_text():
    """Verify that HermesLLMStream._run_turn applies clean_voice_text to streamed sentences."""
    llm = HermesLLM(ws_url="ws://127.0.0.1:9119/api/ws")
    llm._session_id = "sess-clean-streaming"

    events = [
        {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}},
        {"method": "event", "params": {"type": "message.start", "payload": {}}},
        {
            "method": "event",
            "params": {
                "type": "message.delta",
                "payload": {
                    "text": "[warm] Cek [panduan kami](https://example.com) untuk info! "
                },
            },
        },
        {"method": "event", "params": {"type": "message.complete", "payload": {}}},
    ]
    mock_ws = MockWebSocket(incoming_events=events)
    llm._ws = mock_ws

    ctx = ChatContext()
    ctx.add_message(role="user", content="Tolong panduannya")
    stream = HermesLLMStream(
        llm, chat_ctx=ctx, tools=[], conn_options=DEFAULT_API_CONNECT_OPTIONS
    )
    stream._task.cancel()
    event_ch = MockEventChannel()
    stream._event_ch = event_ch

    await stream._run()

    received_texts = [
        ev.delta.content for ev in event_ch.events if isinstance(ev, ChatChunk)
    ]
    combined = " ".join(received_texts)
    # [warm] should be stripped
    assert "[warm]" not in combined
    # [panduan kami](...) should be cleaned to panduan kami
    assert "panduan kami" in combined
    assert "https://" not in combined
    assert "[" not in combined and "]" not in combined


@pytest.mark.asyncio
async def test_turn_activity_timeout_invalidation_and_fallback():
    """Verify that exceeding ACTIVITY_TIMEOUT triggers connection invalidation and voice fallback."""
    llm = HermesLLM(ws_url="ws://127.0.0.1:9119/api/ws")
    llm._session_id = "sess-activity-timeout"

    # Event starts, then dead air (no further frames sent)
    events = [
        {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}},
        {"method": "event", "params": {"type": "message.start", "payload": {}}},
    ]
    mock_ws = HangingAfterStartWebSocket(incoming_events=events)
    llm._ws = mock_ws

    ctx = ChatContext()
    ctx.add_message(role="user", content="Halo?")
    stream = HermesLLMStream(
        llm, chat_ctx=ctx, tools=[], conn_options=DEFAULT_API_CONNECT_OPTIONS
    )
    # Cancel auto-started background task and suppress unretrieved exception in test
    stream._task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await stream._task

    event_ch = MockEventChannel()
    stream._event_ch = event_ch

    # Patch ACTIVITY_TIMEOUT to 0.05s for fast testing
    with patch("hermes_llm.ACTIVITY_TIMEOUT", 0.05):
        await stream._run()

    # Turn lock and WS lock must be released
    assert not llm._turn_lock.locked()
    # WS must be invalidated
    assert llm._ws is None

    received_texts = [
        ev.delta.content for ev in event_ch.events if isinstance(ev, ChatChunk)
    ]
    assert any("assistant connection timed out" in t for t in received_texts)
