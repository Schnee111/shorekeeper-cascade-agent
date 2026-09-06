# Multi-Agent / Multi-Session Orchestration Under a Voice Frontline
## Deep-research synthesis & architectural blueprint for Schnee's Gemini Live → Hermes stack

*Research date: 2026-08-15. Sources: Claude Code official docs (worktrees, subagents, agent teams, cross-session messaging, channels, dynamic workflows), Anthropic engineering "multi-agent research system", LangGraph/DeepWiki multi-agent patterns, presenc.ai 2026 framework comparison, CrewAI Flows docs, OpenAI Swarm + Agents SDK, arXiv 2507.01701 (blackboard MAS), airoads.org §9.7.3 (agent communication), Hermes skills (multi-agent-orchestration, kanban-swe-workflow, using-git-worktrees, code-delegation, context-engineering, handoff). Gemini Live specifics flagged where asserted from domain knowledge rather than fetched docs.*

---

## 0. Executive blueprint (the 30-second version)

Run **one voice-facing Hermes orchestrator session** (the "head") that never does heavy work, plus **ephemeral workers for leaf tasks** and **persistent specialist profiles only for durable, high-volume lanes**. All shared state lives in **one SQLite file as the blackboard** (tasks, claims, events, artifact index). Code concurrency is prevented by **one physical git worktree per lane + an explicit file-ownership map + lease-based claims on shared paths**. The voice frontend gets situational awareness from a **compact event feed it polls/streams**, never from full transcripts. The head narrates; workers do; the board verifies.

```
┌────────────────────────────────────────────────────────────────┐
│ VOICE PLANE (Gemini Live session — low-latency, barge-in)      │
│   • conversation loop only; never blocks on agents             │
│   • turn model: short turns; heavy work → "I'll handle it,     │
│     hang on" → async handoff to control plane                  │
└───────────────┬────────────────────────────────────────────────┘
                │ (function call: dispatch + task_id)
┌───────────────▼────────────────────────────────────────────────┐
│ CONTROL PLANE (Hermes orchestrator profile, lean head)         │
│   • ROUTE + VERIFY + CHAT only (routing table above)           │
│   • owns plan approval, dispatch, verification, integration    │
└───────┬──────────────────────┬─────────────────────────────────┘
        │ kanban/task claims   │ artifact paths + status
┌───────▼──────────┐   ┌───────▼──────────────────────────┐
│ STATE PLANE      │   │ WORKER PLANE                      │
│ SQLite blackboard│   │ subagents / specialist sessions   │
│ • tasks          │   │ • one git worktree per lane       │
│ • claims/leases  │   │ • file-ownership map (shared)     │
│ • event log      │   │ • commit or patch → never push    │
│ • artifact index │   │ • independent verification        │
└──────────────────┘   └───────────────────────────────────┘
```

**The single most important rule (confirmed by every source):** a branch is not isolation; a new session is not separation. Isolate by *filesystem path* (worktree/sandbox), communicate by *durable structured state*, and keep the human-facing layer on *summaries and events*, never raw context.

---

## 1. Multi-Agent vs Multi-Session vs Subagents — when to use what

### The three primitives

| Primitive | What it is | Cost | Best for |
|---|---|---|---|
| **Subagent / delegate** (leaf task) | A worker spawned from a parent session for one bounded task; returns a summary/artifacts; usually no chat memory | Low; inherits parent model; isolated context window | Research, single-lane implementation, one-shot fixes, parallel independent lanes (<4), anything that should not pollute the head's context |
| **Persistent specialist profile** (Hermes profile / Claude "agent teams") | Long-lived session with its own SOUL, skills, model, memory; durable across tasks | High (context accumulates, must be managed) | Durable multi-day lanes, authority over a domain, work that needs memory of prior decisions |
| **Full isolated session** (new Hermes session / Claude Code new session / worktree session) | Independent chat with its own context window, resumable, resumable by id | Medium | Parallel development in the same repo (each needs a *physical* worktree), long-running background jobs that must survive parent restart |

### Decision rules (synthesized from Hermes routing skill + Anthropic + Claude docs)

1. **Chat / 1 tool / 1-2 file clear fix → do it in the head.** Delegating everything multiplies cost ~15× with no quality gain (Hermes 2026 economics note).
2. **Heavy single-lane or parallel independent lanes → subagents/delegates.** Hermes: `delegate_task` × N with <2 true parallel lanes; Anthropic: 1 agent for fact-finding, 2-4 for comparisons, >10 only for complex research (they encode *effort scaling rules in the orchestrator prompt* — agents misjudge effort otherwise).
3. **3+ files / multi-role / durable / audit trail → kanban board + specialist profiles.** The board is the durable record; workers are interchangeable.
4. **Full file-level concurrency in one repo → one worktree per lane + ownership map** (section 3). Do NOT run two sessions on the same working tree ("a second branch in the same directory is still the same working tree" — Hermes hard rule).
5. **The orchestrator's plan must be "codified", not "held"** (Claude dynamic-workflows insight): a workflow script/kanban card holds the loop and intermediate results, so the orchestrator's context holds only the final answer. If the head must remember the state of >4 in-flight tasks, the plan belongs in the board, not the chat.

### The "lean head" architecture (validated across all sources)

Anthropic's Research system: lead agent **routes, decomposes, and synthesizes**; subagents do the search; a dedicated CitationAgent does final processing. The lead never does the subagents' work. Every framework comparison (presenc.ai) and Hermes' own skill set agree: the orchestrator's job is **route + verify + chat**, and the #1 failure is the head absorbing heavy work into its context.

> **Anti-pattern:** subagents returning entire transcript/context to the parent. Messages should be summaries + artifact pointers (Claude cross-session messaging: *"a message is text one session writes to another — never conversation history or files"*). To move whole context, resume the session by id instead.

---

## 2. Inter-Agent / Inter-Session Communication Patterns

The three canonical patterns (airoads §9.7.3 + arXiv blackboard + LangGraph DeepWiki):

| Pattern | Mechanism | Strengths | Weaknesses |
|---|---|---|---|
| **Direct message passing** | Point-to-point text (Claude `SendMessage`/`ListAgents`, LangGraph handoffs, Swarm handoff tools) | Simple, explicit, auditable, human-readable | Requires knowing the peer; delivery is not guaranteed; no replay; no history unless logged |
| **Shared state / blackboard** | A central durable store everyone reads/writes (SQLite, Redis, LangGraph shared `state`/`store`, blackboard MAS arXiv 2507.01701) | Decoupled: agents never address each other, only the board; history + replay; full joint state; selects next actor by board content; **uses fewer tokens** (agents don't re-read each other's messages) | Needs schema discipline; staleness; one writer per document or CAS needed |
| **Event bus / pub-sub** | Immutable event stream with topics; subscribers react (Claude *channels*: MCP server pushing CI/chat events into a running session; CrewAI Flows' `@listen` decorators; Kafka/Redis pub-sub) | Great for *notifications* ("done", "failed", "blocked"); decouples producers/consumers; real-time | No answers to "what is the current state?" — pairing event log + snapshot store is required |

### Known failure modes of inter-agent comms (airoads)

- Inconsistent message formats (two agents parse the same field differently)
- Message sent but nobody handles it (no consumer contract/registry)
- Same message interpreted differently by different agents (ambiguous schema)
- No timeouts or retries → deadlock/blocked lanes
- Fixes: **unify the protocol, unify state tracking, unify timeout/failure policy** — i.e., a small set of typed events with schema, an owner for every event type, mandatory TTLs.

### Industry norms today

- **LangGraph**: supervisor (central router via tools) vs swarm (peer handoffs) vs network. Ownership transitions are *explicit graph edges*, not prompt text. Shared state via checkpointing; `SendMessage`/`Command` for handoffs.
- **OpenAI Swarm** (deprecated Oct 2024 era) → **Agents SDK**: handoffs = agent A returns control to agent B; guardrails; tracing. Swarm itself is explicitly "not a full orchestration framework; narrow handoff flows only" (presenc.ai).
- **Claude Code**: cross-session messaging (`ListAgents` + `SendMessage`) = direct message passing; **channels** = event bus (two-way chat bridge into always-on sessions); agent teams = a lead supervising peers via a shared task list; dynamic workflows = orchestration codified as a script.
- **AutoGen**: conversational/group-chat debate patterns; mature in research, weaker production adoption; known "agents talk forever" problem → needs termination conditions.
- **Blackboard (arXiv 2507.01701)**: agents share all info and messages on a shared board; next actor is selected by board content; matches-or-beats SOTA static/dynamic MAS with **fewer tokens** — the strongest argument for blackboard over fan-out messaging.

### Recommendation for this stack

**Primary: SQLite blackboard + append-only event log.** One file (`~/.hermes/state/ops.sqlite` or per-project):

```
tables:
  tasks        (id, status, assignee, lane, worktree_path, dep_ids, created/updated, lease_until, attempt)
  files_owned  (path, owner_task_id, claimed_at, lease_until)      -- file-ownership map
  events       (id, seq, type, task_id, payload_json, created_at)  -- append-only log
  artifacts    (task_id, path, sha256, kind, verified_by, status)  -- evidence registry
```

- **Direct messaging** for ephemeral peer notes (equivalent of Claude `SendMessage`; in Hermes, ask the head to route the message — workers shouldn't need peers' addresses).
- **Event log** for notifications: every task lifecycle transition writes an event; the voice frontend and the head's status reflections consume it. Anyone can rebuild current state by replaying or by reading the snapshot tables.
- **File-mailbox pattern:** for *artifact* handoff (patch files, JSON outputs, reports) use the filesystem under `artifacts/<task_id>/` and record only paths+hashes in SQLite. Never stuff artifacts into messages between agents.

---

## 3. Conflict Prevention & Workspace Isolation

### 3a. Git worktrees (the industry standard — Claude Code docs, Hermes skill, restatolabs)

- `git worktree add -b lane/xyz /path/.worktrees/xyz main` — **one physical directory per concurrent lane = one worktree per session**. Claude Code now ships `--worktree` flags and subagents with `isolation: worktree` frontmatter that auto-create isolated checkouts; subagent results land in the session (no explicit merge needed), and per-worktree `.worktreeinclude` declares shared files.
- Hermes hard gate before dispatching any repo worker:
  `git branch --show-current; git status --short; git worktree list --porcelain`
  Require: one branch per lane, one physical worktree per lane, clean-or-explicitly-owned dirty state, and a file-ownership map.
- **Never** `git add -A` in a shared/uncertain workspace — stage explicit paths only.
- A repository-wide typecheck/test is **contaminated evidence** while another lane has uncommitted changes; verification becomes authoritative only after isolation.

### 3b. File-ownership map (Hermes production incident: 3 lanes racing on page.tsx → corrupt .next)

- Shared files (nav, barrel exports, lockfiles, Prisma schema, shared config, single-entry pages) have **exactly one owner per task graph**.
- Pattern: component lanes create files only; an **integrator lane** (or the head) owns the shared file and patches it serially after dependents complete. Implement with a `files_owned` table + an "integrator" task with `dep_ids=[...]`.
- On unexpected files appearing mid-run: **stop only your own worker; preserve every diff; never reset/clean/stash/overwrite/terminate** an uncertain owner's process. Reconcile ownership before any mutation.

### 3c. Leases/claims for non-git shared resources (SQLite, ports, dirs, CI slots)

- **Claim lifecycle:** `claimed (attempt N, lease_until=T+15m)` → `running (heartbeat refreshes lease)` → `done|failed|blocked` with `attempt++`.
- A claimant **must re-verify the lease is still held** before mutating shared state; stale `running` claims are reclaimed by the head/gateway using heartbeats + live PIDs (Hermes background-worker recovery).
- SQLite concurrency: **WAL mode** (concurrent readers + single writer, no read blocking), `BEGIN IMMEDIATE` for claim updates, and **compare-and-set claims** (`UPDATE tasks SET status='claimed' WHERE id=? AND status='ready'` — row-count 1 means you won the race). This is all "boring infrastructure" that most agent frameworks do *not* give you — LangGraph's checkpoint store handles its own graph state but not repo files; AutoGen/CrewAI leave file coordination to you. That's why agent frameworks' concurrency story ends at "use worktrees / lock files", and the durable control plane (Hermes kanban + SQLite) is the right owner of this contract.

### 3d. Domain-based partitioning (reduce need for locking)

- Prefer **component/domain partitioning** over lock-free chaos: frontend lane owns `src/components/`, backend lane owns `src/api/`, each with own worktree. Overlap only at the integrator.
- Database/migrations: a single migration owner per release; schema changes serialized through the integrator, never parallel.
- Process-level: one dev server per worktree port (`.next` corrupts under concurrent writes — Hermes incident). Never share a dev server or build cache across lanes.

### 3e. Commits vs pushes

- Workers **commit locally and never push**; the authenticated head (or CI) pushes and opens PRs/reviews. Prevents credential-vs-profile gaps (Hermes: worker profiles don't share gh auth) and keeps the merge review at one choke point.

---

## 4. State & Context Synchronization for the Voice Frontline

The hard problem: **Gemini Live is a low-latency voice conversation loop**; Hermes runs N durable background tasks. The voice session must stay responsive (interruption/barge-in friendly, sub-second TTFT) while the user retains full situational awareness — without blowing the voice model's context window.

### 4a. Context hierarchy (context-engineering skill — the canonical 5 levels)

1. Rules files (always loaded; project conventions, routing table, boundaries)
2. Spec/architecture docs (loaded per feature/session — not whole docs, just sections)
3. Relevant source files (per task)
4. Error/test output (per iteration, targeted snippets)
5. Conversation history (accumulates → **compact deliberately**)

Rules file is the highest-leverage artifact: *"If it's not written, it doesn't exist."* Put the routing table, file-ownership map, and "narrate don't dump" contract into the voice profile's rules file / SOUL.

### 4b. Keep the voice loop thin: events, not transcripts

- **The voice head holds only: current task list (id + status + one-line summary), active interruptions, last narration point.** It must be able to answer "what's happening?" from a `SELECT ... FROM tasks, events WHERE updated > last_sync` — i.e., **query, don't remember**.
- Worker → head communication is **summaries + artifact pointers** (Anthropic: subagents return findings, not streams). Head → voice is **narration sentences** generated from events, never raw tool dumps.
- Long-running work pattern: "I'll start that and keep you posted" → task id → periodic event-driven narration ("still running, ~60% — the integration test just passed"). Claude Code's `channels` doc makes the same point: events arrive **into the already-open session**; the running session reacts, no polling shell session needed.

### 4c. Compact & handoff discipline

- Anthropic long-horizon guidance: conversations span hundreds of turns; context windows run out → **persist plans/state to memory (durable store) before the window truncates**, resume from checkpoints rather than restart (errors compound; restarts are expensive).
- Handoff doc pattern (Hermes `handoff` skill): a compact markdown with goal, decisions, artifacts (referenced by path, not duplicated), redacted secrets, suggested skills — saved per task to a known location (`state/handoffs/<task_id>.md`). A fresh session can continue without the parent's context.
- Hermes 4-layer memory: MEMORY.md (every turn, small), USER.md (preferences), fact_store (semantic, on-demand), vault/brain (long-term). Voice head uses layer 1-2; workers get task-scoped context only.
- **Session-end save + 2h cron backup** so knowledge survives even if the voice session dies mid-stream (Hermes Step 8).

### 4d. Verification without context exhaustion

The head verifies workers by **side-effect predicates** (ports, hashes, file existence, test exit status) — short checks, recorded as evidence rows — not by re-reading worker logs. This keeps the head context small and makes claims checkable by a fresh session (Anthropic: end-state evaluation over turn-by-turn evaluation for state-mutating agents; discrete checkpoints where state changes should have occurred).

---

## 5. Industry Pattern Comparison (what to steal)

| System | Pattern | Steal this | Skip that |
|---|---|---|---|
| **Anthropic multi-agent research** (production) | LeadResearcher orchestrator → parallel subagents → CitationAgent; effort-scaling rules in prompts; memory-persisted plan; rainbow deployments; tracing of agent decision structures | Effort scaling rules; plan persisted before context truncates; **end-state evaluation**; delegation instructions specify objective + output format + tools + boundaries (vague instructions → duplicated/gapped work) | The whole thing runs in one process with synchronous subagent waits — fine for search, not for concurrent repos |
| **LangGraph** | Supervisor-via-tools vs swarm handoffs vs network; state machine + checkpointing; LangSmith tracing | Explicit ownership transitions; shared state with snapshots/checkpoints; "supervisor as router tools > a library" (their own current advice) | Framework weight for a stack that already has a control plane (Hermes kanban) — adopt the *patterns*, not the dependency |
| **CrewAI** | Role crews (sequential/hierarchical processes); **Flows** = event-driven state machine with `@listen` + shared `state` dict | Event-driven flows with explicit state dict — the mental model for our SQLite blackboard; manager-agent revision loop | Production observability/error recovery is weak (presenc.ai) — don't bet the control plane on it |
| **OpenAI Swarm → Agents SDK** | Handoffs; guardrails; **sessions** (auto conversation-history management); **sandbox agents** (container-scoped long-horizon work); **realtime/voice agents** (STT→agent→TTS pipelines; gpt-realtime with barge-in) | Voice pipeline as *pipeline* decoupled from orchestration; sessions managed as first-class; guardrail concept (input/output checks before mutation) | Swarm itself is experimental/deprecated — never build on it |
| **AutoGen** | Group chat / debate / verification patterns | Termination conditions are mandatory (agents otherwise "talk forever"); debate for verification | Production footprint small; heavy config |
| **Claude Code** | Worktrees (`--worktree`, subagent `isolation: worktree`, `.worktreeinclude`); subagents; agent teams (lead + peers, shared task list); **cross-session messaging** (`ListAgents`/`SendMessage`, text-only); **channels** (MCP event bus, two-way); **dynamic workflows** (orchestration as resumable script; dozens-hundreds of agents) | Everything under 2, 3 — it is the most complete public articulation of exactly this problem space: path-level isolation, message-only comms, event bus, codified orchestration | Their teams/sessions are Anthropic-bound; Hermes kanban + profiles are the portable equivalent |
| **Hermes (this stack, from skills)** | Lean head + specialist profiles + kanban; worktree isolation; lease/claim lifecycle; brain/vault memory; timeout-safe gated workflows | Already the control plane — extend with the SQLite blackboard + event feed + voice narration contract | Keep gateway separation (local dispatch vs VPS messaging) |

Production-adoption signal (presenc.ai Q1-2026): LangGraph ~38%, **custom orchestration ~28%** (this stack's path), CrewAI ~12%, AutoGen ~9%, Swarm ~2%. For a bespoke voice+orchestrator product, custom orchestration on a lean control plane is the mainstream choice — frameworks are reference material, not the runtime.

---

## 6. Recommended Blueprint for the Gemini Live → Hermes Stack

### Components

**A. Voice plane (Gemini Live)**
- Dedicated Live session = low-latency bidirectional audio; supports user interruption (barge-in). Voice session is *turn-based conversation only*: it calls control-plane functions (dispatch task, query status, list tasks, cancel) and receives **narration events**.
- Turn model: short turns. Heavy requests → immediate ack ("on it, ~2 min") + `dispatch` call; the result arrives later as an event-driven narration, not as a blocking turn. Gemini Live's async function calling matches this: the dispatched tool's result is delivered back into the Live session as a later event rather than blocking the turn (see the parallel voice-plane research in this directory: `gemini_async_fc.txt`, `livekit_tasks.txt`, `openai_agents_realtime_guide.txt`).
- Manual response control: keep narration on its own turn track so user speech (barge-in) preempts narration — the voice platform exposes interruption events; surrender generation immediately on them.
- Add a lightweight "status digest" function the voice can call to answer "what's running?" from SQLite (query, don't remember).

**B. Control plane (Hermes orchestrator profile — lean head)**
- Loads routing table (section 1) + file-ownership map + narration contract from its rules file/SOUL.
- Owns: plan authoring → user approval → dispatch → verification (side-effect predicates) → integration (pushes, PRs) → session-end save.
- Never: absorbs heavy implementation, re-reads worker logs, fans out with <2 lanes.

**C. Worker plane**
- Subagents (`delegate_task`) for leaf/parallel work, each bounded (one goal, targeted files, early artifacts, self-contained context block — workers have no chat memory).
- Specialist profiles (backend/frontend/qa/research) for durable/kanban lanes, via `hermes kanban` dispatch with `--board`.
- External coding engines (codex/claude code) allowed inside a lane as the *executor*, Hermes still owns the approved plan, boundaries, verification, and no-commit/no-push gates.

**D. State plane (SQLite blackboard — new, small, boring)**
- Tables from section 2. Written only by: head (task creation/integration), workers (claims, artifacts, events), gateway/lease reaper (timeouts). WAL mode; CAS claims; leases with heartbeat; `attempt` counter for retries.
- Every lifecycle transition appends an `event`; the event log is the single source for voice narration and head status.

**E. Synchronization contract (the part most stacks lack)**
1. Claim before touching shared state; re-verify lease before every mutation of a shared row.
2. Artifacts on disk, hashes in SQLite; messages are summaries, never transcripts.
3. One worktree per lane, verified via `git worktree list --porcelain` before dispatch; ownership map checked again if unexpected paths appear.
4. Voice narration generated from events with a **narration rate limit + dedupe** (don't say "moved to QA" 4 times); interruption takes priority over narration (voice session is user-first — pause narration when user speaks — Gemini Live handles this natively via barge-in; let it).

### Phased rollout (keep it small, reversible)

1. **Week 1 — control+state plane:** SQLite blackboard init script + `ops` tables; routing table in SOUL; kanban board with backend/frontend/qa profiles (already working per skills). Gate: two concurrent lanes finish without touching the same file.
2. **Week 2 — isolation hard gate:** add pre-dispatch worktree check script, file-ownership map + integrator-lane pattern, lease/claim helpers (`claim.py`, `release.py`), git commit-only policy.
3. **Week 3 — voice plane:** Gemini Live session wired to 3 functions (dispatch, status, cancel); event→narration generator; "keep you posted" flow for a 10-min bounded task as the canary.
4. **Week 4 — hardening:** timeout recovery per skill (heartbeats + live PID reclamation, administrator reconciliation vs re-run loop), session-end save cron, event-log pruning policy (keep 30 days; snapshot tables are the source of truth).

### Guardrails (non-negotiables, from Hermes production lessons)

- Shell-safety: never interpolate card bodies with backticks/`$()` into shell commands; create cards via structured API/subprocess arrays.
- Timeout ≠ failure: verify live side-effects before re-dispatch; one bounded finalizer, not re-run loops; QA block is terminal until the parent SHA changes.
- Never `git add -A` in shared workspaces; never reset/clean another session's files; stop only your own worker.
- Voice head must never claim success without verifying path/URL/exit; approval gates survive across runs (a denied command stays denied).
- Graph-inflation circuit breaker: if recovery cards outnumber delivery cards, pause and re-scope with the user.

---

## 7. Sources

- Claude Code docs (fetched 2026-08-15): worktrees, sub-agents, agent-teams, cross-session-messaging, channels, workflows (dynamic workflows) — code.claude.com/docs
- Anthropic Engineering: *How we built our multi-agent research system* (Jun 2025) — anthropic.com/engineering/multi-agent-research-system
- DeepWiki: langgraph-101 *Multi-Agent Patterns* (supervisor vs swarm, agent communication, subagent delegation) — indexed May 2026
- presenc.ai: *Multi-Agent Orchestration Frameworks 2026* (May 2026) — framework comparison + production adoption estimates
- CrewAI Docs: *Flows* (event-driven, state dict)
- OpenAI *Swarm* README + *Agents SDK* README (handoffs, guardrails, sessions, sandbox agents, realtime/voice agents, tracing)
- arXiv 2507.01701: *Exploring Advanced LLM Multi-Agent Systems Based on Blackboard Architecture* (Jul 2025)
- airoads.org §9.7.3: *Communication Between Agents* (message passing / shared state / event bus; failure modes)
- Hermes skills (local): multi-agent-orchestration (+ references/concurrent-repository-session-isolation, background-worker-status-and-recovery, bounded-finalizers, wsl-ntfs-verification), kanban-swe-workflow, using-git-worktrees, code-delegation (+ references/parallel-file-ownership, hermes-codex-hybrid), context-engineering, handoff
- Note: Gemini Live API docs timed out during this research; the Live-specific claims (barge-in, turn model) are standard platform knowledge — validate against current Live API docs before implementing the voice plane. Search backend also degraded mid-session (several queries returned empty), so a few secondary claims rest on the primary sources above.