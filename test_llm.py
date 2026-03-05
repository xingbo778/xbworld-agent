#!/usr/bin/env python3
"""Standalone test for LLM provider + tool calling (no game server needed)."""

import asyncio
import json
import aiohttp

from config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
from llm_providers import create_provider

# Fake tools to test function calling
FAKE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
            },
        },
    },
]


async def test_basic_chat():
    """Test 1: Basic chat completion (no tools)."""
    print("=" * 50)
    print("Test 1: Basic chat")
    provider = create_provider(LLM_MODEL, LLM_API_KEY, LLM_BASE_URL)
    print(f"  Provider: {provider.name}, Model: {LLM_MODEL}")

    messages = [
        {"role": "system", "content": "You are a helpful assistant. Be very brief."},
        {"role": "user", "content": "What is 2+2? Answer in one word."},
    ]

    async with aiohttp.ClientSession() as session:
        data = await provider.call(session, messages, [])
        parsed = provider.parse_response(data)

    if parsed and parsed["text"]:
        print(f"  Response: {parsed['text']}")
        print("  PASSED")
    else:
        print(f"  FAILED: {parsed}")


async def test_tool_calling():
    """Test 2: Tool calling (function calling)."""
    print("=" * 50)
    print("Test 2: Tool calling")
    provider = create_provider(LLM_MODEL, LLM_API_KEY, LLM_BASE_URL)

    messages = [
        {"role": "system", "content": "You are a weather assistant. Use the get_weather tool to answer."},
        {"role": "user", "content": "What's the weather in Tokyo?"},
    ]

    async with aiohttp.ClientSession() as session:
        data = await provider.call(session, messages, FAKE_TOOLS)
        parsed = provider.parse_response(data)

    if parsed and parsed["tool_calls"]:
        for tc in parsed["tool_calls"]:
            print(f"  Tool call: {tc['name']}({tc['args']})")
        print("  PASSED")
    else:
        print(f"  FAILED (no tool calls): text={parsed.get('text', '') if parsed else 'None'}")


async def test_tool_roundtrip():
    """Test 3: Full roundtrip — LLM calls tool, gets result, responds."""
    print("=" * 50)
    print("Test 3: Tool roundtrip")
    provider = create_provider(LLM_MODEL, LLM_API_KEY, LLM_BASE_URL)

    messages = [
        {"role": "system", "content": "You are a weather assistant. Use tools to answer. Be brief."},
        {"role": "user", "content": "What's the weather in Beijing?"},
    ]

    async with aiohttp.ClientSession() as session:
        # Step 1: LLM should call the tool
        data = await provider.call(session, messages, FAKE_TOOLS)
        parsed = provider.parse_response(data)

        if not parsed or not parsed["tool_calls"]:
            print(f"  FAILED step 1 (no tool call)")
            return

        tc = parsed["tool_calls"][0]
        print(f"  Step 1 - Tool call: {tc['name']}({tc['args']})")

        # Append assistant message
        messages.append(parsed["raw_assistant"])

        # Step 2: Return fake tool result
        fake_results = [{"name": "get_weather", "result": "Sunny, 25°C, light breeze"}]
        tool_msg = provider.format_tool_results(fake_results, parsed["tool_calls"])
        if isinstance(tool_msg, list):
            messages.extend(tool_msg)
        else:
            messages.append(tool_msg)

        # Step 3: LLM should produce a final text response
        data2 = await provider.call(session, messages, FAKE_TOOLS)
        parsed2 = provider.parse_response(data2)

    if parsed2 and parsed2["text"]:
        print(f"  Step 2 - Final response: {parsed2['text']}")
        print("  PASSED")
    else:
        print(f"  FAILED step 2: {parsed2}")


async def test_agent_tools_schema():
    """Test 4: Verify agent tool definitions are valid."""
    print("=" * 50)
    print("Test 4: Agent tool schema validation")
    from agent_tools import TOOL_REGISTRY

    defs = TOOL_REGISTRY.openai_definitions()
    print(f"  Registered tools: {len(defs)}")
    for d in defs:
        fn = d["function"]
        print(f"    - {fn['name']}: {fn['description'][:60]}...")
    print("  PASSED")


async def main():
    print(f"LLM Config: model={LLM_MODEL} base_url={LLM_BASE_URL}")
    print(f"API key: {'set' if LLM_API_KEY else 'MISSING!'} (len={len(LLM_API_KEY)})")
    print()

    await test_basic_chat()
    print()
    await test_tool_calling()
    print()
    await test_tool_roundtrip()
    print()
    await test_agent_tools_schema()
    print()
    print("=" * 50)
    print("All tests done.")


if __name__ == "__main__":
    asyncio.run(main())
