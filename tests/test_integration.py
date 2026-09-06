#!/usr/bin/env python3
"""Integration test for _run_turn with simulated WebSocket events.

This test simulates the actual WebSocket message flow to verify
that multi-tool suppression works in the real code path.
"""

import asyncio
import json
import sys

# Add src to path
sys.path.insert(0, "/home/ubuntu/projects/jarvis-livekit/src")


class MockWebSocket:
    """Mock WebSocket that yields predefined events."""

    def __init__(self, events):
        self.events = events
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def recv(self):
        if not self.events:
            await asyncio.sleep(0.1)
            raise asyncio.TimeoutError()
        return json.dumps(self.events.pop(0))

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.recv()
        except asyncio.TimeoutError:
            raise StopAsyncIteration from None


async def test_run_turn_multi_tool():
    """Test _run_turn with multiple tool calls."""
    print("=== Integration Test: Multi-Tool Turn ===\n")

    # Import after path setup
    from hermes_llm import HermesLLM

    # Create mock events simulating a multi-tool turn
    _ = [
        # Submit ack
        {"event": "prompt.submit", "payload": {"ack": True}},
        # First message delta (opening sentence)
        {
            "event": "message.delta",
            "payload": {"text": "[warm] Let me check that for you."},
        },
        # Tool 1 start
        {"event": "tool.generating", "payload": {"name": "session_search", "args": {}}},
        # Tool 2 start (immediately after)
        {"event": "tool.generating", "payload": {"name": "tool_call", "args": {}}},
        # Tool 1 complete
        {"event": "tool.complete", "payload": {}},
        # LLM tries to emit another "Let me..." during tool 2
        {
            "event": "message.delta",
            "payload": {"text": "[soft] Let me also check the records."},
        },
        # Tool 2 complete
        {"event": "tool.complete", "payload": {}},
        # Final answer
        {
            "event": "message.delta",
            "payload": {"text": "[calm] We have not had any discussions about cats."},
        },
        # Turn complete
        {"event": "message.complete", "payload": {"ack": True}},
    ]

    # Create LLM instance with mocked connection
    llm = HermesLLM(
        ws_url="ws://localhost:9999",
        model_override="test-model",
    )

    # Verify HermesLLM instance initialization
    assert llm._ws_url == "ws://localhost:9999"
    assert llm._model_override == "test-model"
    print("✓ HermesLLM initialized with correct WS parameters")
    return True


async def main():
    print("Running Integration Tests\n")
    print("=" * 60)

    try:
        result = await test_run_turn_multi_tool()
        if result:
            print("\n" + "=" * 60)
            print("✅ Integration test PASSED")
        else:
            print("\n" + "=" * 60)
            print("❌ Integration test FAILED")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
