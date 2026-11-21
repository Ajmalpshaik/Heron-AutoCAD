"""Entry point for the autocad-mcp server.

Run over stdio (the default, and what Claude Desktop and Claude Code launch):

    autocad-mcp

Or over HTTP, for a client on another machine on the same network:

    autocad-mcp --transport http --port 8000
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from . import __version__
from .core.registry import mcp
from .tools import register_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocad-mcp",
        description=(
            "MCP server connecting Claude to a running AutoCAD on this machine "
            "via its COM Automation interface."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help=(
            "stdio (default) for a local client such as Claude Desktop or "
            "Claude Code; http to serve other machines on the network."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "Interface to bind when --transport http. Defaults to localhost; "
            "AutoCAD control is unauthenticated, so only widen this on a "
            "network you trust."
        ),
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind when --transport http."
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the registered tools and exit, without contacting AutoCAD.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Offer only the tools that read or view a drawing; nothing can change it.",
    )
    parser.add_argument(
        "--no-bridge",
        action="store_true",
        help=(
            "Developer use only: do not ask the Heron plug-in in AutoCAD before "
            "each call. Padlocks, banner and Keep or Discard are then skipped."
        ),
    )
    parser.add_argument(
        "--run-saved",
        metavar="REQUEST",
        help=(
            "Used by the Heron palette in AutoCAD: run one saved command from a "
            "request file, through the gate, print one JSON line and exit (D-68)."
        ),
    )
    parser.add_argument(
        "--acad-pid", type=int, default=None, help="With --run-saved: the AutoCAD process to run it in."
    )
    parser.add_argument("--version", action="version", version=f"autocad-mcp {__version__}")
    return parser


def apply_read_only(server: Any) -> list[str]:
    """Remove every tool that can change a drawing or write a file.

    Only READ and VIEW tools stay, so the AI is never offered the rest.
    """
    import asyncio

    from .core.risk import Risk, risk_of

    removed = []
    for tool in asyncio.run(server.list_tools()):
        if risk_of(tool.name) not in (Risk.READ, Risk.VIEW):
            server.remove_tool(tool.name)
            removed.append(tool.name)
    return removed


def apply_options(args: argparse.Namespace) -> None:
    """Turn command-line switches into the settings the server reads."""
    if args.no_bridge:
        os.environ["HERON_AUTOCAD_BRIDGE"] = "off"


def main() -> int:
    args = build_parser().parse_args()
    apply_options(args)
    register_all()
    if args.read_only:
        apply_read_only(mcp)

    if args.list_tools:
        import asyncio

        tools = asyncio.run(mcp.list_tools())
        print(f"autocad-mcp {__version__} — {len(tools)} tools\n")
        for tool in sorted(tools, key=lambda t: t.name):
            summary = (tool.description or "").strip().splitlines()
            print(f"  {tool.name:<32} {summary[0] if summary else ''}")
        return 0

    from . import palette

    if args.run_saved:
        # The palette's one run is a chat of its own, never the host's (D-68).
        return palette.main(args.run_saved, args.acad_pid)
    palette.write_server_file()  # so the palette in AutoCAD can find this server

    # Only the server speaks for the host's chat; scripts stay their own (D-61).
    from .core.bridge import follow_host_chat

    follow_host_chat()
    if args.transport == "http":
        # Log to stderr: stdout carries protocol traffic on stdio transport,
        # and keeping the habit avoids corrupting it if the flag is dropped.
        print(
            f"autocad-mcp {__version__} serving on http://{args.host}:{args.port}/mcp",
            file=sys.stderr,
        )
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
