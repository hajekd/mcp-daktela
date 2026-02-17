#!/usr/bin/env python3
"""Integration benchmark: measure cache performance on the deployed MCP server.

Usage:
    source .env
    .venv/bin/python scripts/bench_cache.py

Requires DAKTELA_URL and either DAKTELA_ACCESS_TOKEN or
DAKTELA_USERNAME + DAKTELA_PASSWORD in environment.
"""

import asyncio
import os
import sys
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = os.environ.get(
    "MCP_SERVER_URL",
    "http://localhost:8080/",
)

# Cacheable reference-data tools to benchmark
BENCH_TOOLS = ["list_users", "list_queues", "list_ticket_categories", "list_statuses"]
ITERATIONS = 3


def _build_headers() -> dict[str, str]:
    """Build auth headers from environment variables."""
    url = os.environ.get("DAKTELA_URL", "")
    token = os.environ.get("DAKTELA_ACCESS_TOKEN", "")
    username = os.environ.get("DAKTELA_USERNAME", "")
    password = os.environ.get("DAKTELA_PASSWORD", "")

    if not url:
        print("ERROR: DAKTELA_URL not set", file=sys.stderr)
        sys.exit(1)

    headers = {"X-Daktela-Url": url}
    if token:
        headers["X-Daktela-Access-Token"] = token
    elif username and password:
        headers["X-Daktela-Username"] = username
        headers["X-Daktela-Password"] = password
    else:
        print("ERROR: Need DAKTELA_ACCESS_TOKEN or DAKTELA_USERNAME+PASSWORD", file=sys.stderr)
        sys.exit(1)

    return headers


async def bench_tool(session: ClientSession, tool_name: str) -> None:
    """Call a tool multiple times and print timing."""
    times = []
    for i in range(ITERATIONS):
        t0 = time.perf_counter()
        result = await session.call_tool(tool_name, {})
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)

        # Show record count from first text content block
        preview = ""
        if result.content and hasattr(result.content[0], "text"):
            first_line = result.content[0].text.split("\n")[0]
            preview = f"  ({first_line[:60]})"

        label = "COLD" if i == 0 else f"HIT {i}"
        print(f"  [{label}] {elapsed:7.1f} ms{preview}")

    if len(times) > 1:
        speedup = times[0] / times[1]
        print(f"  -> speedup: {speedup:.1f}x (cold {times[0]:.0f}ms vs cached {times[1]:.0f}ms)")


async def main():
    headers = _build_headers()
    print(f"MCP server: {MCP_URL}")
    print(f"Daktela:    {headers['X-Daktela-Url']}")
    print(f"Iterations: {ITERATIONS} per tool\n")

    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools for sanity check
            tools = await session.list_tools()
            print(f"Connected — {len(tools.tools)} tools available\n")

            for tool_name in BENCH_TOOLS:
                print(f"--- {tool_name} ---")
                await bench_tool(session, tool_name)
                print()


if __name__ == "__main__":
    asyncio.run(main())
