"""MCP tool-call logging middleware for Cloud Run.

Logs every tool invocation as structured JSON to stdout, which Cloud Logging
picks up automatically. Captures tool name, parameters, response size, and
elapsed time.
"""

import json
import logging
import time

import pydantic_core
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext
from fastmcp.tools.tool import ToolResult

logger = logging.getLogger("mcp_daktela.tools")


class ToolLoggingMiddleware(Middleware):
    """Log every MCP tool call with structured JSON output."""

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: CallNext,
    ) -> ToolResult:
        tool_name = getattr(context.message, "name", "unknown")
        params = getattr(context.message, "arguments", None) or {}

        start = time.perf_counter()
        try:
            result: ToolResult = await call_next(context=context)
            elapsed_ms = (time.perf_counter() - start) * 1000

            # Measure response size
            try:
                response_bytes = len(pydantic_core.to_json(result.content))
            except Exception:
                response_bytes = 0

            logger.info(
                json.dumps({
                    "event": "tool_call",
                    "tool": tool_name,
                    "params": _sanitize_params(params),
                    "status": "ok",
                    "response_bytes": response_bytes,
                    "duration_ms": round(elapsed_ms, 1),
                }),
            )
            return result

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                json.dumps({
                    "event": "tool_call",
                    "tool": tool_name,
                    "params": _sanitize_params(params),
                    "status": "error",
                    "error": str(exc)[:200],
                    "duration_ms": round(elapsed_ms, 1),
                }),
            )
            raise


def _sanitize_params(params: dict) -> dict:
    """Remove or truncate large values to keep log lines reasonable."""
    sanitized = {}
    for k, v in params.items():
        if isinstance(v, str) and len(v) > 200:
            sanitized[k] = v[:200] + "..."
        else:
            sanitized[k] = v
    return sanitized
