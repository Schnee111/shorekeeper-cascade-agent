# Dual-Tier Voice & Multi-Agent Architecture for Jarvis

## 1. Overview & Vision
A hybrid voice orchestration system combining a real-time conversational frontline with an asynchronous high-reasoning execution engine.

### Core Stack
- **Tier 1 (Frontline)**: Gemini Live Multimodal API / LiveKit Voice Agent. Focus: Ultra-low latency voice, natural turn-taking, filler management, instant acoustic ACK.
- **Tier 2 (Orchestrator & Execution)**: Hermes Agent (High-reasoning models like Gemini 3.7 / Claude 3.7 / DeepSeek V3). Focus: Deep reasoning, tool execution, multi-file edits, project state management.
- **Tier 3 (Specialist Subagents)**: Parallel workers dispatched for isolated tasks (e.g. backend debug, UI development, research).

---

## 2. Architecture & Communication Flow
1. **User Voice Input**: Audio streams bi-directionally into Gemini Live via WebRTC (LiveKit).
2. **Instant ACK & Non-Blocking Dispatch**:
   - Gemini Live classifies intent.
   - For light queries: Gemini Live answers immediately.
   - For heavy tasks / coding: Gemini Live invokes non-blocking async tool calling (`NON_BLOCKING` / `behavior: NON_BLOCKING`), gives an instant verbal acknowledgement, and fires a task to Hermes.
3. **Background Execution**:
   - Hermes orchestrator dispatches subagents with isolated working environments.
   - User continues chatting / brainstorming with Gemini Live without audio pipeline blockage.
4. **Result Injection (`WHEN_IDLE`)**:
   - When the Hermes task finishes, the result is sent back to Gemini Live via `send_tool_response` with scheduling policy `WHEN_IDLE`.
   - Gemini Live waits for a natural conversational pause and delivers a crisp verbal summary.

---

## 3. Multi-Agent & Workspace Isolation
- **Git Worktree Isolation**: Each parallel coding agent operates in an isolated git worktree branch to prevent file write collisions and race conditions.
- **Domain Partitioning**: Tasks are divided by domain (Frontend / Backend / Docs / QA).
- **Automated Verification Gate**: Background code is verified via tests/linters before merging back to the main branch.

---

## 4. Context & Memory Management
- **Stateless/Sliding Voice Buffer**: Gemini Live maintains a lightweight rolling conversational window (10-15 turns) for speed and token efficiency.
- **Durable State Anchor**: Hermes maintains persistent SQLite session transcripts, MemPalace knowledge graphs, and project files.
- **On-Demand Context Lookup**: Gemini Live can issue fast read-only queries to Hermes/MemPalace when historical context is required.

## 5. Multi-Agent Framework & Production Readiness (Discussion Notes)
- **Framework Choices**:
  - **LiveKit Native Async Tools (Recommended Minimal)**: Zero extra dependency, native `get_running_tasks()`, `cancel_task()`, non-blocking turn release.
  - **LangGraph (Production Multi-Agent)**: Built-in state graphs, thread branching, SQLite checkpointing, human-in-the-loop interrupts, clean integration with Hermes WebSocket tool nodes.
  - **Temporal.io (Enterprise Workflow)**: Guaranteed execution, durable background workflow execution across restarts.
- **Session & Task Management**:
  - Tasks registered in SQLite Blackboard (`tasks`, `claims`, `events`).
  - Workers run isolated in Git Worktrees.
  - Gemini Live acts as voice frontline router; Hermes orchestrates backend execution.
