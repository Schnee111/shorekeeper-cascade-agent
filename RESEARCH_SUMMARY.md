# Voice Agent Filler Research Summary
**Date:** 2026-08-14  
**Source:** 10 parallel subagent research (6 completed, 4 timeout)  
**Model:** opencode/deepseek-v4-flash-free via aeter

---

## 📊 Latency Benchmarks

| Method | Latency | Cost per Filler | Use Case |
|--------|---------|-----------------|----------|
| **Pre-synthesized audio** | ~10-50ms | ~$0.00005 | Opening/dwell fillers |
| **Streaming TTS** | ~150-400ms | ~$0.0002-0.001 | Contextual fillers |
| **LLM + TTS** | ~0.5-2.5s | ~$0.0005-0.0015 | Final answers only |

**Key Insight:** Pre-synthesized audio is **10-25x cheaper** and **10-50x faster** than LLM-generated fillers.

---

## 🎯 Multi-Tool Filler Strategy

### Timing Configuration
```python
OPENING_GATE = 0.3  # seconds — tool >0.3s triggers opening filler
DWELL_INTERVAL = 4.0  # seconds — silence >4s triggers dwell filler
MAX_DWELL_PER_TURN = 2  # max 2 dwell fillers per turn
```

### Rules
1. **Opening filler**: Only for first tool that takes >0.3s
2. **Between tools**: Silence (suppress LLM "Let me..." spam)
3. **Dwell filler**: Every 4-5s of silence, max 2 per turn
4. **Never enqueue filler** after reply is queued (FIFO = worse than silence)

### Anti-Patterns to Avoid
- ❌ Per-tool "Let me check..." for every tool in sequence
- ❌ LLM-generated opening filler (2-6s latency)
- ❌ Filler after final answer already queued
- ❌ Hardcoded filler for every turn (even without tools)

---

## 🔧 LiveKit Best Practices

### Official `session.say()` Patterns
```python
# Opening filler (instant, pre-synthesized)
await session.say(
    "Let me check that for you.",
    allow_interruptions=True,  # Allow user to skip
)

# Dwell filler (long operations)
await session.say("Still working on it...", allow_interruptions=True)
```

### Common Pitfalls
1. **Filler scheduler fires over user speech** — must be idle-gated
2. **Per-tool "Let me..." spam** — suppress LLM text during multi-tool
3. **Double filler** — LLM opener + engine race condition
4. **`generate_reply` from inside `llm_node`** → infinite loop (#3915)

### LiveKit Official Recommendation
> "For fixed phrases like these, you can cache TTS and use pre-synthesized audio to avoid redundant TTS calls and reduce latency"

---

## 🗣️ Linguistics Research

### Optimal Filler Frequency
- **Humans**: ~2-3 fillers per 100 words in spontaneous dialogue
- **AI Recommended**: **1-3 fillers per 100 words** (~1 per 30-50 words)
- **Key Finding**: Humans use **fewer fillers when talking to machines** (0.78-1.87/100 words)

### Filler Types
| Type | Duration | Function |
|------|----------|----------|
| "uh" | Short delay (~200ms) | Turn-holding, planning |
| "um" | Longer delay (~500ms) | Longer planning, hesitation |
| "hmm" | Variable | Thinking, processing |

### Cultural Notes
- English: "um", "uh", "hmm"
- Indonesian: "ehm", "ah", "hmm"
- Japanese: "eto", "ano"

---

## 🏭 Production Case Studies

### Latency Requirements
- **Vapi**: >1200ms turn budget breaks conversation flow
- **Optimal**: **600-900ms** end-to-end (user stop speaking → agent start speaking)
- **Human baseline**: ~200ms turn gap

### Filler Impact on Quality
- **Filled-pause insertion** improves TTS naturalness: **+0.24/+0.26 MOS** (Mean Opinion Score)
- Source: SSW12, arXiv:2210.09815

### Real-World Results
- **PG&E** (utilities): +22% CSAT, 67% containment, 35k labor hours saved
- **Healthcare**: Reduced perceived wait time by 40% with appropriate fillers

---

## 🔄 Interruption Handling

### OpenAI Realtime API
- Server auto-cancels responses on VAD speech detection
- WebSocket clients must:
  1. Stop playback on `speech_started`
  2. Send `conversation.item.truncate` with `item_id` + `audio_end_ms`

### LiveKit
- `allow_interruptions=True` for fillers (user can skip)
- Barge-in during `session.say()` works correctly
- Semantic VAD (`eagerness: high`) fixes user-side filler delays

### Vapi/Retell/Bland
- Similar patterns: VAD-triggered cancellation
- Configurable interruption sensitivity
- Post-interruption context preservation

---

## 🎨 Filler Content Guidelines

### Opening Fillers (Tool Start)
- "Let me check that for you."
- "One moment, looking into it."
- "Hmm, let me see..."
- "Checking on that now."

### Dwell Fillers (Progress Updates)
- "Still working on it..."
- "Almost there..."
- "Bear with me..."
- "Just a moment longer..."

### Content Rules
1. **Match brand voice** — casual vs professional
2. **Vary phrasing** — 8-10 variants to avoid repetition
3. **Keep it short** — 1-3 seconds max
4. **Avoid clichés** — "Please hold" is overused

---

## 🏗️ Implementation Architecture

### Recommended Approach: Hybrid

| Component | Method | Reason |
|-----------|--------|--------|
| **Opening filler** | Pre-synthesized audio | Instant (~10ms), consistent |
| **Dwell filler** | Pre-synthesized audio | Predictable, no LLM cost |
| **Final answer** | LLM + TTS | Contextual, accurate |
| **Multi-tool suppression** | Silent execution | Avoid "Let me..." spam |

### Flow Diagram
```
User speech ends
    ↓
[0ms] Check: tool required?
    ↓ Yes
[0ms] Play pre-synthesized opening filler (instant)
    ↓
[parallel] Submit to LLM + execute tool
    ↓
[4s] Tool still running? → Play dwell filler
    ↓
[8s] Still running? → Play second dwell filler (max 2)
    ↓
Tool complete → LLM generates final answer → TTS
```

---

## 📁 Research Files

Subagent research reports saved to:
- `/home/ubuntu/voice-api-filler-research.md` — OpenAI/Gemini/Nova Sonic APIs
- `/home/ubuntu/ai-filler-guidelines.md` — Linguistics & UX research
- `/home/ubuntu/voice_agent_research_summary.md` — Production case studies
- `/home/ubuntu/filler-delivery-comparison.md` — Delivery method comparison
- `/home/ubuntu/interruption-handling-research.md` — Interruption patterns
- `/home/ubuntu/voice-filler-strategies-research.md` — Multi-tool strategies

---

## 🔗 Key Sources

1. **LiveKit Docs** — session.say() patterns, tool loop design
2. **Vapi Blog** — Latency optimization, production requirements
3. **Clark & Fox Tree (2002)** — "uh" vs "um" semantics (Cognition)
4. **Bortfeld et al. (2001)** — Disfluency rates in speech
5. **arXiv:2210.09815** — Filled-pause insertion improves TTS naturalness
6. **Stivers (2009)** — Human turn-taking ~200ms baseline

---

## ⚠️ Research Gaps

1. **No rigorous public A/B tests** of filler strategies exist (proprietary)
2. **Cultural differences** in filler perception under-researched
3. **Long-term user adaptation** to AI fillers unknown

---

---

## 🔧 Current Implementation State (Jarvis Agent)

### File: `src/hermes_llm.py`

#### Smart Filler Engine v6 (Approach D Hybrid)

**Current Behavior:**
- LLM generates opening filler as first sentence (e.g., "[warm] Let me check...")
- Opening filler sent to TTS immediately at TTFT (Time To First Token)
- Dwell fillers generated by `_FillerEngine` class for long operations
- Multi-tool suppression: LLM text suppressed during subsequent tool calls

**Key Classes & Methods:**

```python
class _FillerEngine:
    """Manages filler timing and suppression."""
    
    # State tracking
    has_active_tools: bool          # True when tools are running
    _active_tool_count: int         # Number of currently running tools
    _first_tool_seen: bool          # True after first tool starts
    _dwell_timer: asyncio.Task      # Timer for dwell filler
    _last_activity: float           # Timestamp of last activity
    
    # Configuration
    OPENING_GATE = 0.3              # seconds — tool >0.3s triggers opening
    DWELL_INTERVAL = 4.0            # seconds — silence >4s triggers dwell
    MAX_DWELL_PER_TURN = 2          # max 2 dwell fillers per turn
    
    # Methods
    def record_tool_start(self)     # Called on tool.generating event
    def record_tool_end(self)       # Called on tool.complete event
    def reset_dwell(self)           # Reset dwell timer on new activity
    def should_suppress(self)       # True if LLM text should be suppressed
```

**Filler Pools (Hardcoded):**

```python
_OPENING_FILLERS = [
    "Hmm, let me see...",
    "One sec, looking into it...",
    "Bear with me...",
    "Let me check that for you.",
    "Looking into it now...",
    "Just a moment...",
    "Checking on that...",
    "Give me a second...",
]

_DWELL_FILLERS = [
    "Still working on it...",
    "Almost there...",
    "Just a moment longer...",
    "Taking a bit longer than expected...",
    "Still looking into it...",
    "Bear with me a bit more...",
]
```

**Sentence Splitting (Decimal-Aware):**

```python
_BOUNDARY_CHARS = ".!?\n"  # Period, exclamation, question, newline
# Note: Comma (,) and semicolon (;) are NOT sentence boundaries

# Decimal-aware splitting
if char == "." and prev_char.isdigit() and next_char.isdigit():
    # Don't split — this is a decimal number (e.g., "3.7", "0.54")
    continue
```

**Multi-Tool Suppression Logic:**

```python
# In _run_turn():
if filler.has_active_tools and t_first_sentence is not None:
    # Tools are running and we already sent opening
    if filler.should_suppress(delta.text):
        logger.info("Suppressing: %r", delta.text[:80])
        continue  # Skip sending to TTS
    else:
        logger.info("NOT suppressing: %r", delta.text[:80])
```

**Known Issues:**
1. **Race condition**: `has_active_tools` may not be set when LLM text arrives before `tool_started` event
2. **LLM text gating**: Opening filler sometimes combined with final answer
3. **Dwell repeat**: Dwell filler may repeat if tools complete between dwells

### File: `src/agent.py`

**Agent Server Configuration:**

```python
AgentServer(
    # Process management
    multiprocessing_context="spawn",  # Avoid forkserver orphans
    num_idle_processes=0,             # No idle processes (RAM leak fix)
    job_memory_limit_mb=600,          # 600MB per job
    _kill_own_tree(),                 # Clean up child processes
    
    # Voice settings
    voice=voice,                      # From UI selection
    model=model,                      # From UI selection
    
    # Turn detection
    min_silence_duration=0.6,         # VAD: 600ms silence = end of turn
    min_delay=1.2,                    # Turn detector: 1.2s delay
)
```

**Current Filler Flow:**

```
User: "Jam berapa sekarang"
    ↓
[0ms] VAD detects end of speech
    ↓
[~16ms] Submit to Hermes Gateway
    ↓
[~2.5s] LLM TTFT — first sentence: "[calm] Let me check..."
    ↓
[~2.6s] TTS render opening filler
    ↓
[~2.7s] Audio playback starts
    ↓
[parallel] Tool execution (terminal: date)
    ↓
[~0.14s] Tool complete
    ↓
[~1.5s] LLM final answer: "It is currently 11:03 PM..."
    ↓
[~2.0s] TTS render final answer
    ↓
[~2.1s] Audio playback complete
```

**Total Latency:** ~4.8s (user stop → agent complete)

### File: `client/src/lib/stores/conversation.svelte.ts`

**Turn Progress Tracking:**

```typescript
class ConversationStore {
    // State
    liveAgentBubbles = $state<LiveBubble[]>([]);
    awaitingReply = $state(false);
    liveAgentStartTime = $state('');
    
    // Getters
    get turnInProgress(): boolean {
        return this.awaitingReply 
            || this.liveAgentBubbles.length > 0 
            || this.hasLiveAgentSegment() 
            || tools.active;
    }
    
    get turnElapsedSeconds(): number {
        if (!this.liveAgentStartTime) return 0;
        const start = new Date(`2000-01-01 ${this.liveAgentStartTime}`).getTime();
        const now = new Date(`2000-01-01 ${getTime()}`).getTime();
        return Math.max(0, Math.floor((now - start) / 1000));
    }
}
```

**UI Indicator (Minimalist):**

```svelte
{#if conversation.turnInProgress}
    <div class="flex items-center gap-1.5 text-zinc-500">
        <div class="flex gap-0.5">
            <div class="w-1 h-1 rounded-full bg-current animate-pulse"></div>
            <div class="w-1 h-1 rounded-full bg-current animate-pulse" style="animation-delay: 300ms"></div>
            <div class="w-1 h-1 rounded-full bg-current animate-pulse" style="animation-delay: 600ms"></div>
        </div>
        <span class="text-[10px] font-mono tracking-wide opacity-70">
            {tools.active ? 'working' : 'processing'}
            {#if conversation.turnElapsedSeconds > 2}
                <span class="opacity-50">· {conversation.turnElapsedSeconds}s</span>
            {/if}
        </span>
    </div>
{/if}
```

---

## 🐛 Known Issues & Fixes

### Issue 1: Forkserver Orphans (RAM Leak)
**Status:** ✅ Fixed  
**Fix:** `multiprocessing_context="spawn"` + `num_idle_processes=0` + `_kill_own_tree()`  
**Commit:** `ba40ecd`

### Issue 2: Scaffold Filter Not Gating TTS
**Status:** ✅ Fixed  
**Fix:** Moved `contains_scaffold()` filter before TTS send  
**Commit:** `f437047`

### Issue 3: Multi-Tool "Let me..." Spam
**Status:** ⚠️ Partially Fixed  
**Fix:** `has_active_tools` flag + suppression logic  
**Remaining:** Race condition when LLM text arrives before `tool_started`

### Issue 4: Decimal Number Sentence Splitting
**Status:** ✅ Fixed  
**Fix:** `prev_char.isdigit() and next_char.isdigit()` check  
**Commit:** `8084320`

### Issue 5: Paragraph Breaks in UI
**Status:** ✅ Fixed  
**Fix:** `_BOUNDARY_CHARS` from `".!?,;\n"` to `".!?\n"`  
**Commit:** `8084320`

### Issue 6: LLM Filler Latency
**Status:** ❌ Open  
**Problem:** LLM-generated opening filler has 2-6s latency  
**Solution:** Implement pre-synthesized audio (see research above)

---

## 📝 Git History

| Commit | Description |
|--------|-------------|
| `ba40ecd` | fix(agent): stop forkserver orphans on voice/model switch (RAM leak) |
| `f437047` | fix(hermes_llm): scaffold filter actually gates TTS + timing log |
| `8084320` | feat(filler): Smart Filler Engine v6 with decimal-aware sentence splitting |
| `HEAD` | feat(ui): minimalist turn progress indicator |

---

**Next Steps:** Implement pre-synthesized audio fillers in `hermes_llm.py` and `agent.py` based on this research.
