#!/usr/bin/env python3
"""Live integration tests for the Daktela MCP server.

Connects to the deployed Cloud Run server, runs each tool with a variety
of parameters, and reports pass/fail + response time per test.

Usage:
    python scripts/integration_test.py \
        --url https://your-instance.daktela.com \
        --username myuser \
        --password mypass \
        [--server https://your-cloud-run-url.run.app]

Credentials can also be set via env vars:
    DAKTELA_URL, DAKTELA_USERNAME, DAKTELA_PASSWORD
"""

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8080/")

# ANSI colours
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class TestResult:
    name: str
    tool: str
    params: dict
    passed: bool
    elapsed_ms: float
    error: str = ""
    preview: str = ""


@dataclass
class Suite:
    results: list[TestResult] = field(default_factory=list)

    def record(self, result: TestResult) -> None:
        self.results.append(result)
        status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
        time_str = f"{CYAN}{result.elapsed_ms:.0f}ms{RESET}"
        print(f"  {status}  {time_str:>10}  {result.name}")
        if not result.passed:
            print(f"           {RED}{result.error}{RESET}")
        elif result.preview:
            # Trim to first line and 100 chars
            preview = result.preview.split("\n")[0][:100]
            print(f"           {YELLOW}{preview}{RESET}")

    def summary(self) -> None:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        avg_ms = sum(r.elapsed_ms for r in self.results) / total if total else 0
        slowest = max(self.results, key=lambda r: r.elapsed_ms) if self.results else None

        print()
        print(f"{BOLD}{'─' * 60}{RESET}")
        print(f"{BOLD}Results: {GREEN}{passed} passed{RESET}{BOLD}, {RED}{failed} failed{RESET}{BOLD} / {total} total{RESET}")
        print(f"Avg response: {CYAN}{avg_ms:.0f}ms{RESET}")
        if slowest:
            print(f"Slowest: {CYAN}{slowest.elapsed_ms:.0f}ms{RESET}  {slowest.name}")
        if failed:
            print()
            print(f"{RED}Failed tests:{RESET}")
            for r in self.results:
                if not r.passed:
                    print(f"  • {r.name}: {r.error}")


async def call_tool(session: ClientSession, tool: str, params: dict) -> tuple[str, float]:
    """Call a tool and return (text_result, elapsed_ms)."""
    t0 = time.perf_counter()
    result = await session.call_tool(tool, params)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if result.isError:
        content = result.content[0].text if result.content else "unknown error"
        raise RuntimeError(content)

    text = result.content[0].text if result.content else ""
    return text, elapsed_ms


async def run_test(
    suite: Suite,
    session: ClientSession,
    name: str,
    tool: str,
    params: dict,
    *,
    expect_not_found: bool = False,
    expect_contains: str | None = None,
) -> None:
    try:
        text, elapsed_ms = await call_tool(session, tool, params)

        # Check for error strings in the first line (not in result content which may
        # contain "Error" in email subjects, ticket titles, etc.)
        first_line = text.split("\n", 1)[0] if text else ""
        if "Error" in first_line and not expect_not_found:
            suite.record(TestResult(name, tool, params, False, elapsed_ms, error=text[:200]))
            return

        if expect_not_found and "not found" not in text.lower():
            suite.record(TestResult(name, tool, params, False, elapsed_ms,
                                    error=f"Expected 'not found', got: {text[:100]}"))
            return

        if expect_contains and expect_contains not in text:
            suite.record(TestResult(name, tool, params, False, elapsed_ms,
                                    error=f"Expected '{expect_contains}' in output"))
            return

        suite.record(TestResult(name, tool, params, True, elapsed_ms, preview=text))

    except Exception as e:
        suite.record(TestResult(name, tool, params, False, 0, error=str(e)[:200]))


async def run_group(
    suite: Suite,
    headers: dict,
    server: str,
    label: str,
    tests: list[tuple],
) -> None:
    """Run a group of tests in a fresh MCP session. Isolates session crashes."""
    print(f"\n{BOLD}{label}{RESET}")
    try:
        async with streamablehttp_client(server, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for args in tests:
                    await run_test(suite, session, *args)
    except Exception as e:
        # Session-level failure — mark all remaining tests in this group as failed
        for args in tests:
            name = args[0]
            if not any(r.name == name for r in suite.results):
                suite.record(TestResult(name, "", {}, False, 0,
                                        error=f"Session error: {e}"))


async def main(daktela_url: str, username: str, password: str, server: str) -> int:
    headers = {
        "X-Daktela-Url": daktela_url,
        "X-Daktela-Username": username,
        "X-Daktela-Password": password,
    }

    print(f"{BOLD}Daktela MCP Integration Tests{RESET}")
    print(f"Server:   {server}")
    print(f"Instance: {daktela_url}")

    suite = Suite()

    # ── Reference / config data ──────────────────────────────────────────
    await run_group(suite, headers, server, "Reference data", [
        (tool, tool, {}) for tool in [
            "list_users", "list_queues", "list_ticket_categories",
            "list_statuses", "list_groups", "list_pauses", "list_templates",
        ]
    ])

    # ── Tickets ──────────────────────────────────────────────────────────
    await run_group(suite, headers, server, "Tickets", [
        ("count_tickets (all)",                   "count_tickets", {}),
        ("count_tickets (stage=OPEN)",             "count_tickets", {"stage": "OPEN"}),
        ("count_tickets (stage=CLOSE)",            "count_tickets", {"stage": "CLOSE"}),
        ("list_tickets (stage=OPEN, take=5)",      "list_tickets",  {"stage": "OPEN", "take": 5}),
        ("list_tickets (priority=HIGH, take=5)",   "list_tickets",  {"priority": "HIGH", "take": 5}),
        ("list_tickets (search='invoice')",        "list_tickets",  {"search": "invoice", "take": 5}),
        ("list_tickets (date range Jan 2026)",     "list_tickets",  {"date_from": "2026-01-01", "date_to": "2026-01-31", "take": 5}),
        ("get_ticket (nonexistent)",               "get_ticket",    {"name": "TK00000001"}),
    ])

    # ── Account tickets ──────────────────────────────────────────────────
    await run_group(suite, headers, server, "Account tickets", [
        ("list_account_tickets (Siemens)",              "list_account_tickets", {"account": "Siemens", "take": 5}),
        ("list_account_tickets (Siemens, stage=OPEN)",  "list_account_tickets", {"account": "Siemens", "stage": "OPEN", "take": 5}),
        ("list_account_tickets (nonexistent)",          "list_account_tickets", {"account": "NONEXISTENT_COMPANY_XYZ"}),
    ])

    # ── Activities ───────────────────────────────────────────────────────
    await run_group(suite, headers, server, "Activities", [
        ("list_activities (no filters, take=5)",       "list_activities", {"take": 5}),
        ("list_activities (type=CALL, take=5)",        "list_activities", {"type": "CALL", "take": 5}),
        ("list_activities (type=EMAIL, take=5)",       "list_activities", {"type": "EMAIL", "take": 5}),
        ("list_activities (date range today)",         "list_activities", {"date_from": "2026-02-16", "date_to": "2026-02-16", "take": 5}),
        ("list_activities (date range Jan 2026)",      "list_activities", {"date_from": "2026-01-01", "date_to": "2026-01-31", "take": 5}),
    ])

    # ── Calls ────────────────────────────────────────────────────────────
    await run_group(suite, headers, server, "Calls", [
        ("list_calls (take=5)",                    "list_calls", {"take": 5}),
        ("list_calls (direction=in, take=5)",      "list_calls", {"direction": "in", "take": 5}),
        ("list_calls (direction=out, take=5)",     "list_calls", {"direction": "out", "take": 5}),
        ("list_calls (answered=false, take=5)",    "list_calls", {"answered": False, "take": 5}),
        ("list_calls (date range Jan 2026)",       "list_calls", {"date_from": "2026-01-01", "date_to": "2026-01-31", "take": 5}),
    ])

    # ── Emails ───────────────────────────────────────────────────────────
    await run_group(suite, headers, server, "Emails", [
        ("list_emails (take=5)",               "list_emails", {"take": 5}),
        ("list_emails (direction=in, take=5)", "list_emails", {"direction": "in", "take": 5}),
        ("list_emails (date range Jan 2026)",  "list_emails", {"date_from": "2026-01-01", "date_to": "2026-01-31", "take": 5}),
    ])

    # ── Messaging channels ───────────────────────────────────────────────
    await run_group(suite, headers, server, "Messaging channels", [
        ("list_web_chats (take=5)",         "list_web_chats",        {"take": 5}),
        ("list_sms_chats (take=5)",         "list_sms_chats",        {"take": 5}),
        ("list_messenger_chats (take=5)",   "list_messenger_chats",  {"take": 5}),
        ("list_instagram_chats (take=5)",   "list_instagram_chats",  {"take": 5}),
        ("list_whatsapp_chats (take=5)",    "list_whatsapp_chats",   {"take": 5}),
        ("list_viber_chats (take=5)",       "list_viber_chats",      {"take": 5}),
    ])

    # ── Contacts & CRM ───────────────────────────────────────────────────
    await run_group(suite, headers, server, "Contacts & CRM", [
        ("list_contacts (take=5)",            "list_contacts",  {"take": 5}),
        ("list_contacts (search='a')",        "list_contacts",  {"search": "a", "take": 5}),
        ("get_contact (nonexistent)",         "get_contact",    {"name": "CT00000001"}),
        ("list_accounts (take=5)",            "list_accounts",  {"take": 5}),
        ("list_accounts (search='Siemens')",  "list_accounts",  {"search": "Siemens", "take": 5}),
        ("get_account (nonexistent)",         "get_account",    {"name": "NONEXISTENT_ACCOUNT_XYZ"}),
        ("list_crm_records (take=5)",         "list_crm_records", {"take": 5}),
        ("list_crm_records (stage=OPEN)",     "list_crm_records", {"stage": "OPEN", "take": 5}),
    ])

    # ── Campaigns ────────────────────────────────────────────────────────
    await run_group(suite, headers, server, "Campaigns", [
        ("list_campaign_types",                "list_campaign_types",   {}),
        ("list_campaign_records (take=5)",     "list_campaign_records", {"take": 5}),
    ])

    # ── Call transcripts ────────────────────────────────────────────────
    await run_group(suite, headers, server, "Call transcripts", [
        ("get_call_transcript (nonexistent)",  "get_call_transcript",   {"activity": "activity_nonexistent_xyz"},
         ),
        ("list_call_transcripts (last 7 days)", "list_call_transcripts", {"date_from": "2026-02-09", "take": 3}),
    ])

    # ── Realtime ─────────────────────────────────────────────────────────
    await run_group(suite, headers, server, "Realtime", [
        ("list_realtime_sessions", "list_realtime_sessions", {}),
    ])

    suite.summary()
    return 0 if all(r.passed for r in suite.results) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daktela MCP server integration tests")
    parser.add_argument("--url", default=os.environ.get("DAKTELA_URL", ""),
                        help="Daktela instance URL (or DAKTELA_URL env var)")
    parser.add_argument("--username", default=os.environ.get("DAKTELA_USERNAME", ""),
                        help="Daktela username (or DAKTELA_USERNAME env var)")
    parser.add_argument("--password", default=os.environ.get("DAKTELA_PASSWORD", ""),
                        help="Daktela password (or DAKTELA_PASSWORD env var)")
    parser.add_argument("--server", default=SERVER_URL,
                        help=f"MCP server URL (default: {SERVER_URL})")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    missing = [n for n, v in [("--url", args.url), ("--username", args.username),
                               ("--password", args.password)] if not v]
    if missing:
        print(f"{RED}Missing required args: {', '.join(missing)}{RESET}")
        print("Set via CLI args or DAKTELA_URL / DAKTELA_USERNAME / DAKTELA_PASSWORD env vars.")
        sys.exit(1)

    exit_code = asyncio.run(main(args.url, args.username, args.password, args.server))
    sys.exit(exit_code)
