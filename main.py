#!/usr/bin/env python3
"""
XBWorld Agent — LLM-powered autonomous game player (single agent).

Usage:
    python main.py [--join PORT] [--username NAME]

Without --join, starts a new singleplayer game.
With --join PORT, connects to an existing game server on that port.
For multi-agent games, use multi_main.py instead.
"""

import argparse
import asyncio
import logging
import os
import sys

import uvicorn

from game_client import GameClient
from agent import XBWorldAgent
from trace_server import EventBus, create_trace_app


async def setup_game(client: GameClient):
    """Wait for connection and configure a new singleplayer game."""
    await asyncio.sleep(3)

    if not client.state.connected:
        print("[Error] Failed to connect to game server.")
        return False

    print("[Setup] Connected. Configuring game...")
    await client.send_chat("/set aifill 5")
    await asyncio.sleep(0.5)
    await client.send_chat("/set timeout 0")
    await asyncio.sleep(0.5)

    print("[Setup] Starting game...")
    await client.send_chat("/start")
    await asyncio.sleep(2)

    print("[Setup] Game started. Agent taking control.\n")
    return True


async def read_stdin(agent: XBWorldAgent):
    """Read user input from stdin and forward to the agent."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            line = line.strip()
            if line:
                await agent.submit_command(line)
        except (EOFError, KeyboardInterrupt):
            break


async def main():
    parser = argparse.ArgumentParser(description="XBWorld Agent (single)")
    parser.add_argument("--join", type=int, default=None,
                        help="Join an existing game server on this port")
    parser.add_argument("--username", type=str, default=None,
                        help="Username for the agent player")
    parser.add_argument("--no-autostart", action="store_true",
                        help="Don't auto-configure and start the game")
    parser.add_argument("--trace-port", type=int,
                        default=int(os.environ.get("PORT", "8077")),
                        help="Port for tracing web dashboard (default: $PORT or 8077)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    username = args.username or "agent"
    client = GameClient(username=username)

    try:
        if args.join:
            print(f"[Agent] Joining game on port {args.join} as '{username}'...")
            await client.join_game(args.join)
        else:
            print(f"[Agent] Starting new singleplayer game as '{username}'...")
            await client.start_new_game("singleplayer")

        if not args.no_autostart and not args.join:
            ok = await setup_game(client)
            if not ok:
                return

        event_bus = EventBus()
        agent = XBWorldAgent(client, name=username, event_bus=event_bus)

        print(f"\n[{username}] Waiting for game to start...")
        print(f"[{username}] Type commands anytime. Press Enter with empty input for autonomous play.")
        print(f"[Trace] Dashboard at http://localhost:{args.trace_port}\n")

        trace_app = create_trace_app(agent, client, event_bus)
        config = uvicorn.Config(trace_app, host="0.0.0.0", port=args.trace_port, log_level="warning")
        server = uvicorn.Server(config)

        input_task = asyncio.create_task(read_stdin(agent))
        game_task = asyncio.create_task(agent.run_game_loop())
        server_task = asyncio.create_task(server.serve())

        try:
            await asyncio.gather(input_task, game_task, server_task)
        except asyncio.CancelledError:
            pass

    except KeyboardInterrupt:
        print("\n[Agent] Shutting down...")
    except Exception as e:
        print(f"\n[Error] {e}")
        logging.exception("Fatal error")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
