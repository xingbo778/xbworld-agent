"""Configuration for XBWorld Agent and Server."""

import os
from pathlib import Path

# Load .env file if present (no external dependency needed)
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.is_file():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#"):
            continue
        # Support 'export KEY=VALUE' syntax
        if _line.startswith("export "):
            _line = _line[7:].strip()
        if "=" not in _line:
            continue
        _key, _, _val = _line.partition("=")
        _key = _key.strip()
        _val = _val.strip()
        # Strip surrounding quotes (single or double)
        if len(_val) >= 2 and _val[0] == _val[-1] and _val[0] in ('"', "'"):
            _val = _val[1:-1]
        os.environ.setdefault(_key, _val)

# XBWorld unified server
SERVER_HOST = os.getenv("XBWORLD_HOST", "localhost")
SERVER_PORT = int(os.getenv("XBWORLD_PORT", "8080"))

_USE_TLS = SERVER_PORT == 443 or os.getenv("XBWORLD_TLS", "").lower() in ("1", "true")
_HTTP_SCHEME = "https" if _USE_TLS else "http"
_WS_SCHEME = "wss" if _USE_TLS else "ws"
_PORT_SUFFIX = "" if SERVER_PORT in (80, 443) else f":{SERVER_PORT}"

LAUNCHER_URL = f"{_HTTP_SCHEME}://{SERVER_HOST}{_PORT_SUFFIX}/civclientlauncher"
WS_BASE_URL = f"{_WS_SCHEME}://{SERVER_HOST}{_PORT_SUFFIX}/civsocket"

# Game protocol (server compatibility — must match freeciv-server)
# Override FREECIV_VERSION env var to match the deployed server binary version.
# Use "+Freeciv.Web.Devel-3.3" for the legacy 3.2 server, "+Freeciv.Web.Devel-3.4" for 3.4.
FREECIV_VERSION = os.getenv("FREECIV_VERSION", "+Freeciv.Web.Devel-3.4")
MAJOR_VERSION = 3
MINOR_VERSION = int(os.getenv("FREECIV_MINOR_VERSION", "3"))
PATCH_VERSION = 90

# LLM configuration
LLM_MODEL = os.getenv("LLM_MODEL", "google/gemini-3-flash-preview")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")

# Agent behavior
MAX_MESSAGES_KEPT = 200
TURN_TIMEOUT_SECONDS = int(os.getenv("TURN_TIMEOUT", "30"))
GAME_TURN_TIMEOUT = int(os.getenv("GAME_TURN_TIMEOUT", "30"))
LLM_MAX_ITERATIONS = int(os.getenv("LLM_MAX_ITERATIONS", "5"))
INTER_TURN_DELAY_SECONDS = int(os.getenv("INTER_TURN_DELAY", "0"))

# Multi-agent HTTP API
API_HOST = os.getenv("XBWORLD_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("XBWORLD_API_PORT", "8080")))
