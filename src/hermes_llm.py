import asyncio
import contextlib
import json
import logging
import os
import random
import re
from typing import Any

import websockets
from livekit.agents import llm
from livekit.agents.llm import ChatChunk, ChatContext, ChoiceDelta, LLMStream

# Default connection options matching base LLM.chat signature
from livekit.agents.llm.llm import DEFAULT_API_CONNECT_OPTIONS

logger = logging.getLogger("hermes-llm")

# ---------------------------------------------------------------------------
# Lapis 1 — Voice instructions (plan ui-integration.md §4).
# Stateless: prepended to every prompt.submit, because LiveKit `instructions=`
# NEVER reach Hermes (hermes_llm only forwards the last user message).
# ---------------------------------------------------------------------------
VOICE_INSTRUCTIONS = """\
[VOICE MODE] You are on a voice call with the user.
- Reply in PLAIN TEXT only: no markdown, no code blocks, no lists/tables, no emoji, no raw URLs.
- 1-3 sentences, conversational, one question at a time.
- Spell out numbers, phone numbers and dates when they matter.
- NEVER use em dashes or en dashes (the long dash punctuation), and never use semicolons; they sound like missing pauses in speech. Use commas or full stops instead.
- Delivery cues: start EVERY reply with a bracket cue describing how the first sentence should be delivered. Use a core mood like [warm] [soft] [gentle] [cheerful] [excited] [calm] [serious] [playful] [empathetic], or when it fits better a short free-form direction such as [whispering] [laughing softly] [with quiet enthusiasm] [matter-of-fact tone]. If the emotional tone shifts mid-reply, you may add one more cue immediately before that later sentence (max 2-3 cues per reply, each directly before the sentence it styles). Keep cues lowercase, one or a few words, and never repeat the same cue in consecutive replies. Example: "[with quiet enthusiasm] Oh, that's a clever idea. [playful] How did you come up with it?" Cues are never spoken aloud — do not mention them, and do not use brackets for anything else.
- Language policy: ALWAYS reply in English. Switch to Indonesian ONLY when the user explicitly asks for Indonesian (e.g. "pakai bahasa Indonesia", "jawab dalam bahasa Indonesia", "ngomong bahasa Indonesia"). If the user switches back to Indonesian without such a request, keep replying in English.
- When you need to look something up, search, or run any tool: FIRST speak one short natural sentence about what you're checking (e.g. "Let me take a quick look.", "Give me a second to check that."), THEN run the tool. Never go silent while a tool is working.
- If asked for code or technical details: explain briefly in words; never output code or syntax."""

# ---------------------------------------------------------------------------
# Lapis 3 — Anti-silence filler engine (RE-ENABLED 2026-08-13, v2).
# Tool calls are silent: Hermes emits NO text deltas while a tool runs, so
# the user hears nothing for 10-30s. The pipeline starts TTS synthesis on
# the FIRST stream chunk (agent_activity._produce_segments), so an ack
# emitted at tool start is spoken while the tool is still executing — the
# voice overlaps the wait instead of prepending to it.
# Triggers: tool.generating → immediate ack; pure silence > deadline →
# timer fillers. Randomized, English, with Fish delivery cues.
# ---------------------------------------------------------------------------
FIRST_FILLER_DELAY = 3.0  # pure silence (no tool, no text) before filler 1
SECOND_FILLER_DELAY = 8.0  # still silent after filler 1 / tool ack
MAX_FILLERS = 2
FILLER_FIRST = [
    "[calm] One second, let me think.",
    "[soft] Hmm, give me a moment.",
    "[gentle] Let me think about that for a second.",
]
FILLER_TOOL = [
    "[warm] Let me check on that real quick.",
    "[calm] Give me a second, I'm looking into it.",
    "[soft] One moment, let me pull that up.",
]
FILLER_SECOND = [
    "[calm] Still working on it, hang tight.",
    "[soft] Almost there, just a little more.",
    "[gentle] This is taking a moment, thanks for waiting.",
]

# ---------------------------------------------------------------------------
# Lapis 2 — Sentence splitter + cleaner (TTS safety net).
# ---------------------------------------------------------------------------
_BOUNDARY_CHARS = ".!?\n"
_MIN_SENTENCE_LEN = 12  # guards abbreviations/decimals ("Dr.", "3.14")
_MAX_PENDING_LEN = 400  # force-cut so TTS latency stays bounded

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`([^`\n]*)`")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,3}[.)])\s+", re.MULTILINE)
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_HR_RE = re.compile(r"^\s{0,3}(?:-{3,}|={3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
_TABLE_PIPE_RE = re.compile(r"\|")
_EMPHASIS_RE = re.compile(r"[*_~]")
_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\u2190-\u21ff"
    "\u2300-\u23ff\u25a0-\u25ff\ufe00-\ufe0f\u200d\U0001f1e6-\U0001f1ff"
    "\u2764\u270c\u270b]"
)
_ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u2060\ufeff\u00ad]")
_CONTROL_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f]")
_REPEAT_PUNCT_RE = re.compile(r"([!?])\1+")
_MOJIBAKE: list[tuple[str, str]] = [
    ("\u00e2\u20ac\u201d", "-"),  # â€" → -
    ("\u00e2\u20ac\u201c", "-"),  # â€" → -
    ("\u00e2\u20ac\u0153", '"'),  # â€œ → "
    ("\u00e2\u20ac\u02dc", "'"),  # â€(lsquo) → '
    ("\u00e2\u20ac\u2122", "'"),  # â€™ → '
    ("\u00e2\u20ac\u00a6", "..."),  # â€¦ → ...
    ("\u00c3\u00a9", "\u00e9"),  # Ã© → é
    ("\u00c3\u00a8", "\u00e8"),  # Ã¨ → è
    ("\u00c3\u00a0", "\u00e0"),  # Ã  → à
    ("\u00e2\u20ac", '"'),  # bare â€ prefix catch-all — must stay last
]


def clean_voice_text(text: str) -> str:
    """Strip markdown/emoji/URLs/control chars from one chunk of voice text.

    Server-side mirror of the client's cleanVoiceText() (voice-text.ts).
    Preserves line breaks; collapses other whitespace.
    """
    if not text:
        return ""
    s = text

    # 1. Mojibake first (before stripping touches the byte-ish sequences).
    for bad, good in _MOJIBAKE:
        s = s.replace(bad, good)

    # 1b. Em/en dashes: Fish S2.1 Pro reads them with NO pause (they behave
    # like plain spaces). Convert to a comma so TTS gets a natural breath.
    # Absorb surrounding whitespace so "you — what" becomes "you, what".
    s = re.sub(r"\s*[\u2014\u2013]\s*", ", ", s)

    # 2. Code fences → spoken placeholder; inline code keeps its text.
    s = _CODE_FENCE_RE.sub(" [potongan kode] ", s)
    s = _INLINE_CODE_RE.sub(r"\1", s)

    # 3. Markdown links → link text.
    s = _MD_LINK_RE.sub(r"\1", s)

    # 4. URLs / emails → spoken words.
    s = _URL_RE.sub("link", s)
    s = _EMAIL_RE.sub("alamat email", s)

    # 5. Line-level markdown: hr, headings, bullets, quotes, table pipes.
    s = _HR_RE.sub("", s)
    s = _HEADING_RE.sub("", s)
    s = _BULLET_RE.sub("", s)
    s = _QUOTE_RE.sub("", s)
    s = _TABLE_PIPE_RE.sub(" ", s)

    # 6. Emphasis leftovers.
    s = _EMPHASIS_RE.sub("", s)

    # 7. Emoji, zero-width, control chars (keep \n).
    s = _EMOJI_RE.sub("", s)
    s = _ZERO_WIDTH_RE.sub("", s)
    s = _CONTROL_RE.sub("", s)

    # 8. Normalize repeated punctuation.
    s = _REPEAT_PUNCT_RE.sub(r"\1", s)

    # 9. Whitespace: newlines → space (voice text is read linearly), collapse
    # runs, cap blank lines, trim. (Newlines must become SPACES, not vanish,
    # or consecutive sentences run together: "Schnee.Semua sistem".)
    s = s.replace("\n", " ")
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    return s


def _split_sentence(buffer: str) -> tuple[str | None, str]:
    """Split the first complete sentence off the buffer.

    Returns (sentence, rest), or (None, buffer) when no complete sentence is
    available yet. Boundaries: `.`, `!`, `?`, newline. A minimum-length guard
    avoids cutting abbreviations/decimals mid-token; a max-pending cap
    force-cuts at the last space so TTS latency stays bounded.
    """
    for i, ch in enumerate(buffer):
        if ch in _BOUNDARY_CHARS and (ch == "\n" or i + 1 >= _MIN_SENTENCE_LEN):
            return buffer[: i + 1], buffer[i + 1 :]
    if len(buffer) > _MAX_PENDING_LEN:
        cut = buffer.rfind(" ")
        if cut > 0:
            return buffer[:cut], buffer[cut:].lstrip()
        return buffer, ""
    return None, buffer


async def _ws_reader(ws: Any, queue: asyncio.Queue) -> None:
    """Pump WS frames into a queue so the stream loop can race incoming
    events against the filler timeouts (a bare `async for` can't time out)."""
    try:
        async for raw in ws:
            await queue.put(raw)
    except Exception as exc:
        await queue.put(exc)
        return
    await queue.put(None)  # EOF sentinel


def _extract_last_user_text(messages: list) -> str:
    """Pull the last user message text out of provider-format messages."""
    for msg in reversed(messages):
        if msg is None or not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        user_text = ""
        if isinstance(content, list):
            for part in content:
                if part and isinstance(part, dict) and part.get("type") == "text":
                    user_text = part.get("text", "")
                    break
        else:
            user_text = str(content) if content else ""
        if user_text:
            return user_text
    return ""


class HermesLLM(llm.LLM):
    """Custom LLM that bridges to Hermes Agent via WebSocket."""

    def __init__(
        self,
        *,
        ws_url: str = "ws://127.0.0.1:9119/api/ws",
        token: str | None = None,
    ) -> None:
        super().__init__()
        self._ws_url = ws_url
        # Prefer env (set in .env.local); fallback keeps old setups working.
        self._token = token or os.environ.get("HERMES_WS_TOKEN", "")
        self._ws: Any = None
        self._session_id: str | None = None
        self._message_id = 0
        # Serializes WS protocol traffic only (short-lived), NOT the full stream
        self._ws_lock = asyncio.Lock()
        # Serializes the whole turn lifecycle (submit + WS read loop). Without
        # this, a second turn submitted while the first is still streaming
        # spawns a second `_ws_reader`, and two concurrent `ws.recv()` calls
        # raise websockets.ConcurrencyError. Holding the lock across submit +
        # read guarantees a single reader at a time; a barged-in turn's stream
        # is cancelled by the framework, releasing the lock for the next turn.
        self._turn_lock = asyncio.Lock()

    @property
    def model(self) -> str:
        return "hermes-agent"

    @property
    def provider(self) -> str:
        return "hermes"

    async def _connect(self) -> None:
        if self._ws is not None and getattr(self._ws, "open", False):
            return
        # Close half-open leftovers from a previous failed turn, if any.
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
        url = self._ws_url + "?token=" + self._token
        logger.info("Connecting to Hermes at %s", url.replace(self._token, "***"))
        self._ws = await websockets.connect(url, ping_interval=20, ping_timeout=20)
        logger.info("Connected to Hermes")

    def _invalidate_connection(self) -> None:
        """Force reconnect + fresh Hermes session on the next turn."""
        self._ws = None
        self._session_id = None

    async def _ensure_session(self) -> str:
        if self._session_id:
            return self._session_id

        async with self._ws_lock:
            await self._connect()

            # Wait for gateway.ready
            async for raw in self._ws:
                data = json.loads(raw)
                if (
                    data.get("method") == "event"
                    and data.get("params", {}).get("type") == "gateway.ready"
                ):
                    break

            # Create session
            self._message_id += 1
            create_id = self._message_id
            await self._ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": create_id,
                        "method": "session.create",
                        "params": {
                            "title": f"livekit-{asyncio.get_event_loop().time()}"
                        },
                    }
                )
            )

            async for raw in self._ws:
                data = json.loads(raw)
                if data.get("id") == create_id:
                    if "error" in data:
                        raise RuntimeError(f"Session create failed: {data['error']}")
                    self._session_id = data["result"]["session_id"]
                    break

            # Activate session
            self._message_id += 1
            activate_id = self._message_id
            await self._ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": activate_id,
                        "method": "session.activate",
                        "params": {"session_id": self._session_id},
                    }
                )
            )

            async for raw in self._ws:
                data = json.loads(raw)
                if data.get("id") == activate_id:
                    break

        logger.info("Hermes session created: %s", self._session_id)
        return self._session_id

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: Any = None,
        parallel_tool_calls: Any = None,
        tool_choice: Any = None,
        extra_kwargs: Any = None,
    ) -> LLMStream:
        if conn_options is None:
            conn_options = DEFAULT_API_CONNECT_OPTIONS
        return HermesLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )

    async def aclose(self) -> None:
        if self._ws:
            await self._ws.close()


class HermesLLMStream(LLMStream):
    """LLMStream implementation for Hermes Agent with voice formatting:
    Lapis 1 (instructions prepend), Lapis 2 (sentence cleaner),
    Lapis 3 (anti-silence filler engine)."""

    async def _run(self) -> None:
        hermes = self._llm
        loop = asyncio.get_running_loop()
        session_id = await hermes._ensure_session()

        # NOTE: to_provider_format returns a tuple (messages_list, tools)
        messages, _tools = self._chat_ctx.to_provider_format(format="openai")
        user_text = _extract_last_user_text(messages)
        if not user_text:
            logger.warning("No user text found in chat context")
            return

        # Serialize the whole turn (submit + read loop) so overlapping turns
        # never spawn concurrent `_ws_reader` tasks on the same socket.
        async with hermes._turn_lock:
            await self._run_turn(hermes, session_id, user_text, loop)

    async def _run_turn(
        self,
        hermes: "HermesLLM",
        session_id: str,
        user_text: str,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        # Lapis 1: prepend voice instructions (LiveKit `instructions=` never
        # reach Hermes — verified in code).
        submit_text = VOICE_INSTRUCTIONS + "\n\n" + user_text
        logger.info("Sending to Hermes: %s", user_text[:80])

        hermes._message_id += 1
        submit_id = hermes._message_id

        t_submit = loop.time()

        async with hermes._ws_lock:
            await hermes._ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": submit_id,
                        "method": "prompt.submit",
                        "params": {"session_id": session_id, "text": submit_text},
                    }
                )
            )

        # Reader task → queue so we can race WS events against filler timers.
        queue: asyncio.Queue = asyncio.Queue()
        reader = asyncio.create_task(_ws_reader(hermes._ws, queue))

        async def send_text(text: str) -> None:
            # Always terminate chunks on whitespace: the voice pipeline
            # concatenates deltas, so "satu." + "Dua" would become "satu.Dua"
            # — Fish TTS spells the glued token letter-by-letter and the
            # transcript shows the missing space.
            await self._event_ch.send(
                ChatChunk(
                    id="hermes",
                    delta=ChoiceDelta(role="assistant", content=text + " "),
                )
            )

        got_ack = False
        turn_over = False
        sentence_buffer = ""
        fillers_sent = 0
        t_first_delta: float | None = None
        t_first_sentence: float | None = None
        # Lapis 3 v2 (RE-ENABLED): arm the silence timer at submit. Tool
        # execution and long reasoning emit ZERO text deltas; the pipeline
        # starts TTS on the first chunk, so a filler emitted here overlaps
        # the wait instead of prepending to it (v1's analysis was wrong).
        filler_deadline: float | None = loop.time() + FIRST_FILLER_DELAY

        try:
            while not turn_over:
                timeout = None
                if filler_deadline is not None:
                    timeout = max(filler_deadline - loop.time(), 0.05)
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    # Silence exceeded deadline → emit next filler.
                    if fillers_sent == 0:
                        logger.info("Filler 1 after %.1fs silence", FIRST_FILLER_DELAY)
                        await send_text(random.choice(FILLER_FIRST))
                        fillers_sent = 1
                        filler_deadline = loop.time() + SECOND_FILLER_DELAY
                    elif fillers_sent < MAX_FILLERS:
                        logger.info(
                            "Filler 2 after %.1fs more silence", SECOND_FILLER_DELAY
                        )
                        await send_text(random.choice(FILLER_SECOND))
                        fillers_sent += 1
                        filler_deadline = None
                    else:
                        filler_deadline = None
                    continue

                if isinstance(item, BaseException):
                    hermes._invalidate_connection()
                    raise RuntimeError(f"Hermes WS error: {item}") from item
                if item is None:  # EOF sentinel
                    hermes._invalidate_connection()
                    raise RuntimeError("Hermes WS closed mid-turn")

                try:
                    data = json.loads(item)
                except json.JSONDecodeError:
                    continue

                # JSON-RPC response (ack or error)
                if data.get("id") == submit_id:
                    if "error" in data:
                        raise RuntimeError(f"Submit failed: {data['error']}")
                    got_ack = True
                    logger.info("Hermes submit ack: %s", data.get("result"))
                    continue

                if data.get("method") != "event":
                    continue

                params = data.get("params", {})
                event_type = params.get("type")
                payload = params.get("payload", {}) or {}

                if event_type == "message.delta":
                    delta = payload.get("text", "")
                    if delta:
                        if t_first_delta is None:
                            t_first_delta = loop.time()
                            logger.info(
                                "Hermes TTFT: %.2fs after submit",
                                t_first_delta - t_submit,
                            )
                        filler_deadline = None  # real text flowing → no fillers
                        sentence_buffer += delta
                        # Lapis 2: cut complete sentences, clean, yield.
                        while True:
                            sentence, sentence_buffer = _split_sentence(sentence_buffer)
                            if sentence is None:
                                break
                            cleaned = clean_voice_text(sentence)
                            if cleaned:
                                if t_first_sentence is None:
                                    t_first_sentence = loop.time()
                                    logger.info(
                                        "First sentence to TTS: %.2fs after submit",
                                        t_first_sentence - t_submit,
                                    )
                                await send_text(cleaned)
                elif event_type == "thinking.delta":
                    # Thinking produces NO audio for the user — keep the
                    # silence timer running (v1 wrongly treated thinking
                    # activity as user-perceptible activity).
                    pass
                elif event_type == "tool.generating":
                    tool_name = payload.get("name", "?")
                    logger.info("Hermes tool started: %s", tool_name)
                    # Speak immediately: the ack is synthesized while the
                    # tool is still executing, so the voice OVERLAPS the
                    # wait. Fire ONLY if nothing was spoken yet this turn
                    # (no real text — those cancel the timer — and no
                    # timer filler, else the user hears two back-to-back
                    # acknowledgments).
                    if filler_deadline is not None and fillers_sent == 0:
                        logger.info("Tool ack before: %s", tool_name)
                        await send_text(random.choice(FILLER_TOOL))
                        fillers_sent += 1
                        filler_deadline = loop.time() + SECOND_FILLER_DELAY
                elif event_type == "tool.complete":
                    logger.info("Hermes tool complete")
                    if filler_deadline is not None and fillers_sent < MAX_FILLERS:
                        filler_deadline = loop.time() + SECOND_FILLER_DELAY
                elif event_type in (
                    "message.complete",
                    "turn.complete",
                    "session.turn_end",
                ):
                    logger.info(
                        "Hermes turn complete (event=%s, ack=%s, total=%.2fs)",
                        event_type,
                        got_ack,
                        loop.time() - t_submit,
                    )
                    turn_over = True
                elif event_type == "error":
                    logger.error("Hermes error event: %s", payload)
                    turn_over = True
        finally:
            reader.cancel()

        # Flush any trailing partial sentence.
        if sentence_buffer.strip():
            cleaned = clean_voice_text(sentence_buffer)
            if cleaned:
                await send_text(cleaned)
