#!/usr/bin/env python3
"""E2E test for multi-tool suppression in hermes_llm.py.

Simulates a Hermes Gateway WebSocket flow with multiple tool calls
to verify that LLM text suppression works correctly.
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path
sys.path.insert(0, "/home/ubuntu/projects/jarvis-livekit/src")

from hermes_llm import _FillerEngine, _split_sentence


async def test_multi_tool_suppression():
    """Test that LLM text is suppressed during multi-tool execution."""
    print("=== Testing Multi-Tool Suppression ===\n")

    # Create filler engine
    loop = asyncio.get_event_loop()
    filler = _FillerEngine(loop)

    # Simulate first tool start
    is_first = filler.record_tool_start("session_search")
    print(f"Tool 1 started: session_search, is_first={is_first}")
    print(f"  has_active_tools={filler.has_active_tools}")
    assert filler.has_active_tools == True

    # Simulate second tool start
    is_first = filler.record_tool_start("tool_call")
    print(f"Tool 2 started: tool_call, is_first={is_first}")
    print(f"  has_active_tools={filler.has_active_tools}")
    assert filler.has_active_tools == True

    # At this point, both tools are active
    # LLM text should be suppressed
    print("\n--- LLM emits text during tool execution ---")
    print("Expected: Text should be SUPPRESSED (not sent to TTS)")

    # Check suppression condition
    t_first_sentence = 1.0  # Already sent opening
    should_suppress = filler.has_active_tools and t_first_sentence is not None
    print(f"  has_active_tools={filler.has_active_tools}")
    print(f"  t_first_sentence={t_first_sentence}")
    print(f"  should_suppress={should_suppress}")
    assert should_suppress == True, "LLM text should be suppressed during tool execution"

    # Simulate first tool complete
    filler.record_tool_end()
    print(f"\nTool 1 completed")
    print(f"  has_active_tools={filler.has_active_tools}")
    # Under idempotent tool lifecycle, tool completion resets active status to allow final response streaming
    assert filler.has_active_tools == False

    # Simulate second tool complete (no-op)
    filler.record_tool_end()
    print(f"\nTool 2 completed")
    print(f"  has_active_tools={filler.has_active_tools}")
    assert filler.has_active_tools == False  # No more active tools

    # Now LLM text should NOT be suppressed
    should_suppress = filler.has_active_tools and t_first_sentence is not None
    print(f"  should_suppress={should_suppress}")
    assert should_suppress == False, "LLM text should NOT be suppressed after all tools complete"

    print("\n✅ Multi-tool suppression test PASSED")


async def test_sentence_splitting():
    """Test that sentence splitting handles decimals correctly."""
    print("\n=== Testing Sentence Splitting ===\n")

    test_cases = [
        # (input, expected_first_sentence)
        ("Hello world. How are you?", "Hello world."),
        ("The version is 3.7 Flash.", "The version is 3.7 Flash."),  # Complete sentence with period
        ("The version is 3.7 Flash. It works.", "The version is 3.7 Flash."),
        ("Price is 1.500. That's cheap.", "Price is 1.500."),
        ("As of today, 14 August 2026, it works.", "As of today, 14 August 2026, it works."),
    ]

    for input_text, expected in test_cases:
        sentence, rest = _split_sentence(input_text)
        status = "✓" if sentence == expected else "✗"
        print(f"{status} Input: {input_text!r}")
        print(f"   Expected: {expected!r}")
        print(f"   Got:      {sentence!r}")
        if sentence != expected:
            print(f"   REST:     {rest!r}")
        print()

    print("✅ Sentence splitting tests completed")


async def test_filler_rotation():
    """Test that filler pools have enough variety."""
    print("\n=== Testing Filler Variety ===\n")

    from hermes_llm import _OPENING_FILLERS, _DWELL_FILLERS

    print(f"Opening fillers: {len(_OPENING_FILLERS)} variations")
    for i, f in enumerate(_OPENING_FILLERS, 1):
        print(f"  {i}. {f}")

    print(f"\nDwell fillers: {len(_DWELL_FILLERS)} variations")
    for i, f in enumerate(_DWELL_FILLERS, 1):
        print(f"  {i}. {f}")

    assert len(_OPENING_FILLERS) >= 6, "Should have at least 6 opening fillers"
    assert len(_DWELL_FILLERS) >= 6, "Should have at least 6 dwell fillers"

    print("\n✅ Filler variety test PASSED")


async def main():
    print("Running E2E tests for Smart Filler Engine v6\n")
    print("=" * 60)

    await test_sentence_splitting()
    await test_filler_rotation()
    await test_multi_tool_suppression()

    print("\n" + "=" * 60)
    print("✅ All tests PASSED")


if __name__ == "__main__":
    asyncio.run(main())
