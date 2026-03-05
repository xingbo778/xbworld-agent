# XBWorld Agent — Code Review & OpenClaw Skill 方案

## 一、代码质量总评

整体架构设计**良好**：模块化清晰（GameClient / Agent / LLMProvider / ToolRegistry / DecisionEngine），抽象层合理，异步处理正确。以下是具体的优化建议。

---

## 二、可优化项

### 🔴 高优先级

#### 1. `EventBus` 重复定义
`trace_server.py:19` 和 `multi_main.py:86` 各定义了一个完全相同的 `EventBus` 类。应提取到公共模块。

```python
# 建议: 新建 event_bus.py 或放在 utils.py 中
# trace_server.py 和 multi_main.py 都 import 同一个
```

#### 2. `_unit_type_name` / `_tech_name` / `_building_name` / `_terrain_name` 重复
- `agent_tools.py:127-136` 定义了这4个辅助函数
- `state_api.py:19-32` 又定义了一套完全相同的

**建议**: 提取到 `game_client.py` 的 `GameState` 类中作为方法，或提取到 `utils.py`。

#### 3. `import json` 在函数内部 (llm_providers.py:268)
`OpenAIProvider.parse_response` 在 for 循环内部 `import json`，每次调用都执行。应移到文件顶部。

```python
# llm_providers.py:268 — 在循环内 import json
for tc in tool_calls_raw:
    fn = tc.get("function", {})
    import json  # ← 应该在文件顶部
```

#### 4. `from urllib.parse import unquote/quote` 在函数内部
- `game_client.py:630`: `from urllib.parse import unquote`
- `agent_tools.py:432`: `from urllib.parse import quote`

应移到文件顶部，避免每次函数调用重复解析 import。

#### 5. 对话修剪逻辑 (`_trim_conversation`) 可能破坏 tool_call 配对
`agent.py:478-504`: 当前逻辑取最近 10 条消息，跳过孤立的 tool 消息，但未验证保留的 assistant 消息的 `tool_calls` 是否都有对应的 tool response。OpenAI API 会因为不匹配而报错。

**建议**: 增加完整性校验 —— 确保每个 assistant.tool_calls 的 id 在后续 tool messages 中都有对应。

#### 6. 硬编码 `asyncio.sleep` 等待
- `agent_tools.py:436`: `await asyncio.sleep(0.8)` — found_city 后等0.8秒
- `main.py:29,37,41`: `asyncio.sleep(3)`, `asyncio.sleep(0.5)`, `asyncio.sleep(2)`
- `multi_main.py:199,208,237,244,247`: 大量固定 sleep

应改为**事件驱动**等待（监听特定 packet 到达），或至少使用 `wait_for` + 超时模式。

### 🟡 中优先级

#### 7. `found_city` 中 URL encode city name 不必要
`agent_tools.py:433`: 对 city_name 做 `urllib.parse.quote()`，但 Freeciv 协议是 JSON over WebSocket，不是 HTTP URL。除非服务器端有特殊处理，否则这是多余的（而且 `game_client.py:629` 又做了 `unquote`，说明这是一个 workaround）。

**建议**: 统一在 `GameClient.unit_found_city` 中处理编码，而不是分散在 tool 和 client 两层。

#### 8. 生产匹配逻辑重复
`agent_tools.py` 中 `change_city_production` (322-342) 和 `set_productions` (531-553) 有几乎相同的名称匹配逻辑。

**建议**: 提取公共方法 `_resolve_production(client, name) -> (kind, id, display_name)`。

#### 9. `config.py` 手动解析 `.env` 文件
`config.py:8-13`: 手动逐行解析 `.env`，不支持引号包裹的值、多行值、export 前缀等。

**建议**: 使用 `python-dotenv`（已经很轻量），或至少处理 `"` 包裹的值和 `export` 前缀。

#### 10. `trace_server.py` 内嵌巨大 HTML 字符串 (137-554)
约 400 行 HTML/CSS/JS 内嵌在 Python 文件中，难以维护。

**建议**: 移到 `static/trace.html`，用 `FileResponse` 或 `Jinja2Templates` 加载。

#### 11. 缺少重试逻辑 (LLM API 调用)
`llm_providers.py` 中 HTTP 调用没有重试。网络抖动或 rate limit (429) 会直接失败。

**建议**: 加入指数退避重试（至少对 429 和 5xx 状态码）。

### 🟢 低优先级

#### 12. `my_units()` / `my_cities()` 每次调用都遍历全部
`game_client.py:158-164`: 每次调用 `my_units()` 和 `my_cities()` 都做字典推导。在 `_autonomous_turn` 中被多次调用。

**建议**: 可以缓存结果（在 turn 开始时计算一次），或用 `@cached_property` + turn 变更时失效。

#### 13. 日志文件无 rotation
`agent.py:204-215`: `_log_llm_detail` 持续追加 JSONL，长时间运行会无限增长。

**建议**: 加文件大小限制或使用 `logging.handlers.RotatingFileHandler`。

#### 14. `LEGACY_ALIASES` 无人使用
`config.py:28-29`: `NGINX_HOST` / `NGINX_PORT` 标注为 "Legacy aliases"，但 `multi_main.py` 仍在使用。要么去掉 "legacy" 标注，要么统一使用 `SERVER_HOST`/`SERVER_PORT`。

#### 15. 缺少类型注解
多处使用 `dict` 而不是更具体的类型（如 `TypedDict`），如 `pkt: dict`、`data: dict`。对于一个协议密集的项目，严格类型能减少很多 bug。

---

## 三、安全相关

1. **API Key 泄露风险**: `LLM_API_KEY` 通过环境变量传入，但 `_log_llm_detail` 不会记录它，这是好的。需确保 `.env` 在 `.gitignore` 中。
2. **`send_command` 无过滤**: 任何服务器命令都可以通过 LLM 发送（如 `/set timeout 0`、`/save`），没有白名单限制。如果面向公众开放 API，需要增加命令过滤。
3. **`0.0.0.0` 绑定**: `config.py:48` 默认绑定所有网络接口，生产环境应限制。

---

## 四、如何做成 OpenClaw Skill

### 什么是 OpenClaw Skill？

OpenClaw 是一个 Claude Code 的 skill 插件系统。Skill 本质上是一个**提示词模板 + 触发条件**，在用户使用 `/skill-name` 或满足触发条件时自动激活。

### 方案：将 XBWorld Agent 打包为 `xbworld` Skill

#### 目标
让用户在 Claude Code 中通过 `/xbworld` 命令启动和控制 XBWorld AI 代理，实现：
- 一键启动游戏
- 自然语言控制代理
- 查看游戏状态和分析

#### 实现步骤

##### 1. 创建 Skill 配置文件

```json
// .claude/skills/xbworld.json
{
  "name": "xbworld",
  "description": "Control an AI-powered XBWorld/Freeciv agent",
  "trigger": {
    "slash_command": "/xbworld",
    "keywords": ["xbworld", "freeciv", "civilization game"]
  },
  "system_prompt_path": ".claude/skills/xbworld_prompt.md"
}
```

##### 2. 编写 Skill Prompt

```markdown
<!-- .claude/skills/xbworld_prompt.md -->
You are an XBWorld game controller. You help the user manage AI agents
playing Freeciv through the xbworld-agent system.

## Available Commands
- Start a game: `python main.py [--join PORT] [--username NAME]`
- Multi-agent: `python multi_main.py --agents N [--api]`
- API mode: POST /game/create, GET /game/status, etc.

## Architecture
- game_client.py: WebSocket client for Freeciv protocol
- agent.py: LLM-powered autonomous agent
- agent_tools.py: Game actions (move, build, research)
- multi_main.py: Multi-agent orchestrator with HTTP API

## When the user asks to:
- "start a game" → Run main.py with appropriate args
- "create agents" → Use multi_main.py
- "check status" → Query /game/status or /api/status
- "send command" → Use /agents/{name}/command API
```

##### 3. 核心改造：暴露为 MCP Server（推荐）

最强大的集成方式是将 xbworld-agent 包装为一个 **MCP (Model Context Protocol) Server**，这样 Claude Code 可以直接调用游戏工具：

```python
# mcp_server.py — 新建文件
from mcp.server import Server
from mcp.types import Tool, TextContent

from game_client import GameClient
from agent_tools import TOOL_REGISTRY, execute_tool

server = Server("xbworld")
client = None  # 全局 GameClient 实例

@server.list_tools()
async def list_tools():
    """将 TOOL_REGISTRY 中的工具导出为 MCP Tools"""
    tools = []
    for entry in TOOL_REGISTRY._tools.values():
        tools.append(Tool(
            name=entry.name,
            description=entry.description,
            inputSchema=entry.parameters,
        ))
    return tools

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """执行游戏工具"""
    result = await execute_tool(client, name, arguments)
    return [TextContent(type="text", text=result)]
```

然后在 Claude Code 的 MCP 配置中注册：

```json
// .claude/mcp.json
{
  "mcpServers": {
    "xbworld": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": {
        "XBWORLD_HOST": "localhost",
        "XBWORLD_PORT": "8080",
        "LLM_API_KEY": "${LLM_API_KEY}"
      }
    }
  }
}
```

##### 4. 项目结构变更

```
xbworld-agent/
├── .claude/
│   ├── skills/
│   │   ├── xbworld.json          # Skill 配置
│   │   └── xbworld_prompt.md     # Skill 提示词
│   └── mcp.json                  # MCP Server 配置
├── mcp_server.py                 # MCP Server 入口 (新增)
├── agent.py
├── game_client.py
├── ...
```

### 优势对比

| 方案 | 集成深度 | 实现难度 | 用户体验 |
|------|---------|---------|---------|
| 纯 Slash Command | 低 | 简单 | 只能触发提示词 |
| HTTP API + Skill | 中 | 中等 | 通过 Bash 调用 API |
| **MCP Server** | **高** | 中等 | **Claude 直接调用游戏工具** |

**推荐 MCP Server 方案**：既保留现有架构，又让 Claude Code 能直接操控游戏，用户体验最佳。

---

## 五、总结

### 代码优化 Top 5
1. 消除 `EventBus` 和辅助函数的重复定义
2. 修复 `import` 位置问题（json、urllib）
3. 加强 `_trim_conversation` 的 tool_call 配对校验
4. 将硬编码 sleep 改为事件驱动等待
5. 提取重复的生产匹配逻辑

### OpenClaw Skill 路径
1. **快速方案**: 创建 `.claude/skills/xbworld.json` + prompt（1小时）
2. **完整方案**: 实现 MCP Server，导出所有游戏工具（1天）
3. **终极方案**: MCP Server + 实时 SSE 事件流 + 游戏状态订阅（2-3天）
