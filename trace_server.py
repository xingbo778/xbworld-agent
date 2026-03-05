"""
Tracing dashboard for XBWorld Agent.

Embeds a FastAPI server with SSE event streaming and an inline HTML dashboard
that shows real-time agent activity: LLM calls, tool executions, game state,
and per-turn performance metrics.
"""

import asyncio
import json
import re

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from state_api import game_state_to_json


class EventBus:
    """Simple pub/sub for SSE game events."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def publish(self, event: dict):
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


def create_trace_app(agent, client, event_bus: EventBus) -> FastAPI:
    """Create a FastAPI app for the tracing dashboard."""

    app = FastAPI(title="XBWorld Agent Trace")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return TRACE_HTML

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
                import re
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


# ---------------------------------------------------------------------------
# Inline HTML Dashboard
# ---------------------------------------------------------------------------

TRACE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XBWorld Agent Trace</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 14px; line-height: 1.5;
}
header {
    background: #161b22; border-bottom: 1px solid #30363d; padding: 12px 20px;
    display: flex; align-items: center; gap: 16px; position: sticky; top: 0; z-index: 100;
}
header h1 { font-size: 16px; font-weight: 600; color: #58a6ff; }
.badge {
    padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500;
}
.badge-green { background: #238636; color: #fff; }
.badge-yellow { background: #9e6a03; color: #fff; }
.badge-red { background: #da3633; color: #fff; }
.badge-blue { background: #1f6feb; color: #fff; }
.header-stats {
    display: flex; gap: 12px; margin-left: auto; font-size: 13px; color: #8b949e;
}
.header-stats span { color: #c9d1d9; font-weight: 500; }

.grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 1px;
    background: #30363d;
}
.panel {
    background: #0d1117; padding: 12px 16px; overflow: hidden; display: flex; flex-direction: column;
    max-height: 500px;
}
.panel.panel-short { max-height: 300px; }
.panel.panel-tall { max-height: 700px; }
.panel-title {
    font-size: 13px; font-weight: 600; color: #8b949e; text-transform: uppercase;
    letter-spacing: 0.5px; margin-bottom: 8px; flex-shrink: 0;
}
.panel-body {
    flex: 1; overflow-y: auto; min-height: 0;
}

/* Status Panel */
.status-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px;
}
.stat-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px 12px;
}
.stat-label { font-size: 11px; color: #8b949e; text-transform: uppercase; }
.stat-value { font-size: 20px; font-weight: 600; color: #f0f6fc; }
.stat-value.gold { color: #f5c542; }
.stat-value.science { color: #58a6ff; }
.stat-value.cities { color: #3fb950; }
.stat-value.units { color: #bc8cff; }

/* Events Panel */
.event-item {
    padding: 4px 0; border-bottom: 1px solid #21262d; font-family: 'SF Mono', Consolas, monospace; font-size: 12px;
    display: flex; gap: 8px; align-items: flex-start;
}
.event-time { color: #484f58; flex-shrink: 0; min-width: 65px; }
.event-type { font-weight: 600; flex-shrink: 0; min-width: 100px; }
.event-type.turn_start { color: #3fb950; }
.event-type.turn_end { color: #f85149; }
.event-type.agent_action { color: #d2a8ff; }
.event-type.llm_response { color: #58a6ff; }
.event-detail { color: #8b949e; word-break: break-all; }

/* Performance */
.perf-bar-row {
    display: flex; align-items: center; gap: 8px; margin-bottom: 3px; font-size: 12px;
    font-family: 'SF Mono', Consolas, monospace;
}
.perf-turn { color: #8b949e; min-width: 35px; text-align: right; }
.perf-bar-container { flex: 1; height: 16px; background: #21262d; border-radius: 3px; overflow: hidden; display: flex; }
.perf-bar-llm { background: #58a6ff; height: 100%; }
.perf-bar-tool { background: #d2a8ff; height: 100%; }
.perf-bar-idle { background: #30363d; height: 100%; }
.perf-time { color: #8b949e; min-width: 40px; text-align: right; }

/* Conversation */
.conv-msg {
    margin-bottom: 8px; padding: 8px 10px; border-radius: 6px; font-size: 13px;
    font-family: 'SF Mono', Consolas, monospace; white-space: pre-wrap; word-break: break-word;
}
.conv-msg.system { background: #1c2128; border-left: 3px solid #484f58; }
.conv-msg.user { background: #0c2d6b; border-left: 3px solid #58a6ff; }
.conv-msg.assistant { background: #1a0c2b; border-left: 3px solid #d2a8ff; }
.conv-msg.tool { background: #071a07; border-left: 3px solid #3fb950; }
.conv-role {
    font-size: 11px; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;
}
.conv-role.system { color: #484f58; }
.conv-role.user { color: #58a6ff; }
.conv-role.assistant { color: #d2a8ff; }
.conv-role.tool { color: #3fb950; }
.conv-content { color: #c9d1d9; max-height: 200px; overflow-y: auto; }
.conv-tool-calls {
    margin-top: 4px; padding: 4px 8px; background: rgba(255,255,255,0.05); border-radius: 4px;
    font-size: 12px; color: #f0883e;
}

/* Action Log */
.log-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: 'SF Mono', Consolas, monospace; }
.log-table th { text-align: left; color: #8b949e; padding: 4px 8px; border-bottom: 1px solid #30363d; position: sticky; top: 0; background: #0d1117; }
.log-table td { padding: 3px 8px; border-bottom: 1px solid #21262d; }
.log-table td.turn { color: #58a6ff; }
.log-table td.action { color: #d2a8ff; }
.log-table td.detail { color: #8b949e; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Perf Legend */
.perf-legend { display: flex; gap: 12px; margin-bottom: 8px; font-size: 11px; }
.perf-legend-item { display: flex; align-items: center; gap: 4px; }
.perf-legend-dot { width: 10px; height: 10px; border-radius: 2px; }

/* Game Log */
.player-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: 'SF Mono', Consolas, monospace; margin-bottom: 12px; }
.player-table th { text-align: left; color: #8b949e; padding: 4px 8px; border-bottom: 1px solid #30363d; position: sticky; top: 0; background: #0d1117; }
.player-table td { padding: 3px 8px; border-bottom: 1px solid #21262d; }
.player-table tr.is-me { background: rgba(31, 111, 235, 0.1); }
.player-table tr.is-dead { opacity: 0.4; text-decoration: line-through; }
.player-table td.p-name { color: #f0f6fc; font-weight: 500; }
.player-table td.p-gold { color: #f5c542; }
.player-table td.p-cities { color: #3fb950; }
.player-table td.p-units { color: #bc8cff; }
.game-msg {
    padding: 3px 0; border-bottom: 1px solid #21262d; font-size: 12px;
    font-family: 'SF Mono', Consolas, monospace; color: #8b949e;
}
.game-msg .msg-event { color: #f0883e; }
.game-section-title { font-size: 11px; font-weight: 600; color: #58a6ff; margin: 8px 0 4px; text-transform: uppercase; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #484f58; }

/* Full-width panels */
.grid-full { grid-column: 1 / -1; }
</style>
</head>
<body>

<header>
    <h1>XBWorld Agent Trace</h1>
    <span id="hdr-name" class="badge badge-blue">--</span>
    <span id="hdr-phase" class="badge badge-yellow">--</span>
    <span id="hdr-turn" class="badge badge-green">Turn --</span>
    <span id="hdr-sse" class="badge badge-red">Connecting...</span>
    <div class="header-stats">
        Gold: <span id="hdr-gold">--</span> |
        Cities: <span id="hdr-cities">--</span> |
        Units: <span id="hdr-units">--</span> |
        Research: <span id="hdr-research">--</span>
    </div>
</header>

<div class="grid">
    <!-- Status Panel -->
    <div class="panel panel-short">
        <div class="panel-title">Game Status</div>
        <div class="panel-body">
            <div class="status-grid" id="status-grid"></div>
        </div>
    </div>

    <!-- Live Events -->
    <div class="panel panel-short">
        <div class="panel-title">Live Events</div>
        <div class="panel-body" id="events-body"></div>
    </div>

    <!-- Performance -->
    <div class="panel grid-full">
        <div class="panel-title">Turn Performance</div>
        <div class="perf-legend">
            <div class="perf-legend-item"><div class="perf-legend-dot" style="background:#58a6ff"></div> LLM</div>
            <div class="perf-legend-item"><div class="perf-legend-dot" style="background:#d2a8ff"></div> Tool</div>
            <div class="perf-legend-item"><div class="perf-legend-dot" style="background:#30363d"></div> Idle</div>
        </div>
        <div class="panel-body" id="perf-body"></div>
    </div>

    <!-- Conversation -->
    <div class="panel">
        <div class="panel-title">LLM Conversation</div>
        <div class="panel-body" id="conv-body"></div>
    </div>

    <!-- Action Log -->
    <div class="panel">
        <div class="panel-title">Action Log</div>
        <div class="panel-body" id="log-body">
            <table class="log-table">
                <thead><tr><th>Time</th><th>Turn</th><th>Action</th><th>Detail</th></tr></thead>
                <tbody id="log-tbody"></tbody>
            </table>
        </div>
    </div>

    <!-- Game Log -->
    <div class="panel grid-full">
        <div class="panel-title">Game Log (All Players)</div>
        <div class="panel-body" id="game-body" style="display:flex; gap:16px;">
            <div style="flex:0 0 340px; overflow-y:auto;" id="game-players"></div>
            <div style="flex:1; overflow-y:auto;" id="game-messages"></div>
        </div>
    </div>
</div>

<script>
const eventsBody = document.getElementById('events-body');
const statusGrid = document.getElementById('status-grid');
const perfBody = document.getElementById('perf-body');
const convBody = document.getElementById('conv-body');
const logTbody = document.getElementById('log-tbody');

// --- SSE ---
let sseConnected = false;
function connectSSE() {
    const es = new EventSource('/api/events');
    es.onopen = () => {
        sseConnected = true;
        document.getElementById('hdr-sse').textContent = 'LIVE';
        document.getElementById('hdr-sse').className = 'badge badge-green';
    };
    es.onmessage = (e) => {
        if (e.data.startsWith(':')) return;
        try {
            const evt = JSON.parse(e.data);
            addEvent(evt);
        } catch {}
    };
    es.onerror = () => {
        sseConnected = false;
        document.getElementById('hdr-sse').textContent = 'Disconnected';
        document.getElementById('hdr-sse').className = 'badge badge-red';
        es.close();
        setTimeout(connectSSE, 3000);
    };
}

function addEvent(evt) {
    const div = document.createElement('div');
    div.className = 'event-item';
    const now = new Date().toLocaleTimeString('en-US', {hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'});
    let detail = '';
    if (evt.type === 'turn_start') detail = `year=${evt.year || ''}`;
    else if (evt.type === 'turn_end') detail = `total=${evt.total_s}s llm=${evt.llm_s}s tool=${evt.tool_s}s`;
    else if (evt.type === 'agent_action') detail = `${evt.tool}(${JSON.stringify(evt.args||{}).substring(0,80)}) -> ${(evt.result||'').substring(0,60)}`;
    else if (evt.type === 'llm_response') detail = `${evt.model} ${evt.elapsed_s}s`;
    else detail = JSON.stringify(evt).substring(0, 120);

    div.innerHTML = `<span class="event-time">${now}</span><span class="event-type ${evt.type}">${evt.type}</span><span class="event-detail">${escHtml(detail)}</span>`;
    eventsBody.appendChild(div);
    if (eventsBody.children.length > 200) eventsBody.removeChild(eventsBody.firstChild);
    eventsBody.scrollTop = eventsBody.scrollHeight;

    // Trigger immediate refresh on turn events
    if (evt.type === 'turn_start' || evt.type === 'turn_end') {
        fetchStatus(); fetchPerf(); fetchConversation(); fetchLog(); fetchGame();
    }
}

function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function stripHtml(s) { const d = document.createElement('div'); d.innerHTML = s; return d.textContent || d.innerText || ''; }

// --- Polling ---
async function fetchStatus() {
    try {
        const r = await fetch('/api/status');
        const d = await r.json();
        document.getElementById('hdr-name').textContent = d.name || '--';
        document.getElementById('hdr-phase').textContent = d.phase || '--';
        document.getElementById('hdr-turn').textContent = `Turn ${d.turn || '--'}`;
        document.getElementById('hdr-gold').textContent = d.gold ?? '--';
        document.getElementById('hdr-cities').textContent = d.cities ?? '--';
        document.getElementById('hdr-units').textContent = d.units ?? '--';
        document.getElementById('hdr-research').textContent = d.researching || 'None';

        const bulbsPct = d.tech_cost > 0 ? Math.round(d.bulbs / d.tech_cost * 100) : 0;
        statusGrid.innerHTML = `
            <div class="stat-card"><div class="stat-label">Gold</div><div class="stat-value gold">${d.gold ?? '--'}</div></div>
            <div class="stat-card"><div class="stat-label">Tax</div><div class="stat-value">${d.tax ?? '--'}%</div></div>
            <div class="stat-card"><div class="stat-label">Science</div><div class="stat-value science">${d.science ?? '--'}%</div></div>
            <div class="stat-card"><div class="stat-label">Luxury</div><div class="stat-value">${d.luxury ?? '--'}%</div></div>
            <div class="stat-card"><div class="stat-label">Cities</div><div class="stat-value cities">${d.cities ?? '--'}</div></div>
            <div class="stat-card"><div class="stat-label">Units</div><div class="stat-value units">${d.units ?? '--'}</div></div>
            <div class="stat-card"><div class="stat-label">Research</div><div class="stat-value science">${d.researching || 'None'}</div></div>
            <div class="stat-card"><div class="stat-label">Bulbs</div><div class="stat-value">${d.bulbs || 0}/${d.tech_cost || 0} (${bulbsPct}%)</div></div>
            <div class="stat-card"><div class="stat-label">Known Techs</div><div class="stat-value">${d.known_techs ?? '--'}</div></div>
            <div class="stat-card"><div class="stat-label">Phase</div><div class="stat-value">${d.phase || '--'}</div></div>
            ${d.perf ? `<div class="stat-card"><div class="stat-label">Avg Turn</div><div class="stat-value">${d.perf.avg_turn_s}s</div></div>
            <div class="stat-card"><div class="stat-label">Last Turn</div><div class="stat-value">${d.perf.last_turn_total_s}s</div></div>` : ''}
        `;
    } catch {}
}

async function fetchPerf() {
    try {
        const r = await fetch('/api/perf');
        const d = await r.json();
        const turns = (d.turns || []).slice(-30);
        if (!turns.length) { perfBody.innerHTML = '<div style="color:#484f58">No turn data yet</div>'; return; }
        const maxTime = Math.max(...turns.map(t => t.total_s), 1);
        perfBody.innerHTML = turns.map(t => {
            const llmPct = (t.llm_s / maxTime * 100).toFixed(1);
            const toolPct = (t.tool_s / maxTime * 100).toFixed(1);
            const idlePct = (t.idle_s / maxTime * 100).toFixed(1);
            return `<div class="perf-bar-row">
                <span class="perf-turn">T${t.turn}</span>
                <div class="perf-bar-container">
                    <div class="perf-bar-llm" style="width:${llmPct}%" title="LLM: ${t.llm_s}s"></div>
                    <div class="perf-bar-tool" style="width:${toolPct}%" title="Tool: ${t.tool_s}s"></div>
                    <div class="perf-bar-idle" style="width:${idlePct}%" title="Idle: ${t.idle_s}s"></div>
                </div>
                <span class="perf-time">${t.total_s}s</span>
            </div>`;
        }).join('');
    } catch {}
}

async function fetchConversation() {
    try {
        const r = await fetch('/api/conversation?limit=20');
        const d = await r.json();
        const msgs = d.messages || [];
        convBody.innerHTML = msgs.map(m => {
            let extra = '';
            if (m.tool_calls && m.tool_calls.length) {
                extra = m.tool_calls.map(tc =>
                    `<div class="conv-tool-calls">call: ${escHtml(tc.name)}(${escHtml(tc.arguments.substring(0, 200))})</div>`
                ).join('');
            }
            const content = m.content || '';
            const displayContent = content.length > 1000 ? content.substring(0, 1000) + '...' : content;
            return `<div class="conv-msg ${m.role}">
                <div class="conv-role ${m.role}">${m.role}${m.tool_call_id ? ' [' + m.tool_call_id.substring(0, 12) + ']' : ''}</div>
                <div class="conv-content">${escHtml(displayContent)}</div>
                ${extra}
            </div>`;
        }).join('');
        convBody.scrollTop = convBody.scrollHeight;
    } catch {}
}

async function fetchLog() {
    try {
        const r = await fetch('/api/log?limit=50');
        const d = await r.json();
        const logs = (d.log || []).reverse();
        logTbody.innerHTML = logs.map(l => {
            const t = new Date(l.time * 1000);
            const ts = t.toLocaleTimeString('en-US', {hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'});
            return `<tr>
                <td>${ts}</td>
                <td class="turn">${l.turn}</td>
                <td class="action">${escHtml(l.action)}</td>
                <td class="detail" title="${escHtml(l.detail)}">${escHtml((l.detail||'').substring(0, 120))}</td>
            </tr>`;
        }).join('');
    } catch {}
}

async function fetchGame() {
    try {
        const r = await fetch('/api/game?limit=80');
        const d = await r.json();
        const players = d.players || [];
        const msgs = d.messages || [];

        const gamePlayers = document.getElementById('game-players');
        gamePlayers.innerHTML = `<div class="game-section-title">Scoreboard — Turn ${d.turn || '--'} (${d.year || ''})</div>
            <table class="player-table">
                <thead><tr><th>Player</th><th>Gold</th><th>Cities</th><th>Units</th></tr></thead>
                <tbody>${players.map(p => {
                    const cls = (!p.is_ai ? ' is-me' : '') + (!p.is_alive ? ' is-dead' : '');
                    return `<tr class="${cls}">
                        <td class="p-name">${escHtml(p.name)}${!p.is_ai ? ' (You)' : ''}</td>
                        <td class="p-gold">${p.gold ?? '?'}</td>
                        <td class="p-cities">${p.cities}</td>
                        <td class="p-units">${p.units}</td>
                    </tr>`;
                }).join('')}</tbody>
            </table>`;

        const gameMsgs = document.getElementById('game-messages');
        gameMsgs.innerHTML = `<div class="game-section-title">Server Messages</div>` +
            msgs.slice(-80).reverse().map(m => {
                const raw = typeof m === 'string' ? m : (m.message || m.text || JSON.stringify(m));
                const text = stripHtml(typeof raw === 'string' ? raw : JSON.stringify(raw));
                const mtype = typeof m === 'object' ? (m.type || '') : '';
                return `<div class="game-msg">${mtype ? `<span class="msg-event">[${escHtml(mtype)}]</span> ` : ''}${escHtml(text)}</div>`;
            }).join('');
    } catch {}
}

// --- Init ---
connectSSE();
fetchStatus(); fetchPerf(); fetchConversation(); fetchLog(); fetchGame();
setInterval(fetchStatus, 3000);
setInterval(fetchPerf, 5000);
setInterval(fetchConversation, 5000);
setInterval(fetchLog, 5000);
setInterval(fetchGame, 4000);
</script>

</body>
</html>
"""
