"""
Admin dashboard backend for XBWorld.

Follows the same pattern as trace_server.py: a factory function that returns
a FastAPI app which can be mounted on the main app.
"""

import asyncio
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any

from admin_config import get_config, update_config, config_to_dict
import ruleset_api

# ---------------------------------------------------------------------------
# SSE helpers (same pattern as trace_server.py)
# ---------------------------------------------------------------------------

_admin_queues: list[asyncio.Queue] = []


async def _push_event(event_type: str, data: dict):
    payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    dead = []
    for q in _admin_queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _admin_queues.remove(q)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ConfigPatch(BaseModel):
    updates: dict[str, Any]


class PromptUpdate(BaseModel):
    prompt: str


class RulesetUnitPatch(BaseModel):
    name: str
    stat: str
    value: int


class RulesetBuildingPatch(BaseModel):
    name: str
    stat: str
    value: int


class GameCommand(BaseModel):
    command: str


class ServScriptUpdate(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_admin_app(agent=None, client=None, event_bus=None) -> FastAPI:
    """Create a FastAPI app for the admin dashboard.

    Parameters match trace_server.py's create_trace_app() convention.
    All parameters are optional — the app returns sensible defaults when
    agent/client are None (useful for testing without a live game).
    """
    app = FastAPI(title="XBWorld Admin API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Admin secret check (skip if not set — dev mode)
    ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")

    def check_auth(request: Request):
        if not ADMIN_SECRET:
            return
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {ADMIN_SECRET}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    # -----------------------------------------------------------------------
    # Config endpoints
    # -----------------------------------------------------------------------

    @app.get("/config")
    async def get_full_config(request: Request):
        check_auth(request)
        return config_to_dict()

    @app.patch("/config")
    async def patch_config(body: ConfigPatch, request: Request):
        check_auth(request)
        result = update_config(body.updates)
        if result["changed"]:
            await _push_event("config_changed", result["changed"])
        return result

    @app.get("/config/prompt")
    async def get_prompt(request: Request):
        check_auth(request)
        if agent and hasattr(agent, 'get_system_prompt'):
            return {"prompt": agent.get_system_prompt()}
        return {"prompt": get_config().__dict__.get("system_prompt", "")}

    @app.put("/config/prompt")
    async def put_prompt(body: PromptUpdate, request: Request):
        check_auth(request)
        update_config({"system_prompt": body.prompt})
        if agent and hasattr(agent, 'reload_config'):
            agent.reload_config()
        await _push_event("config_changed", {"system_prompt": body.prompt[:80] + "..."})
        return {"ok": True}

    # -----------------------------------------------------------------------
    # Agent status
    # -----------------------------------------------------------------------

    @app.get("/agent/status")
    async def get_agent_status(request: Request):
        check_auth(request)
        cfg = get_config()
        status = {
            "engine_type": cfg.engine_type,
            "llm_max_iterations": cfg.llm_max_iterations,
            "turn_timeout_seconds": cfg.turn_timeout_seconds,
            "agent_running": agent is not None,
        }
        if agent and hasattr(agent, 'perf'):
            status["perf"] = agent.perf.__dict__ if hasattr(agent.perf, '__dict__') else {}
        return status

    @app.get("/agent/tools")
    async def get_tools(request: Request):
        check_auth(request)
        try:
            from agent_tools import TOOL_REGISTRY
            return TOOL_REGISTRY.openai_definitions()
        except Exception as e:
            return {"error": str(e), "tools": []}

    # -----------------------------------------------------------------------
    # Ruleset endpoints
    # -----------------------------------------------------------------------

    @app.get("/ruleset/units")
    async def get_units(request: Request):
        check_auth(request)
        return ruleset_api.list_units()

    @app.get("/ruleset/buildings")
    async def get_buildings(request: Request):
        check_auth(request)
        return ruleset_api.list_buildings()

    @app.patch("/ruleset/unit")
    async def patch_unit(body: RulesetUnitPatch, request: Request):
        check_auth(request)
        result = ruleset_api.patch_unit_stat(body.name, body.stat, body.value)
        if result.get("ok"):
            await _push_event("ruleset_changed", {
                "type": "unit", "name": body.name,
                "stat": body.stat, "value": body.value,
            })
        return result

    @app.patch("/ruleset/building")
    async def patch_building(body: RulesetBuildingPatch, request: Request):
        check_auth(request)
        result = ruleset_api.patch_building_stat(body.name, body.stat, body.value)
        if result.get("ok"):
            await _push_event("ruleset_changed", {
                "type": "building", "name": body.name,
                "stat": body.stat, "value": body.value,
            })
        return result

    # -----------------------------------------------------------------------
    # Game state
    # -----------------------------------------------------------------------

    @app.get("/game/state")
    async def get_game_state(request: Request):
        check_auth(request)
        if client is None:
            return {"error": "No game client connected", "turn": 0,
                    "players": [], "cities": [], "units": []}
        try:
            from state_api import game_state_to_json
            return game_state_to_json(client)
        except Exception as e:
            gs = client.state if hasattr(client, 'state') else None
            if gs:
                return {
                    "turn": getattr(gs, 'current_turn', 0),
                    "players": list(gs.players.values()) if hasattr(gs, 'players') else [],
                    "cities": list(gs.cities.values()) if hasattr(gs, 'cities') else [],
                    "units": list(gs.units.values()) if hasattr(gs, 'units') else [],
                }
            return {"error": str(e)}

    @app.post("/game/command")
    async def send_command(body: GameCommand, request: Request):
        check_auth(request)
        if client is None:
            return {"error": "No game client connected"}
        try:
            await client.send_chat(body.command)
            return {"sent": body.command}
        except Exception as e:
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # UI tokens
    # -----------------------------------------------------------------------

    @app.get("/ui/tokens")
    async def get_ui_tokens(request: Request):
        check_auth(request)
        tokens_path = Path(__file__).parent.parent / "xbworld-web/src/ts/styles/tokens.css"
        if not tokens_path.exists():
            tokens_path = Path(__file__).parent / "../xbworld-web/src/ts/styles/tokens.css"
        if not tokens_path.exists():
            return {"error": "tokens.css not found"}

        text = tokens_path.read_text()
        tokens = {}
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r'^(--xb-[\w-]+)\s*:\s*(.+?)\s*;', line)
            if m:
                name, value = m.group(1), m.group(2)
                category = name.split('-')[2] if name.count('-') >= 2 else 'other'
                tokens[name] = {"value": value, "category": category}
        return tokens

    # -----------------------------------------------------------------------
    # Serv scripts (proxy to game server)
    # -----------------------------------------------------------------------

    SERV_SCRIPT_DIR = Path(__file__).parent.parent / "xbworld-server"

    @app.get("/serv-scripts")
    async def list_serv_scripts(request: Request):
        check_auth(request)
        scripts = []
        for p in SERV_SCRIPT_DIR.rglob("*.serv"):
            scripts.append({"name": p.name, "path": str(p.relative_to(SERV_SCRIPT_DIR))})
        return scripts

    @app.get("/serv-script/{name}")
    async def get_serv_script(name: str, request: Request):
        check_auth(request)
        if not name.endswith('.serv') or '/' in name or '..' in name:
            raise HTTPException(400, "Invalid script name")
        matches = list(SERV_SCRIPT_DIR.rglob(name))
        if not matches:
            raise HTTPException(404, "Script not found")
        return {"name": name, "content": matches[0].read_text()}

    @app.put("/serv-script/{name}")
    async def put_serv_script(name: str, body: ServScriptUpdate, request: Request):
        check_auth(request)
        if not name.endswith('.serv') or '/' in name or '..' in name:
            raise HTTPException(400, "Invalid script name")
        # Security: reject shell injection
        dangerous = ['$(', '`', '&&', '||', ';', '|', '>', '<', 'rm ', 'sudo']
        for d in dangerous:
            if d in body.content:
                raise HTTPException(400, f"Potentially dangerous content: {d}")
        matches = list(SERV_SCRIPT_DIR.rglob(name))
        if not matches:
            raise HTTPException(404, "Script not found")
        matches[0].write_text(body.content)
        return {"ok": True, "note": "Restart game server for changes to take effect"}

    # -----------------------------------------------------------------------
    # SSE stream (mirrors trace_server.py /api/events pattern)
    # -----------------------------------------------------------------------

    @app.get("/events")
    async def sse_events(request: Request):
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        _admin_queues.append(q)

        async def generate():
            try:
                yield "data: {\"type\": \"connected\"}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield msg
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                if q in _admin_queues:
                    _admin_queues.remove(q)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
