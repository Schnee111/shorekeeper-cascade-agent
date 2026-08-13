"""Which layer holds the sentence? Test blingfire streaming tokenizer alone."""
import asyncio
import sys
import time

sys.path.insert(0, "src")
from dotenv import load_dotenv

load_dotenv(".env.local")

from livekit.agents import tokenize  # noqa: E402


async def main():
    t0 = time.monotonic()

    def ts():
        return f"+{time.monotonic() - t0:6.2f}s"

    tk = tokenize.blingfire.SentenceTokenizer().stream()

    async def reader():
        async for ev in tk:
            print(f"[{ts()}] TOKENIZER EMITS: {ev.token!r}")

    task = asyncio.create_task(reader())

    print(f"[{ts()}] push A: 'Let me check on that real quick.'")
    tk.push_text("Let me check on that real quick.")
    await asyncio.sleep(6.0)

    print(f"[{ts()}] push B: 'It is currently three fifteen.'")
    tk.push_text("It is currently three fifteen.")
    await asyncio.sleep(3.0)

    print(f"[{ts()}] end_input()")
    tk.end_input()
    await asyncio.wait_for(task, timeout=10)

    print("=" * 55)
    print("If A emitted only AFTER B arrived → tokenizer holds the")
    print("trailing sentence. That alone delays every filler until")
    print("the next text (the final answer) streams.")


asyncio.run(main())
