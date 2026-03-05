# XBWorld Agent

AI agent that connects to [xbworld-server](https://github.com/xingbo778/xbworld-server) and plays the game autonomously using LLM.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export XBWORLD_HOST=localhost    # Game server host
export XBWORLD_PORT=8080        # Game server port
export LLM_API_KEY=your-key     # LLM API key
export LLM_MODEL=openai/gemini-3-flash-preview

# Run single agent
python run_remote.py

# Run multi-agent game
python multi_main.py
```

## Docker

```bash
docker build -t xbworld-agent .
docker run -e XBWORLD_HOST=your-server -e LLM_API_KEY=... xbworld-agent
```

## Architecture

The agent connects to a running `xbworld-server` via WebSocket and uses LLM to make strategic decisions each turn.

```
xbworld-agent ──WebSocket──▶ xbworld-server ──TCP──▶ freeciv-server
     │
     ▼
  LLM API (Gemini/GPT/Claude)
```
