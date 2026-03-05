"""
Tracing dashboard for XBWorld Agent.

Embeds a FastAPI server with SSE event streaming and an inline HTML dashboard
that shows real-time agent activity: LLM calls, tool executions, game state,
and per-turn performance metrics.
"""

import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from event_bus import EventBus
from state_api import game_state_to_json

# Load dashboard HTML from file (falls back to minimal message if missing)
_TRACE_HTML_PATH = Path(__file__).parent / "static" / "trace.html"
_TRACE_HTML = _TRACE_HTML_PATH.read_text() if _TRACE_HTML_PATH.exists() else "<h1>trace.html not found</h1>"


def create_trace_app(agent, client, event_bus: EventBus) -> FastAPI:
    """Create a FastAPI app for the tracing dashboard."""

    app = FastAPI(title="XBWorld Agent Trace")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _TRACE_HTML

    @app.get("/api/status")
    async def api_status():
        return agent.get_status()

    @app.get("/api/state")
    async def api_state():
        return game_state_to_json(client)

    @app.get("/api/log")
    async def api_log(limit: int = 100):
        return {"log": agent.action_log[-limit:]}

    @app.get("/api/perf")
    async def api_perf():
        return {"turns": agent.perf.turn_history}

    @app.get("/api/conversation")
    async def api_conversation(limit: int = 30):
        return {"messages": agent.get_conversation_safe(limit)}

    @app.get("/api/game")
    async def api_game(limit: int = 100):
        s = client.state
        messages = s.messages[-limit:] if s.messages else []
        players = []
        for pid, p in s.players.items():
            player_cities = [c for c in s.cities.values() if c.get("owner") == pid]
            player_units = [u for u in s.units.values() if u.get("owner") == pid]
            players.append({
                "id": pid,
                "name": p.get("name", f"player_{pid}"),
                "is_alive": p.get("is_alive", True),
                "is_ai": pid != s.my_player_id,
                "gold": p.get("gold"),
                "cities": len(player_cities),
                "units": len(player_units),
            })
        players.sort(key=lambda x: (x["cities"], x["units"]), reverse=True)
        # Extract year from last "Year:" chat message
        year = ""
        for m in reversed(messages):
            t = m.get("text", "") if isinstance(m, dict) else str(m)
            if "Year:" in t:
                match = re.search(r"Year:\s*(.+?)(?:<|$)", t)
                if match:
                    year = match.group(1).strip()
                break
        return {"turn": s.turn, "year": year, "messages": messages, "players": players}

    @app.get("/api/events")
    async def api_events():
        queue = event_bus.subscribe()

        async def event_generator():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                event_bus.unsubscribe(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app

