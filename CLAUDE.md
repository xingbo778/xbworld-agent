# XBWorld Agent

AI-powered autonomous Freeciv (4X strategy game) player. LLM agents connect via WebSocket to xbworld-server and play the game using function-calling.

## Tech Stack

- **Python 3.11+**, async (asyncio, aiohttp, websockets)
- **FastAPI + uvicorn** for trace dashboard and multi-agent HTTP API
- **LLM providers**: Gemini (native), OpenAI-compatible (Claude, GPT, etc. via OpenRouter)

## Project Structure

```
agent.py          — Main XBWorldAgent class (LLM game loop)
game_client.py    — WebSocket client for Freeciv protocol (GameClient, GameState)
agent_tools.py    — Tool registry + 20+ game tools (move, build, research, etc.)
llm_providers.py  — Pluggable LLM provider abstraction (Gemini/OpenAI)
decision_engine.py — Strategy patterns (LLM/RuleBased/External)
state_api.py      — Game state JSON serialization & turn deltas
config.py         — Environment variable configuration
event_bus.py      — Shared pub/sub for SSE events
trace_server.py   — FastAPI tracing dashboard
main.py           — Single-agent entry point
multi_main.py     — Multi-agent orchestrator + HTTP API
static/trace.html — Dashboard HTML (loaded by trace_server.py)
skill.md          — OpenClaw skill for playing via Claude Code
```

## How to Run

```bash
# Single agent
python main.py

# Multi-agent
python multi_main.py --agents 3

# HTTP API mode
python multi_main.py --api
```

Requires `.env` with at least `LLM_API_KEY`. See `config.py` for all variables.

## Key Conventions

- All game tools are registered via `@tool()` decorator in `agent_tools.py`
- GameState lookup helpers are on the `GameState` dataclass: `unit_type_name()`, `tech_name()`, `building_name()`, `terrain_name()`
- EventBus is shared via `event_bus.py` (do not duplicate)
- Dashboard HTML lives in `static/trace.html` (not inline in Python)
- Imports must be at file top level (no lazy imports inside functions)
- `_trim_conversation()` must validate tool_call/response pairing for OpenAI compatibility
- LLM API calls include exponential backoff retry (429/5xx)
- `my_units()`/`my_cities()` on GameState are cached with turn-based + mutation invalidation

## Testing

```bash
python test_connection.py   # Basic connectivity
python test_llm.py          # LLM provider test
python test_10turns.py      # 10-turn smoke test
python test_100turns.py     # Long-running stability test
```

Tests require a running xbworld-server.
