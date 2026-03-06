---
name: xbworld
description: Play XBWorld/Freeciv civilization game via AI agents
triggers:
  - /xbworld
  - play freeciv
  - play civilization
  - start xbworld game
---

# XBWorld Game Skill

You are a game master for **XBWorld** — an AI-powered Freeciv (4X strategy) game. You help users start games, control AI agents, observe game state, and play strategically.

## Project Location

The xbworld-agent project is located at the current working directory. All commands should be run from here.

## Quick Reference

### Environment Setup

Before starting, ensure `.env` is configured:

```bash
# Required
LLM_API_KEY=your-api-key-here

# Optional (defaults shown)
LLM_MODEL=google/gemini-3-flash-preview
LLM_BASE_URL=https://openrouter.ai/api/v1
XBWORLD_HOST=localhost
XBWORLD_PORT=8080
XBWORLD_TLS=0                 # Set to 1 for HTTPS/WSS
TURN_TIMEOUT=30               # LLM turn timeout (seconds)
GAME_TURN_TIMEOUT=30          # Server-side turn timeout
```

### Starting a Game

**Single agent (simplest):**
```bash
python main.py
```

**Single agent with options:**
```bash
python main.py --username MyBot --trace-port 8077 --verbose
python main.py --join 6001       # Join existing game
python main.py --no-autostart    # Don't auto-configure, manual /start
```

**Multi-agent (2-8 players):**
```bash
python multi_main.py --agents 3
python multi_main.py --agents alpha:aggressive,beta:defensive,gamma:economic
python multi_main.py --agents 3 --aifill 2  # 3 LLM agents + 2 AI
python multi_main.py --config agents.json
python multi_main.py --api                 # Start HTTP API mode
python multi_main.py --api --api-port 9000 # Custom API port
python multi_main.py --standalone          # Spawn freeciv-server locally (no Tomcat needed)
```

**agents.json example:**
```json
[
  {"name": "alpha", "strategy": "aggressive military expansion"},
  {"name": "beta",  "strategy": "defensive turtle with science focus"},
  {"name": "gamma", "strategy": "economic and diplomatic", "llm_model": "gpt-4o-mini"}
]
```

### Monitoring

- **Trace dashboard**: `http://localhost:8077` (single agent)
- **Observer URL**: `http://localhost:8080/webclient/?action=observe&civserverport=PORT`

---

## Multi-Agent HTTP API

When running `python multi_main.py --api`, the following endpoints are available:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/game/create` | Create new game with agents |
| GET | `/game/status` | Status of all agents |
| DELETE | `/game` | Shut down game |
| GET | `/game/state` | Full game state for all agents |
| GET | `/game/tools` | List available tools with schemas |
| GET | `/game/events` | SSE event stream |
| POST | `/game/join` | External agent joins game |
| GET | `/agents/{name}/state` | Agent's detailed state |
| POST | `/agents/{name}/command` | Send natural language command |
| GET | `/agents/{name}/log` | Agent's action log |
| POST | `/agents/{name}/actions` | Execute tools directly |
| POST | `/agents/{name}/end_turn` | End agent's turn |
| GET | `/agents/{name}/state/json` | Structured game state |
| GET | `/agents/{name}/state/delta` | State changes since last query |

### API Examples

```bash
# Create a 3-agent game
curl -X POST http://localhost:8080/game/create \
  -H 'Content-Type: application/json' \
  -d '{"agents": [{"name":"alpha","strategy":"aggressive"},{"name":"beta"},{"name":"gamma"}], "aifill": 2}'

# Check status
curl http://localhost:8080/game/status

# Send command to agent
curl -X POST http://localhost:8080/agents/alpha/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "build Granary in all cities"}'

# Execute tools directly (bypass LLM)
curl -X POST http://localhost:8080/agents/alpha/actions \
  -H 'Content-Type: application/json' \
  -d '{"actions": [{"name":"set_research_target","args":{"tech_name":"Alphabet"}}, {"name":"end_turn","args":{}}]}'

# Stream game events
curl -N http://localhost:8080/game/events
```

---

## Available Game Tools

These are the tools the AI agent can call each turn:

### Query Tools (read-only)
| Tool | Description |
|------|-------------|
| `get_game_overview` | Turn, gold, cities, units, research summary |
| `get_my_cities` | List cities with population and production |
| `get_my_units` | List units with type, location, HP, MP |
| `get_research_status` | Current research progress and known techs |
| `get_visible_enemies` | Enemy units visible on the map |
| `get_recent_messages` | Chat/game messages |
| `get_tile_info` | Terrain info for a tile |

### Action Tools
| Tool | Description |
|------|-------------|
| `move_unit` | Move unit one tile (N/NE/E/SE/S/SW/W/NW) |
| `move_units` | Batch move multiple units |
| `found_city` | Settler founds a city on current tile |
| `set_research_target` | Set tech to research |
| `change_city_production` | Change what a city builds |
| `set_productions` | Batch set production for multiple cities |
| `set_tax_rates` | Set tax/luxury/science (must sum to 100) |
| `buy_city_production` | Buy production instantly with gold |
| `fortify_unit` | Fortify for defense bonus |
| `auto_explore_unit` | Set unit to auto-explore |
| `disband_unit` | Permanently remove a unit |
| `sentry_unit` | Put unit on sentry |
| `send_command` | Send raw server command |
| `end_turn` | End the current turn |

---

## Strategy Guide

When helping users play or configuring agents, follow these priorities:

### Early Game (Turns 1-20)
1. **Research**: Alphabet → Code of Laws → Republic
2. **Production**: 2 Warriors (explore) → Granary → Settler (when size ≥ 3)
3. **Exploration**: Set Warriors to `auto_explore_unit`
4. **Tax rates**: Tax 10%, Luxury 30%, Science 60%
5. **City founding**: Move Settlers 4-5+ tiles from existing cities

### Mid Game (Turns 20-60)
1. **Research**: Republic → Construction → Currency
2. **Production**: Temple, Marketplace, Phalanx for defense
3. **Expansion**: Aim for 3-5 cities
4. **Government**: Switch to Republic when available

### Key Rules
- ALWAYS keep a research target active — never leave it on "None"
- Don't move a Settler and found a city in the same turn (0 MP = fail)
- Don't build only Warriors — diversify with buildings and Settlers
- Use batch tools (`move_units`, `set_productions`) for efficiency
- Issue all actions, then call `end_turn`

---

## Architecture

```
User / Claude Code
       │
       ├── main.py ──────── Single-agent entry point
       │                       └── GameClient (WebSocket)
       │                       └── XBWorldAgent (LLM loop)
       │                       └── Trace Dashboard (:8077)
       │
       ├── multi_main.py ── Multi-agent entry point
       │                       └── GameOrchestrator
       │                       └── HTTP API (FastAPI)
       │                       └── SSE Event Stream
       │
       ├── game_client.py ─ Freeciv WebSocket protocol
       ├── agent.py ─────── LLM-powered autonomous agent
       ├── agent_tools.py ─ Game tools (move, build, research)
       ├── llm_providers.py Provider abstraction (Gemini/OpenAI)
       ├── decision_engine.py Strategy patterns (LLM/Rule/External)
       ├── state_api.py ──── State serialization & deltas
       └── config.py ─────── Environment config
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Failed to connect" | Check XBWORLD_HOST/PORT, ensure xbworld-server is running |
| "LLM call failed" | Check LLM_API_KEY, LLM_BASE_URL, model name |
| Agent not acting | Check `http://localhost:8077` trace dashboard |
| "No research" warning | Agent should call `set_research_target` — may be an LLM issue |
| Turn timeout | Increase TURN_TIMEOUT env var (default 30s) |

## When the User Wants to Play

1. **Check prerequisites**: Verify `.env` exists with `LLM_API_KEY`, check if xbworld-server is reachable
2. **Start the game**: Run `python main.py` or `python multi_main.py` based on preference
3. **Monitor**: Open trace dashboard and observe game progress
4. **Interact**: Send natural language commands via stdin or HTTP API
5. **Adjust**: Help tune strategy, change research, adjust tax rates as needed
