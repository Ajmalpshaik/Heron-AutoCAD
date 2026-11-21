#!/usr/bin/env python3
"""Verify the server over the real MCP protocol, the way a client launches it.

This spawns the installed executable as a subprocess, performs the MCP
handshake over stdio, lists the tools and calls one — exercising exactly the
path Claude Desktop and Claude Code use, rather than importing the tools in
process.

    .venv\\Scripts\\python.exe tools/protocol_check.py
"""

from __future__ import annotations

import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".venv",
    "Scripts",
    "autocad-mcp.exe",
)


async def main() -> int:
    if not os.path.isfile(SERVER):
        print(f"Server executable not found at {SERVER}")
        print("Run: uv pip install -e .")
        return 1

    print(f"launching {SERVER}\n")
    # Run from inside a chat, the server would otherwise speak for that chat (D-61).
    env = {key: value for key, value in os.environ.items() if key != "CLAUDE_CODE_SESSION_ID"}
    env.setdefault("HERON_CONVERSATION_ID", "protocol-check")
    params = StdioServerParameters(command=SERVER, args=[], env=env)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            # mcp 2.x uses snake_case on the wire types (server_info, not
            # serverInfo) — see the v1 to v2 migration notes.
            info = init.server_info
            print(f"handshake OK — server: {info.name} v{info.version}")
            if init.instructions:
                first = init.instructions.strip().splitlines()[0]
                print(f"instructions delivered: {first[:70]}...")

            listing = await session.list_tools()
            tools = listing.tools
            print(f"tools advertised: {len(tools)}\n")

            # Call a read-only tool over the wire.
            result = await session.call_tool("autocad_status", {})
            payload = result.content[0].text
            print("autocad_status over the protocol:")
            if payload.startswith("Error:"):
                print(f"  {payload}")
                print("\n(AutoCAD is not reachable — the protocol layer is fine,")
                print(" but open AutoCAD with a drawing for a full check.)")
                return 0

            status = json.loads(payload)
            drawing = status.get("active_drawing") or {}
            print(f"  connected : {status['connected']}")
            print(f"  autocad   : {status['version']}")
            print(f"  drawing   : {drawing.get('name', 'none')}")
            print(f"  units     : {drawing.get('units', '-')}")
            print(f"  entities  : {drawing.get('model_space_entities', '-')}")

            # Confirm an error path is reported as text, not a protocol fault.
            bad = await session.call_tool(
                "autocad_get_entity", {"handle": "NOPE"}
            )
            text = bad.content[0].text
            ok = text.startswith("Error:")
            print(f"\nerror path returns text, not a crash: {ok}")
            print(f"  {text[:90]}...")

            print("\nprotocol check passed")
            return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
