# Dual-Tier Voice Architecture: Realtime Frontline (Gemini Live) + Async Deep-Reasoning Engine (Hermes)

**Research date:** 2026-08-15
**Scope:** Patterns, communication protocols, state management, edge-case strategies, and a concrete component breakdown for the Python / LiveKit / Hermes stack.

---

## 1. Executive Summary

The architecture splits the assistant into two cooperating tiers:

```
 User (audio)
    │  WebRTC (LiveKit) / Gemini Live WebSocket
    ▼
 ┌─────────────────────────────────────────────────────────┐
 │ TIER 1 — Voice Frontline (latency-critical)             │
 │ Gemini Live API (gemini-2.5-flash-live-preview)         │
 │  • conversational pacing, banter, fillers, barge-in     │
 │  • turn/segment ownership of the live audio session     │
 └───────────────┬─────────────────────────────────────────┘
                 │ 1. tool_call event: {name: "dispatch_task", args}
                 │ 2. immediate audio ACK ("…on it now")
                 ▼
 ┌─────────────────────────────────────────────────────────┐
 │ TIER 2 — Deep Reasoning & Action Engine (latency-OK)    │
 │ Hermes Agent (high-reasoning LLM, api_server or WS      │
 │ bridge or subprocess) — research / coding / multi-tool   │
 │  • owns long-run tool chains, planning, verification     │
 └───────────────┬─────────────────────────────────────────┘
                 │ 3. done: {task_id, summary, artifacts}
                 ▼
 ┌─────────────────────────────────────────────────────────┐
 │ INJECTION GATE (Tier 1) — freshness, relevance,         │
 │ coalescing, idle-gating  →  send_tool_response          │
 │ with scheduling: WHEN_IDLE (default) / INTERRUPT /      │
 │ SILENT                                                   │
 └───────────────┬─────────────────────────────────────────┘
                 │ 4. "…and here's what I found."
                 ▼
             User (audio)
```

**Core design facts (verified against primary sources, 2026-08-15):**

- **Gemini Live API has first-class asynchronous function calling.** All function
  calls can be non-blocking; slow tools are dispatched to the client's own background
  tasks while the model keeps listening/speaking. Results are *pushed back* with
  `session.send_tool_response(function_responses=[...])` where each response carries a
  `scheduling` policy: `SILENT` | `WHEN_IDLE` | `INTERRUPT`. **(This is the native
  "background result injection" primitive — the entire Tier-1→Tier-2 loop can ride on
  it without any hacks.)** Async function calling is supported on
  `gemini-2.5-flash-live-preview`; **not yet on `gemini-3.1-flash-live-preview`**
  (3.1 is synchronous: the model stays silent until the tool response arrives — the
  pattern below still works, but the SILENT/WHEN_IDLE/INTERRUPT scheduling is the 2.5
  capability).
- **LiveKit async tools** (livekit-agents ≥ 1.6.0) provide the same pattern for the
  independent STT→LLM→TTS pipeline: `ctx.update(msg)` (first call releases the turn so
  the agent acknowledges instantly), `ctx.with_filler(...)` (dwell-gated acoustic
  fillers), `ToolFlag.CANCELLABLE` + auto-exposed `get_running_tasks()` /
  `cancel_task(call_id)`, `on_duplicate=` dedup modes, `ctx.foreground()` for
  mid-task interactive clarification, and `AsyncToolset` to survive agent handoffs.
- **The agent already owns the Tier-2 channel**: `hermes_llm.py` implements a verified
  WS-bridge client (`ws://127.0.0.1:9119/api/ws`) to the Hermes gateway. In the new
  architecture this same client becomes the *dispatcher* for Tier 2 instead of the
  inline LLM. The Hermes **HTTP API server** (`/v1/runs` + SSE + `/stop` + `/approval`)
  is the complementary channel for long, unattended missions.
- **Interruption ≠ cancellation.** User barge-in interrupts the *voice*; the background
  task keeps running until explicitly cancelled. Keep those two signal paths separate.

---

## 2. Pattern A — Async Tool Invocation + Conversational ACK

### 2.1 Gemini Live API (recommended Tier-1 core)

**Mark the slow tool as non-blocking** in the session config (2.5 Live):

```python
tools = [
    {
        "function_declarations": [
            {
                "name": "dispatch_task",
                "description": (
                    "Delegates heavy research, coding, or multi-step work to the "
                    "background reasoning agent (Hermes). Takes 10s–10min. Fire and "
                    "forget; you will receive the result later and should summarize it "
                    "naturally. For trivial lookups, answer directly."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "context": {"type": "string"},  # distilled digest, see §4.3
                        "artifact_path": {
                            "type": "string",
                            "description": "optional save path",
                        },
                    },
                    "required": ["objective"],
                },
                "behavior": "NON_BLOCKING",  # async function calling (2.5 Flash Live)
            }
        ]
    }
]
config = {"response_modalities": ["AUDIO"], "tools": tools}
```

**Receive-loop rule — never `await` slow work in the receive loop:**

```python
async for response in session.receive():
    if response.data is not None:
        audio_sink.write(response.data)
    elif response.server_content and response.server_content.interrupted:
        audio_sink.clear()  # barge-in: discard unplayed buffer
    elif response.tool_call is not None:
        for fc in response.tool_call.function_calls:
            if fc.name == "dispatch_task":
                # ACK immediately via an injected client turn, THEN spawn:
                await session.send_client_content(
                    turns={
                        "parts": [
                            {
                                "text": "Briefly acknowledge you are starting this task, "
                                "then hand control back: 'working on it'."
                            }
                        ]
                    }
                )
                asyncio.create_task(hermes_dispatcher(fc.id, fc.args, session))
            else:
                await fast_local_tool(fc.id, fc.args, session)  # safe to await
```

**The ACK trick (official recommendation):** the client injects a *client-content text
turn* right after receiving the `tool_call`, instructing the model to voice an
acknowledgement ("I'm booking your ticket now, please wait" is Google's example). This:
(1) prevents dead air, (2) reduces "hello? are you there?" re-prompts, (3) lowers the
probability of duplicate function calls caused by user re-impatience. Phase-aware ACKs
can be rotated by the dispatcher ("On it — this is the deep one, give me a couple
minutes."). For even faster ack, play a locally cached pre-synthesized filler
(their existing filler engine; ~10–50 ms) as a client-side audio turn.

**Completion — push the result back through the tool-response channel:**

```python
await session.send_tool_response(
    function_responses=[
        types.FunctionResponse(
            id=call_id,  # MUST match the original function call id
            name="dispatch_task",
            response={"status": "ok", "summary": result_summary, "artifacts": [...]},
            scheduling="WHEN_IDLE",  # the injection policy, §3.1
        )
    ]
)
```

### 2.2 LiveKit async tools (if Tier-1 runs the LiveKit pipeline instead)

```python
from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolFlag


@function_tool(flags=ToolFlag.CANCELLABLE, on_duplicate="reject")
async def dispatch_task(ctx: RunContext, objective: str, context: str = "") -> str:
    """Delegate heavy work to the Hermes background agent. Returns the spoken summary."""
    await ctx.update(
        f"Starting on: {objective[:80]}. This one goes to the deep engine."
    )  # seed = LLM-voiced ack, instant
    async with ctx.with_filler(
        lambda step: [
            "Still digging into that…",
            "Deep reasoning takes a moment…",
            "Almost there…",
        ][step],
        delay=4,
        interval=6,
        max_steps=3,
    ):
        # Python cancellation semantics: cancel_task(call_id) raises
        # asyncio.CancelledError *inside* this tool -> structure the Hermes call so
        # cancellation propagates cleanly (cancel the pending task handle); wrap
        # non-cancel-safe phases in ctx.disallow_interruptions().
        result = await hermes_dispatcher(objective, context, call_id=ctx.call_id)
    return result.summary  # voiced when the session is next idle
```

- First `ctx.update()` is the **boundary between blocking and async**: it hands the
  LLM its synthetic return value immediately, unblocking the turn.
- Prefer `ctx.update()` for events the LLM must know (start, phase change, final),
  `ctx.with_filler()` for acoustic fills it doesn't need to track. Never double-voice
  both for the same event.
- **Prompt templates** (`tool_handling = {"async_options": {"update_template": …}}`)
  control how updates are voiced; e.g. "Acknowledge briefly, phrase as **still in
  progress**, never announce completion." The final tool return is the *only* line
  that announces completion (verified recommendation from LiveKit's refund demo).

### 2.3 OpenAI Realtime API (reference pattern, same shape)

Protocol: `response.done` yields `function_call` item (`call_id`) → run tool in
background → when finished, `conversation.item.create` with
`{"type": "function_call_output", "call_id": …, "output": …}` → `response.create` to
trigger the model to speak. For an immediate ACK, push a second item right after the
call (`conversation.item.create` with a system/user message + `response.create`).
Caveats: delaying `function_call_output` is the sanctioned "async" behavior; there is
no native `scheduling` policy — idle-gating is app-side (only emit
`response.create` when the conversation is quiescent). OpenAI's own guardrail recipe
(interrupt active response → `response.cancel` → inject follow-up user message →
`response.create`) is the canonical "unsolicited push" idiom and applies directly to
"Tier-2 finished, make the model speak now."

---

## 3. Pattern B — Event Injection & Interruption Management

### 3.1 The injection gate (Gemini: `scheduling` policy)

| Policy | Semantics | Use |
|---|---|---|
| `SILENT` | Result added to model context; **no spoken narration**; active interaction unaffected | Status/facts the model should remember but not announce; avoided double-answers |
| `WHEN_IDLE` | Model answers result only once the current user interaction completes — never cuts someone off | **Default for Tier-2 completions** |
| `INTERRUPT` | Model stops current response and announces the result immediately | Critical alerts only (errors, user-requested "tell me the second it's done") |

- **Avoid `INTERRUPT` for routine results** — it is jarring and discards the
  in-flight narration.
- **The SILENT caveat (official):** the model may still narrate a SILENT result;
  enforce true silence with explicit system instructions ("Perform SILENT EXECUTION
  and say nothing for tool X") or omit `send_tool_response` entirely for
  fire-and-forget jobs (context stays clean, result never enters state).
- **Injection is client-side orchestration, not model-side**: the model never
  "decides" to announce — the client decides *when* to send the response and *which
  policy* to use. This is the right inversion: Tier-2 completion arrives on an
  arbitrary thread/time, and the injection gate owns politeness.

### 3.2 The injection gate (LiveKit idle-gating, built-in)

LiveKit's async-tool machinery already gates: `ctx.update()` messages are surfaced
only when both agent and user are idle; `with_filler` only plays after continuous
session idle `delay` seconds, never over user speech. `ctx.foreground()` blocks other
agent speech while a sub-task interactively asks the user something the background
job needs (missing param, confirmation). Keep the Tier-1 system prompt scoped so the
voice model *summarizes, never dumps* results (their existing
"2–3 sentences + follow-up question" rules apply to injected results too).

### 3.3 Injection timing rules (stack-agnostic)

1. **Freshness gate** — drop or re-rank results older than a task TTL (default ~15 min
   for ambient results; remember user-solicited ones regardless).
2. **Relevance gate** — before pushing, the frontline must judge "is this still what
   the user is doing?" (WHEN_IDLE + an update template that permits silent dropping of
   stale updates; for Gemini, `SILENT` + instructions).
3. **Coalescing** — never inject two completions concurrently. Queue them; if the
   user talks, merge: "Also, while you were typing — X finished, Y finished."
   (LiveKit's `reply_maybe_covered` template exists precisely for this.)
4. **One-spoken-injection-at-a-time** — an injection turn reserves the floor until
   the user responds or the next turn starts.
5. **Never inject over music/pause-by-design UI states**; respects `allow_interruptions`.

### 3.4 Barge-in vs cancellation (keep the two paths separate)

| Event | Voice behavior | Background task behavior |
|---|---|---|
| User talks over Tier-1 (barge-in) | Stop/truncate playback; Gemini: `server_content.interrupted` → clear audio buffer; LiveKit: `InterruptionOptions`; OpenAI: `conversation.item.truncate` | **Continues running** (result may still be delivered later) |
| User says "cancel that / never mind" | Acknowledge; end topic | **Must actually abort**: LiveKit `cancel_task(call_id)` (raises `CancelledError` in the tool) or your own cancel token propagated over the Tier-2 channel (§7.2) |

---

## 4. State Management & Context Synchronization

### 4.1 Task lifecycle record (single source of truth in Tier-1)

```jsonc
{
  "task_id": "t_01J3…",            // uuid; the ONLY join key both tiers share
  "fc_call_id": "fc_abc123",        // Gemini function-call id (reply must echo it)
  "objective": "…",                 // user intent, normalized
  "status": "pending|running|done|cancelled|failed|expired",
  "fired_at": "…", "ttl": 900,
  "pending_result": null,           // parked completion while user talks
  "coalesced_ids": [],              // merged completions
  "dispatch_channel": "api_server|ws_bridge|subprocess"
}
```

- Keep a small in-memory `TaskRegistry` (dict + asyncio locks) per voice session;
  persist nothing unless you need crash recovery (then SQLite, mirroring
  `state.db` habits).
- **Single-flight rule**: one `dispatch_task` call per objective hash. Duplicate
  `tool_call` events with no response yet are *ignored client-side* (Google's
  documented duplicate policy) or handled by `on_duplicate="reject|confirm"` in
  LiveKit.

### 4.2 Context handoff: Tier-1 → Tier-2 (the TaskPacket)

Never ship the raw transcript. Build a distilled packet:

```jsonc
{
  "task_id": "t_…", "objective": "…",
  "digest": "Last 8 exchanges, entity list, files mentioned, decision constraints",
  "voice_constraints": {"max_words": 160, "must_end_with_followup": true,
                        "tone": "warm, concise", "include_delivery_cue": true},
  "retrieval_pointers": ["/home/ubuntu/projects/jarvis-livekit", "session:jarvis-main"],
  "cancel_token": "/stop?task=t_…",          // see §7.2
  "return_spec": {"summary": "string", "full_result_path": "string",
                  "sources": ["…"], "confidence": 0.0–1.0}
}
```

The Tier-2 prompt should be self-contained (their `hermes_llm.py` already forwards
only the *last* user message + `VOICE_INSTRUCTIONS`, so the dispatcher must compose
the full objective/digest — this is an existing constraint, not a new one).
Short-lived tasks get fresh context; **long-lived recurring context** (persona,
preferences, standing goals) comes from Hermes memory, not from the packet.

### 4.3 Context sync: Tier-2 → Tier-1

- **Result envelope**: `{task_id, status, summary (pre-trimmed for voice), artifacts,
  sources, confidence, completed_at}`. The frontline stores it in
  `pending_result`, and the *injection gate* (not the model) decides when to speak.
- **Transcript feed-forward**: the voice session's `use_tts_aligned_transcript`
  already gives an aligned user/agent transcript — feed the *digest* of it (not raw
  audio) to Tier-2 for follow-up work ("continue that research").
- **Memory ownership (single-writer rule)**: Tier-2 (Hermes) is the long-term-memory
  *writer* (MEMORY.md / USER.md / state.db sessions); Tier-1 is a *reader* of a
  voice-friendly digest. Avoid two Hermes processes writing memory concurrently —
  run Tier-2 dispatches with session-scoped memory keys
  (`X-Hermes-Session-Key`, or `skip_memory=True` equivalent via cron-style config) or
  accept the existing rsync-newer-wins cron as the merge strategy. When Tier-1 is a
  custom Gemini session, Tier-1 memory = Gemini's own session/LTM; the durable
  cross-session memory lives in Hermes.

### 4.4 Session continuity

- One Hermes session per conversation channel (`jarvis-main`) via
  `X-Hermes-Session-Id` or `/api/sessions/*` — successive Tier-2 dispatch runs share
  context *within* Hermes, so the voice layer doesn't re-send accumulated history.
- Gemini side: tools/config are fixed at session setup (reconfiguring tools mid-
  session is not supported) → keep `dispatch_task` registered for the whole session;
  the async mechanism makes "broad tool always present" harmless.

---

## 5. Communication Protocols (Tier-1 ↔ Hermes Tier-2)

Four viable channels; choose per job class.

| Channel | Latency/overhead | Semantics | Best for |
|---|---|---|---|
| **A. In-process Hermes client inside the async tool** (reuse `hermes_dispatcher` from `hermes_llm.py` — same WS protocol, `prompt.submit` + streaming events) | ~TTFT of gateway; reuses verified two-phase ack + stale-event drain logic | Long-lived orchestrator worker session; streaming deltas can become `ctx.update()` progress | **Default** |
| **B. Hermes HTTP API server** `POST /v1/runs` (SSE events) + `GET /v1/runs/{id}` + `POST /v1/runs/{id}/stop` + `/approval` | per-mission | OpenAI-compatible; built-in cancellation, approvals, concurrency caps, session continuity headers | Long unattended missions; scale-out; multi-tenant |
| **C. Subprocess** `hermes chat -q "<TaskPacket json>"` (or tmux for interactive) | process spawn cost | fire-and-forget; write summary to artifact path, poll file | Quick one-shots; isolation; no gateway dep |
| **D. Hermes Kanban board** (`hermes kanban`, `HERMES_KANBAN_TASK` worker dispatch, `kanban_complete` etc.) | durable queue | SQLite-backed work queue; dispatcher promotes ready tasks; failure limits | Multiple parallel Tier-2 jobs; crash recovery |

**Recommendation:** **A for interactive background work** (it is the natural
continuation of the existing WS bridge and inherits the already-fixed pitfalls:
`message.start`/`turn.complete` gating, stale-event drain, early-ack timer), **B for
long/autonomous missions**, **D once parallelism > ~3 jobs**. Keep a thin
`Dispatcher` interface so the channel is swappable per task.

Envelope framing on any channel: JSON TaskPacket in, JSON ResultEnvelope out
(§4.2/§4.3). Include `task_id` everywhere; the frontier never re-keys results by text.

---

## 6. Edge Cases & Strategies

| Edge case | Strategy |
|---|---|
| **User changes topic while task runs** | Keep the task running (it's cheap; user may return). Inject with `WHEN_IDLE` + relevance gate; if the model judges it stale (update template/instructions: "if this update is no longer relevant, acknowledge silently or not at all"), drop or park it. Parked results live in `pending_result` and surface if the user later asks "did that ever finish?" |
| **User cancels** | Tier-1 detects intent ("cancel that") → for Gemini: simply never send the `FunctionResponse` (the model never learns it existed — zero phantom state); for LiveKit: LLM calls `cancel_task(call_id)` → `CancelledError` inside the tool. **Both tiers must abort**: propagate a cancel token into the Hermes dispatch (`/v1/runs/{id}/stop`, or write a cancel file / send kill to the subprocess). Define cancel-safe phases in Tier-2 prompts for long missions (checkpoint before destructive steps). |
| **Duplicate dispatch** | Ignore duplicate `tool_call` for pending call ids (Gemini official guidance); LiveKit `on_duplicate="reject"` (then LLM is told to use `cancel_task`), or `"confirm"` for expensive ops. Objective-hash single-flight in `TaskRegistry` regardless of channel. |
| **Latency mismatch (Tier-2 takes 1–20+ min)** | ACK instantly (injected client turn / pre-synth filler at ~10–50 ms). Stage progress via Tier-2 streaming deltas → periodic `ctx.update()`/parked updates. Dwell fillers only after continuous idle ≥4–6 s (their proven dwell config), max ~2 per turn, race-grace ~1.5 s before speaking. Warn once for genuinely long jobs ("this usually takes a few minutes"). |
| **Barge-in during result narration** | Gemini: handle `server_content.interrupted` (clear audio buffer; only already-sent content retained). LiveKit: `InterruptionOptions` + truncation; the tool result is still delivered on the *next* idle turn — never re-announce mid-barge-in. |
| **Task fails / returns garbage** | Tier-2 result includes `confidence` + `status=failed|needs_verification`; the injection gate: (a) tell the truth briefly, (b) offer retry, (c) never let Tier-1 fabricate a summary of a failed run. Retry with exponential backoff ≤2 attempts for transient (429/timeout); surface persistent failures as follow-up suggestions. Hermes `/v1/runs` failures visible via SSE `error` events and `finish_reason`. |
| **Session ends / handoff while running** | Decide policy explicitly: (a) **drain** — finish, then post result into the next session's context (LiveKit `AsyncToolset` keeps running tools and pending updates alive across agent handoffs), or (b) **cancel** on `session ended`. For Hermes missions, let them finish server-side and store to artifact path; the voice layer reads it on next session start. |
| **Concurrency limits** | Hermes gateway in-flight cap → 429 `concurrency_limit_exceeded` on `/v1/runs`; queue locally (asyncio.Queue) before dispatching; keep ≤2 parallel Tier-2 jobs per conversation. |
| **Security/approvals** | Unattended Tier-2 needs `approvals.mode: off` or the explicit `/v1/runs/{id}/approval` flow; never run approving-mode Hermes from a voice loop without a human channel. Mute cost/spend accounting per task_id. |
| **Two Tier-2 jobs for one user turn** | Coalesce: single injection turn "X done and Y done." Prefer sequential dispatch (frontline instructs Hermes to break work into a single multi-step mission rather than N parallel tasks). |

---

## 7. Concrete Component Breakdown (Python / LiveKit / Hermes)

```
jarvis-livekit/src/
├── agent.py                  # Tier-1 LiveKit Agent (Gemini Realtime plugin OR pipeline)
│                             #   - registers dispatch_task tool, owns TaskRegistry
├── gemini_orchestrator.py    # NEW: Gemini Live session wrapper
│     - receive loop (audio sink / tool_call / interrupted)
│     - send_client_content ACK injection
│     - pending_result store + injection gate (freshness/relevance/coalesce)
│     - send_tool_response(scheduling=…)
├── hermes_dispatcher.py      # NEW: unified Tier-2 client (channels A/B/C/D)
│     - TaskPacket builder (digest, voice_constraints, return_spec)
│     - channel drivers: ws_bridge (reuse hermes_llm.py plumbing),
│       api_server (/v1/runs, SSE, /stop), subprocess, kanban
│     - cancel token propagation; retry/backoff; timeout
├── hermes_llm.py             # KEEP (becomes ws-bridge driver for dispatcher)
├── filler_engine.py          # KEEP (pre-synth fillers; now also drives
│                             #   Gemini client-turn ACKs + LiveKit with_filler)
└── task_registry.py          # NEW: task lifecycle store (single-flight, TTL,
                              #   parking, coalescing)
```

**Sequence — dispatch:**

```
User: "…can you research vector DBs for me and update the doc?"
Gemini Live:  tool_call {dispatch_task, args:{objective,digest}}
└─ Tier-1:  send_client_content("acknowledge briefly")  → "On it — this is the
│           deep one, expect a few minutes."   [<1–2 s]
└─ Tier-1:  asyncio.create_task(hermes_dispatcher(...))   [never blocks receive()]
└─ Hermes:  gateway WS/API run; streams deltas → Tier-1 parks progress updates
   └─ user talks about the weather meanwhile → Gemini answers normally (parallel!)
```

**Sequence — injection:**

```
Hermes completes → ResultEnvelope {task_id, summary, artifacts}
└─ Tier-1 injection gate: fresh? relevant? idle?
   ├─ idle        → send_tool_response(scheduling="WHEN_IDLE")
   │                → Gemini voices "…here's what I found: …"  (+ audio stream)
   ├─ user active → park in pending_result; inject after their turn completes
   └─ stale       → drop or SILENT-park; answer only if user asks later
```

**Recommended rollout phases:**

1. **Phase 0 (already in place):** WS bridge + filler engine + barge-in handling —
   keep as-is; they are the Tier-1→Tier-2 plumbing.
2. **Phase 1:** Introduce `dispatch_task` async tool on the *current* pipeline
   (LiveKit async tools, `ctx.update` + `with_filler` + `CANCELLABLE`) with Hermes
   as the executor — instantly kills TTFT-dead-air for deep tasks and proves the
   dispatcher/envelope design end-to-end.
3. **Phase 2:** Swap Tier-1 core to Gemini Live (2.5) with `behavior: NON_BLOCKING`
   + `scheduling` policies; reuse the same `hermes_dispatcher`.
4. **Phase 3:** Add `/v1/runs` channel for long missions + kanban for parallelism;
   wire cross-session memory ownership (single-writer).

---

## 8. Sources (primary, fetched 2026-08-15; raw dumps in /home/ubuntu/research/)

- LiveKit Docs — *Async tools* (docs.livekit.io/agents/logic/tools/async/), *Tasks &
  task groups* (agents/logic/tasks/), *Workflows* (agents/logic/workflows/)
- LiveKit Blog — *Async Tools for Voice Agents* (livekit.com/blog/async-tools-voice-agents)
- Google Cloud — *Asynchronous function calling with Gemini Live API* (docs.cloud.google.com/
  gemini-enterprise-agent-platform/models/live-api/asynchronous-function-calling)
- Google AI for Developers — *Tool use with Live API* (ai.google.dev/gemini-api/docs/live-api/tools)
- OpenAI — *Realtime conversations* guide + *Agents SDK Realtime guide*
- Hermes skills: `hermes-api-server-integration` (API server contract), `hermes-agent`
  (spawning, kanban, cron, gateway WS), `realtime-voice-pipeline`
  (references/gemini-live-hybrid-orchestrator.md, livekit-agents-integration.md —
  verified WS bridge protocol + filler/barge-in findings), plus project
  `RESEARCH_SUMMARY.md` (filler timing config) and this repo's `src/hermes_llm.py`.