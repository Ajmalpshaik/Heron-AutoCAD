"""autocad-mcp — an MCP server that connects Claude to a running AutoCAD.

The server talks to AutoCAD over its COM Automation interface, so it drives the
copy of AutoCAD already open on this machine: what Claude draws appears live on
screen, and what the user has open is what Claude reads.
"""

__version__ = "1.10.1"

__all__ = ["__version__"]
