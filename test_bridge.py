"""Live bridge test (plan ui-integration.md §7.3).

Runs HermesLLM.chat() against the real Hermes Gateway and checks:
  1. markdown-bait prompt  → streamed text must be clean
  2. code-bait prompt      → streamed text must be clean
  3. tool-call-bait prompt → filler emitted before the answer

Usage: uv run python test_bridge.py
"""

import asyncio
import logging
import re
import sys
import time

sys.path.insert(0, "src")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env.local")

from livekit.agents.llm import ChatContext, ChatMessage  # noqa: E402
from hermes_llm import HermesLLM  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

DIRTY_RE = re.compile(r"[#*`|~>\[\]]|https?://")


async def run_one(llm: HermesLLM, prompt: str, expect_filler: bool) -> bool:
    ctx = ChatContext.empty()
    ctx.insert(ChatMessage(role="user", content=[prompt], id="u1"))

    print(f"\n{'='*60}\nPROMPT: {prompt}\n{'='*60}")
    chunks: list[tuple[float, str]] = []
    t0 = time.monotonic()

    stream = llm.chat(chat_ctx=ctx)
    async for chunk in stream:
        delta = chunk.delta
        if delta and delta.content:
            chunks.append((time.monotonic() - t0, delta.content))
            print(f"[{chunks[-1][0]:5.1f}s] {delta.content!r}")

    full = "".join(c for _, c in chunks)
    ok = True

    if expect_filler:
        filler = next((t for t, c in chunks if "Bentar" in c or "cek dulu" in c or "sebentar" in c.lower()), None)
        answer = next((t for t, c in chunks if c != chunks[0][1]), None)
        if filler is None:
            print("FAIL: no filler emitted"); ok = False
        elif answer is not None and filler >= answer:
            print(f"FAIL: filler at {filler:.1f}s not before answer"); ok = False
        else:
            print(f"OK: filler at {filler:.1f}s before answer")
    else:
        dirty = DIRTY_RE.findall(full)
        if dirty:
            print(f"FAIL: dirty chars in output: {set(dirty)}")
            ok = False
        else:
            print("OK: output clean (no markdown/code/url symbols)")

    return ok


async def main() -> None:
    llm = HermesLLM()
    results = []
    try:
        results.append(await run_one(llm, "buatkan tabel 3 kolom berisi nama buah dan warna", expect_filler=False))
        results.append(await run_one(llm, "tulis kode python hello world", expect_filler=False))
        results.append(await run_one(llm, "cek isi folder /tmp di server ini, sebutkan beberapa file saja", expect_filler=True))
    finally:
        await llm.aclose()

    print(f"\n{'='*60}\nRESULT: {sum(results)}/{len(results)} passed\n{'='*60}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
