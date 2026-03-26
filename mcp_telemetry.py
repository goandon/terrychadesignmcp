"""
Shared MCP telemetry module — copy this file into each MCP server as mcp_telemetry.py.

Fire-and-forget HTTP POST to the dashboard telemetry endpoint on each tool call.
NEVER blocks or raises — MCP tool operation must not be affected by telemetry failure.

Usage:
    from mcp_telemetry import report_tool_call

    @mcp_server.tool()
    async def generate_image(...):
        start = time.time()
        try:
            result = await _do_work(...)
            await report_tool_call(
                server="nanobanana", tool="generate_image",
                duration_ms=int((time.time() - start) * 1000),
                input_summary={"prompt_length": len(prompt), "size": image_size},
                output_summary={"count": 1, "file_size": len(result)},
                estimated_cost_usd=0.02,
            )
            return result
        except Exception as e:
            await report_tool_call(
                server="nanobanana", tool="generate_image",
                duration_ms=int((time.time() - start) * 1000),
                input_summary={"prompt_length": len(prompt)},
                output_summary={},
                estimated_cost_usd=0.0,
                success=False, error=str(e),
            )
            raise

Env vars:
    DASHBOARD_TELEMETRY_URL: Dashboard endpoint (default: empty, disabled)
    DASHBOARD_TELEMETRY_HOST: Host identifier (default: auto-detected hostname)

Author: Terry kim <goandonh@gmail.com>
Co-Author: Claudie
"""

from __future__ import annotations

import logging
import os
import platform
import socket
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DASHBOARD_URL = os.environ.get(
    "DASHBOARD_TELEMETRY_URL", ""
)
HOST_NAME = os.environ.get(
    "DASHBOARD_TELEMETRY_HOST", platform.node() or socket.gethostname()
)

_client = None


def _get_client():
    """Lazily create an httpx async client."""
    global _client
    if _client is None:
        try:
            import httpx
            _client = httpx.AsyncClient(timeout=5.0)
        except ImportError:
            logger.warning("httpx not installed — MCP telemetry disabled")
    return _client


async def report_tool_call(
    server: str,
    tool: str,
    duration_ms: int = 0,
    input_summary: dict | None = None,
    output_summary: dict | None = None,
    estimated_cost_usd: float = 0.0,
    success: bool = True,
    error: str | None = None,
    caller: str = "",
) -> None:
    """Fire-and-forget POST to dashboard telemetry endpoint.

    NEVER blocks or raises — MCP tool operation must not be affected.
    """
    client = _get_client()
    if client is None:
        return

    payload = {
        "event": "mcp_tool_call",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": server,
        "tool": tool,
        "host": HOST_NAME,
        "caller": caller,
        "duration_ms": duration_ms,
        "input_summary": input_summary or {},
        "output_summary": output_summary or {},
        "estimated_cost_usd": estimated_cost_usd,
        "success": success,
        "error": error,
    }

    try:
        await client.post(DASHBOARD_URL, json=payload)
    except Exception as exc:
        logger.debug("Telemetry POST failed (non-blocking): %s", exc)
