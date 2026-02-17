"""Daktela MCP Server - read-only tools for the Daktela contact center API."""

import asyncio
import os
from pathlib import Path

from fastmcp import FastMCP
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.requests import Request
from starlette.responses import Response

from mcp_daktela.auth import DaktelaAuthMiddleware
from mcp_daktela.logging_middleware import ToolLoggingMiddleware
from mcp_daktela.client import DaktelaClient
from mcp_daktela.config import get_config
from mcp_daktela.formatting import (
    _extract_id,
    format_account,
    format_account_list,
    format_activity,
    format_activity_list,
    format_call,
    format_call_list,
    format_campaign_record_list,
    format_chat,
    format_chat_list,
    format_contact,
    format_contact_list,
    format_crm_record_list,
    format_email,
    format_email_list,
    format_realtime_session_list,
    format_simple_list,
    format_ticket,
    format_ticket_list,
    format_transcript,
)
from mcp_daktela.oauth import (
    OAuthGateMiddleware,
    handle_authorization_server_metadata,
    handle_authorize,
    handle_protected_resource_metadata,
    handle_register,
    handle_token,
)

mcp = FastMCP(
    "Daktela",
    instructions=(
        "Read-only access to the Daktela contact center platform (REST API v6). "
        "Use these tools to query tickets, activities, contacts, accounts, CRM records, "
        "queues, users, campaigns, and real-time agent status.\n\n"

        "## Key naming conventions\n"
        "- Every record has a `name` field (internal unique ID) and a `title` field (human display name).\n"
        "- **user/agent filters**: pass the LOGIN NAME (the `name` field from list_users), "
        "e.g. 'john.doe', NOT the display name 'John Doe'.\n"
        "- **contact filters**: pass the contact's internal `name` ID (e.g. 'contact_674eda46162a8403430453'), "
        "NOT a person's name. Call list_contacts(search='John') first to find the ID.\n"
        "- **account filters**: pass the account's internal `name` ID (e.g. 'account_674eda46162a8403430453'), "
        "NOT the company name. Call list_accounts(search='Notino') first to find the ID. "
        "Exception: list_account_tickets accepts a human-readable company name directly.\n"
        "- **category filters**: pass the `name` field from list_ticket_categories.\n"
        "- **queue filters**: pass the `name` field from list_queues (e.g. '10333').\n\n"

        "## Ticket stages (stage field)\n"
        "OPEN = agent is actively working on it | "
        "WAIT = agent replied, waiting for customer response | "
        "CLOSE = resolved/solved | "
        "ARCHIVE = resolved, any new customer reply creates a fresh ticket\n\n"
        "**Natural language → stage mapping** (use this when interpreting user requests):\n"
        "- 'open', 'active', 'unresolved', 'pending' → stage=OPEN and/or stage=WAIT\n"
        "- 'waiting' → stage=WAIT\n"
        "- 'closed', 'resolved', 'solved', 'done' → stage=CLOSE\n"
        "- 'archived' → stage=ARCHIVE\n"
        "- To get ALL unresolved tickets (both being worked on and awaiting reply): "
        "make two calls — one with stage=OPEN and one with stage=WAIT — then combine.\n\n"

        "## Ticket priority (priority field)\n"
        "LOW | MEDIUM | HIGH\n\n"

        "## Activity types (type field)\n"
        "CALL = phone call | EMAIL = email | CHAT = web chat | SMS = SMS | "
        "FBM = Facebook Messenger | IGDM = Instagram DM | WAP = WhatsApp | "
        "VBR = Viber | CUSTOM = custom channel\n\n"

        "## Activity action/status (action field)\n"
        "OPEN = in progress | WAIT = waiting | POSTPONE = postponed | CLOSE = closed\n\n"

        "## Call direction\n"
        "in = incoming | out = outgoing | internal = internal\n\n"

        "## Entity relationships\n"
        "- Accounts are companies/organizations. Contacts belong to accounts.\n"
        "- CRM records are deals/opportunities linked to contacts, accounts, and tickets.\n"
        "- Campaign records track outbound campaign activity (calls made, results).\n\n"

        "## Workflow guidance\n"
        "- **Agent/user names are resolved automatically**: all tools that accept a 'user' parameter "
        "(list_tickets, count_tickets, list_activities, list_calls, etc.) accept display names "
        "like 'John Doe' or login names like 'john.doe'. You do NOT need to call list_users first.\n"
        "- **To find tickets for a company/account**: call list_account_tickets(account='company name') "
        "directly. Pass a COMPANY NAME like 'Notino' or 'Siemens'. "
        "The tool resolves the name automatically. Do NOT call list_accounts first.\n"
        "- **To count tickets for an agent**: call count_tickets(user='John Doe', stage='OPEN') directly.\n"
        "- When user says 'open tickets': use stage='OPEN'. "
        "For ALL unresolved tickets (both active and awaiting reply): make two calls with stage='OPEN' and stage='WAIT'.\n"
        "- **To analyze a specific ticket in depth**: use get_ticket_detail — it returns the ticket "
        "plus all linked activities (emails, calls, chats) with their content in one call.\n"
        "- **To filter tickets by workflow/sales stage**: use the status parameter "
        "(e.g. list_tickets(status='S1-Discovery')). Call list_statuses first to see available values.\n"
        "- To count or filter tickets by a category, first call list_ticket_categories to get the exact name.\n"
        "- To filter activities by queue, first call list_queues to get the queue name.\n"
        "- Use count_tickets (not list_tickets) when you only need a number — it is much faster.\n"
        "- Use get_ticket when you have a specific ticket ID (e.g. TK00123) — do not list all tickets to find one.\n"
        "- Use get_contact when you have a specific contact ID — do not list all contacts to find one.\n"
        "- Use get_activity when you have a specific activity ID — do not list all activities to find one.\n"
        "- Use get_account when you have a specific account name — do not list all accounts to find one.\n"
        "- **Channel detail tools**: use get_call, get_email, get_web_chat, get_sms, "
        "get_messenger_chat, get_instagram_chat, get_whatsapp_chat, get_viber_chat "
        "to get full details of a specific activity by channel.\n"
        "- **Call transcripts**: use list_call_transcripts to get recent calls with their "
        "full speech-to-text dialogue inline — ideal for quality review, escalation detection, "
        "or identifying calls needing management attention. Use get_call_transcript for a "
        "single call's transcript when you already know the activity name.\n"
        "- Use list_tickets(search=...) to find tickets by keyword in title/description.\n"
        "- For detailed call data (duration, CLID, missed calls), use list_calls instead of list_activities(type='CALL').\n"
        "- For detailed email data (subject, address, body), use list_emails instead of list_activities(type='EMAIL').\n"
        "- For channel-specific chat details, use list_web_chats, list_sms_chats, list_messenger_chats, etc.\n"
        "- Use list_realtime_sessions to see which agents are currently online and their status.\n"
        "- When listing activities, always specify type and/or date range to keep results focused.\n"
        "- Dates in YYYY-MM-DD or 'YYYY-MM-DD HH:MM:SS' format.\n"
        "- Pagination: use skip + take. Max take=1000. Default take=50.\n\n"

        "## Custom fields\n"
        "Tickets, activities, contacts, accounts, CRM records, and campaign records can all have "
        "instance-specific custom fields. These are returned automatically in every tool response "
        "under labeled fields. Custom fields vary per Daktela instance — they may include sales "
        "pipeline data (MRR, lead source, product), support metadata, or any business-specific attributes. "
        "Use these fields for analysis just like standard fields.\n\n"

        "## How to think about data access\n"
        "This server is designed for **active conversation analysis**, not historical reporting. "
        "The LLM's strength is understanding language, sentiment, and context — use it on live data:\n\n"

        "**Tickets → filter by stage and status, NOT by date.**\n"
        "- Open tickets (OPEN + WAIT) are the active workload — these matter regardless of age.\n"
        "- A sales lead open for 6 months is just as relevant as one opened yesterday.\n"
        "- Use stage, status, category, and priority to find what matters.\n"
        "- Closed/archived tickets are historical — only query them for specific investigations.\n\n"

        "**Activities → filter by date range.**\n"
        "- Recent calls, emails, chats (last 7 days) are the fresh conversations.\n"
        "- Many activities exist WITHOUT a ticket — standalone calls, quick chats.\n"
        "- Use date_from/date_to to scope to the relevant period.\n\n"

        "**Drill into specifics, don't bulk-download.**\n"
        "- List tickets/activities with filters to scan the landscape.\n"
        "- Use get_ticket_detail on interesting tickets to read the full conversation.\n"
        "- Use get_email, get_call, etc. for individual activity details.\n"
        "- Max 200 records per list call. Use pagination if needed.\n\n"

        "## Analytical workflow patterns\n"
        "- **What needs attention now?** List OPEN tickets sorted by SLA deadline. "
        "Check for unread tickets, overdue SLAs, high-priority items.\n"
        "- **Sales pipeline review**: list tickets by category + status (e.g. 'S1-Discovery'). "
        "Read custom fields (MRR, product, source) to assess each lead.\n"
        "- **Agent performance**: list recent calls/emails per agent. "
        "Check handle time, missed calls, response patterns.\n"
        "- **Customer deep-dive**: find contact → list their open tickets → "
        "get_ticket_detail on each to read the conversation history.\n"
        "- **Operational health**: check missed calls (last 7 days), realtime agent sessions, "
        "SLA breaches on open tickets.\n"
        "- **Communication quality**: use get_ticket_detail or get_email to read actual content "
        "for sentiment analysis, quality assessment, or escalation detection.\n"
        "- **Call quality / management attention**: use list_call_transcripts(date_from=..., take=10) "
        "to get recent calls with full dialogue, then analyze transcripts for customer frustration, "
        "escalation requests, compliance issues, or exceptional service.\n\n"

        "## Data presentation\n"
        "Always choose the richest appropriate format — default to visual when the data supports it.\n\n"

        "**Charts** — create a React artifact using Recharts (render inline, not as a code block):\n"
        "- Per-day, per-hour, or any time-series breakdown → bar chart (X = date/time, Y = count or duration)\n"
        "- Trends across multiple periods → line chart\n"
        "- Comparisons across queues, agents, or channels → horizontal bar chart sorted by value\n"
        "- Distributions (call duration buckets, ticket age, etc.) → bar chart\n"
        "- When a date range spans 3 or more days, default to a per-day chart unless asked otherwise\n\n"

        "**Tables** — markdown table:\n"
        "- Any list of records with 3 or more fields (tickets, agents, contacts, calls)\n"
        "- Leaderboards (top agents by volume, resolution rate, handle time, etc.)\n\n"

        "**Inline figures:**\n"
        "- Single counts or percentages → bold the key number, one sentence of context\n\n"

        "**Always follow every chart or table with a 2–3 sentence insight**: name the peak, the outlier, "
        "or the actionable takeaway. Don't just display data — interpret it.\n\n"

        "**Contact center defaults:**\n"
        "- Missed calls, answered calls, handle time → bar chart by day/queue/agent\n"
        "- Ticket volume by stage, priority, or category → bar chart\n"
        "- Agent activity or performance summary → ranked table\n"
        "- Real-time agent status → table (agent, state, pause reason)\n"
        "- SLA figures → bold percentage with a one-line verdict (on track / at risk / breached)"
    ),
)
mcp.add_middleware(DaktelaAuthMiddleware())
mcp.add_middleware(ToolLoggingMiddleware())

# ASGI middleware: returns 401 + WWW-Authenticate on /mcp when no auth is present
oauth_gate_middleware = ASGIMiddleware(OAuthGateMiddleware)

# OAuth 2.0 endpoints for Claude Desktop "Add custom connector" flow
mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])(
    handle_protected_resource_metadata
)
mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])(
    handle_authorization_server_metadata
)
mcp.custom_route("/oauth/register", methods=["POST"])(handle_register)
mcp.custom_route("/oauth/authorize", methods=["GET", "POST"])(handle_authorize)
mcp.custom_route("/oauth/token", methods=["POST"])(handle_token)

_LOGO_PATH = Path(__file__).parent / "static" / "logo.png"


async def _handle_logo(request: Request) -> Response:
    if not _LOGO_PATH.exists():
        return Response(status_code=404)
    return Response(
        content=_LOGO_PATH.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


mcp.custom_route("/logo.png", methods=["GET"])(_handle_logo)


# Hard limits to protect the API and keep responses context-friendly.
# The total count is always returned so the LLM can paginate if needed.
_MAX_TAKE_DATA = 200       # tickets, activities, calls, emails, chats, CRM, campaigns
_MAX_TAKE_REFERENCE = 1000  # users, queues, categories, groups, statuses, pauses, templates
_MAX_TAKE_DETAIL = 100      # activities inside get_ticket_detail


def _get_client() -> DaktelaClient:
    config = get_config()
    url = config["url"]
    if "username" in config:
        return DaktelaClient(url, username=config["username"], password=config["password"])
    return DaktelaClient(url, token=config["token"])


def _get_base_url() -> str:
    """Return the Daktela instance base URL (without trailing slash)."""
    return get_config()["url"].rstrip("/")


def _date_filters(
    field: str, date_from: str | None, date_to: str | None
) -> list[tuple[str, str, str]]:
    """Build date range filter tuples.

    Daktela expects 'YYYY-MM-DD HH:MM:SS'. A bare date like '2026-02-17'
    is treated as midnight (00:00:00), so date_to without a time component
    would exclude everything that happened during that day. We append
    ' 23:59:59' to date_to when no time is present.
    """
    filters = []
    if date_from:
        # Normalize ISO 8601 'T' separator
        filters.append((field, "gte", date_from.replace("T", " ")))
    if date_to:
        normalized = date_to.replace("T", " ")
        # If only a date was given (no time component), include the full day
        if len(normalized) == 10:
            normalized = normalized + " 23:59:59"
        filters.append((field, "lte", normalized))
    return filters


# Valid sort fields per endpoint family. Sorting by an unknown field
# silently returns 0 results from the Daktela API, so we drop invalid sorts.
_SORT_FIELDS: dict[str, set[str]] = {
    "tickets": {"name", "title", "created", "edited", "last_activity",
                "last_activity_operator", "last_activity_client",
                "sla_deadtime", "sla_close_deadline", "priority", "stage",
                "first_answer", "closed"},
    "activities": {"time", "time_close", "duration", "ringing_time"},
    "activitiesCall": {"call_time", "duration", "waiting_time", "ringing_time"},
    "activitiesEmail": {"time", "duration", "wait_time"},
    "activitiesWeb": {"time", "duration", "wait_time"},
    "activitiesSms": {"time", "duration", "wait_time"},
    "activitiesFbm": {"time", "duration", "wait_time"},
    "activitiesIgdm": {"time", "duration", "wait_time"},
    "activitiesWap": {"time", "duration", "wait_time"},
    "activitiesVbr": {"time", "duration", "wait_time"},
    "contacts": {"created", "edited", "title", "lastname"},
    "accounts": {"created", "edited", "title"},
    "crmRecords": {"created", "edited", "title", "stage"},
    "campaignsRecords": {"created", "edited", "nextcall"},
    "activitiesCallTranscripts": {"start", "end"},
}


def _validated_sort(endpoint: str, sort: str | None) -> str | None:
    """Return sort field if valid for the endpoint, otherwise None."""
    if sort is None:
        return None
    allowed = _SORT_FIELDS.get(endpoint)
    if allowed is None:
        return sort  # unknown endpoint — pass through
    return sort if sort in allowed else None


async def _resolve_user(client: DaktelaClient, user_input: str) -> tuple[str, str | None]:
    """Resolve a user display name or login name to (login_name, display_name).

    Searches by display name (title) first. If there's an exact match, uses it.
    Otherwise falls back to the first partial match. If nothing matches by title,
    tries matching by login name. Returns the input as-is if nothing matches.
    """
    # Search by display name
    result = await client.list(
        "users",
        field_filters=[("title", "like", user_input)],
        take=10,
        fields=["name", "title"],
    )
    if result["data"]:
        # Prefer exact title match
        for u in result["data"]:
            if u.get("title", "").strip().lower() == user_input.strip().lower():
                return u["name"], u.get("title")
        # Fall back to first match
        return result["data"][0]["name"], result["data"][0].get("title")

    # Search by login name
    result = await client.list(
        "users",
        field_filters=[("name", "like", user_input)],
        take=10,
        fields=["name", "title"],
    )
    if result["data"]:
        for u in result["data"]:
            if u["name"].lower() == user_input.strip().lower():
                return u["name"], u.get("title")
        return result["data"][0]["name"], result["data"][0].get("title")

    # Nothing found — use as-is
    return user_input, None


def _build_ticket_filters(
    *,
    category: str | None = None,
    stage: str | None = None,
    priority: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    search: str | None = None,
    status: str | None = None,
    include_merged: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[tuple[str, str, str]]:
    """Build the filter list shared by list_tickets, count_tickets, and list_account_tickets."""
    filters: list[tuple[str, str, str]] = []
    if category:
        filters.append(("category", "eq", category))
    if stage:
        filters.append(("stage", "eq", stage))
    if priority:
        filters.append(("priority", "eq", priority))
    if user:
        filters.append(("user", "eq", user))
    if contact:
        filters.append(("contact", "eq", contact))
    if search:
        filters.append(("title", "like", search))
    if status:
        filters.append(("statuses", "eq", status))
    if not include_merged:
        filters.append(("id_merge", "isnull", "true"))
    filters.extend(_date_filters("created", date_from, date_to))
    return filters


async def _list_channel_chats(
    endpoint: str,
    entity: str,
    channel: str = "chat",
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    direction: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """Shared implementation for all list_*_chats tools."""
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort(endpoint, sort)
    async with _get_client() as client:
        if user:
            user, _ = await _resolve_user(client, user)

        filters: list[tuple[str, str, str]] = []
        if queue:
            filters.append(("queue", "eq", queue))
        if user:
            filters.append(("user", "eq", user))
        if contact:
            filters.append(("contact", "eq", contact))
        if direction:
            filters.append(("direction", "eq", direction))
        filters.extend(_date_filters("time", date_from, date_to))

        result = await client.list(
            endpoint,
            field_filters=filters or None,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
        )
    return format_chat_list(
        result["data"], result["total"], skip, take, entity,
        channel=channel, base_url=_get_base_url(),
    )


async def _get_channel_record(
    endpoint: str, entity_label: str, name: str, channel: str = "chat",
) -> str:
    """Shared implementation for all get_*_chat/get_sms tools."""
    async with _get_client() as client:
        record = await client.get(endpoint, name)
    if record is None:
        return f"{entity_label} '{name}' not found."
    return format_chat(record, channel=channel, base_url=_get_base_url())


# ---------------------------------------------------------------------------
# Ticket tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_tickets(
    category: str | None = None,
    stage: str | None = None,
    priority: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    search: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_merged: bool = False,
    sort: str = "edited",
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List tickets with optional filters. Returns one page of results.

    Args:
        category: Filter by category internal name (use list_ticket_categories to find valid names).
        stage: Ticket lifecycle stage — exact values (case-sensitive):
            'OPEN' = agent actively working on it,
            'WAIT' = reply sent, awaiting customer response,
            'CLOSE' = resolved/solved,
            'ARCHIVE' = resolved and archived.
            When user says "open tickets", use stage='OPEN'.
        priority: Filter by priority: LOW, MEDIUM, HIGH.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Display names are resolved automatically. You do NOT need to
            call list_users first.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        search: Full-text search across ticket title and description (partial match).
        status: Filter by workflow status name (e.g. 'S0-Qualify', 'S1-Discovery').
            Use list_statuses to see available status names. This filters on the ticket's
            statuses MN relation — useful for sales pipeline stages, custom workflows, etc.
        date_from: Filter tickets created on or after this date (YYYY-MM-DD).
        date_to: Filter tickets created on or before this date (YYYY-MM-DD).
        include_merged: Include tickets that were merged into other tickets (default: false).
        sort: Field to sort by. Useful values: edited (default), created, sla_deadtime,
            sla_close_deadline, last_activity.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Number of records to skip for pagination (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort("tickets", sort)
    async with _get_client() as client:
        resolved_name = None
        if user:
            user, resolved_name = await _resolve_user(client, user)

        filters = _build_ticket_filters(
            category=category, stage=stage, priority=priority,
            user=user, contact=contact, search=search, status=status,
            include_merged=include_merged, date_from=date_from, date_to=date_to,
        )

        result = await client.list(
            "tickets",
            field_filters=filters or None,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
        )
    header = ""
    if resolved_name:
        header = f"Agent: **{resolved_name}** ({user})\n\n"
    return header + format_ticket_list(result["data"], result["total"], skip, take, base_url=_get_base_url())


@mcp.tool()
async def count_tickets(
    category: str | None = None,
    stage: str | None = None,
    priority: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    search: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_merged: bool = False,
) -> str:
    """Count tickets matching filters. Use this instead of list_tickets when you only need a number.

    Args:
        category: Filter by category internal name (use list_ticket_categories to find valid names).
        stage: Ticket lifecycle stage — exact values (case-sensitive):
            'OPEN' = agent actively working,
            'WAIT' = awaiting customer response,
            'CLOSE' = resolved,
            'ARCHIVE' = archived.
            When user says "open tickets", use stage='OPEN'.
        priority: Filter by priority: LOW, MEDIUM, HIGH.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Display names are resolved automatically. You do NOT need to
            call list_users first.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        search: Full-text search across ticket title and description (partial match).
        status: Filter by workflow status name (e.g. 'S0-Qualify', 'S1-Discovery').
            Use list_statuses to see available status names.
        date_from: Filter tickets created on or after this date (YYYY-MM-DD).
        date_to: Filter tickets created on or before this date (YYYY-MM-DD).
        include_merged: Include tickets that were merged into other tickets (default: false).
    """
    async with _get_client() as client:
        resolved_name = None
        if user:
            user, resolved_name = await _resolve_user(client, user)

        filters = _build_ticket_filters(
            category=category, stage=stage, priority=priority,
            user=user, contact=contact, search=search, status=status,
            include_merged=include_merged, date_from=date_from, date_to=date_to,
        )

        result = await client.list(
            "tickets",
            field_filters=filters or None,
            skip=0,
            take=1,
            fields=["name"],
        )
    total = result["total"]
    parts = []
    if category:
        parts.append(f"category={category}")
    if stage:
        parts.append(f"stage={stage}")
    if priority:
        parts.append(f"priority={priority}")
    if user:
        agent_label = f"{resolved_name} ({user})" if resolved_name else user
        parts.append(f"user={agent_label}")
    if contact:
        parts.append(f"contact={contact}")
    if search:
        parts.append(f"search={search!r}")
    if status:
        parts.append(f"status={status}")
    if date_from:
        parts.append(f"from {date_from}")
    if date_to:
        parts.append(f"to {date_to}")

    filter_desc = f" matching [{', '.join(parts)}]" if parts else ""
    return f"Total tickets{filter_desc}: **{total}**"


@mcp.tool()
async def get_ticket(name: str) -> str:
    """Get full details of a single ticket by its ID. Use this when you already know the ticket ID.

    Args:
        name: The ticket ID (numeric, e.g. 787979). If passed with a prefix like TK00787979, the prefix is stripped automatically.
    """
    # Strip common prefixes — Daktela ticket IDs are plain numbers
    cleaned = str(name).lstrip("TKtk").lstrip("0") or str(name)
    async with _get_client() as client:
        record = await client.get("tickets", cleaned)
    if record is None:
        return f"Ticket '{name}' not found."
    return format_ticket(record, base_url=_get_base_url(), detail=True)


@mcp.tool()
async def get_ticket_detail(name: str, take: int = 50) -> str:
    """Get a ticket with all its activities and their content in one call.

    This is the recommended tool for analyzing a specific ticket — it returns the
    ticket details plus all linked activities (calls, emails, chats, etc.) with
    their descriptions and metadata, avoiding multiple round-trips.

    Args:
        name: The ticket ID (numeric, e.g. 787979). Prefix like TK00787979 is stripped automatically.
        take: Max number of activities to include (default: 50, max: 100).
    """
    cleaned = str(name).lstrip("TKtk").lstrip("0") or str(name)
    take = min(take, _MAX_TAKE_DETAIL)
    base_url = _get_base_url()

    async with _get_client() as client:
        ticket = await client.get("tickets", cleaned)
        if ticket is None:
            return f"Ticket '{name}' not found."

        # Fetch activities linked to this ticket
        activities_result = await client.list(
            "activities",
            field_filters=[("ticket", "eq", cleaned)],
            skip=0,
            take=take,
            sort="time",
            sort_dir="asc",
        )

    # Format ticket
    parts = [format_ticket(ticket, base_url=base_url, detail=True)]

    # Format activities
    activities = activities_result["data"]
    total_activities = activities_result["total"]
    if activities:
        parts.append(f"\n--- Activities ({len(activities)} of {total_activities}) ---")
        for act in activities:
            parts.append(format_activity(act, base_url=base_url, detail=True))
    else:
        parts.append("\n--- No activities ---")

    if total_activities > take:
        parts.append(f"\n(Showing first {take} of {total_activities} activities. "
                      f"Use list_activities(ticket='{cleaned}', skip={take}) for more.)")

    return "\n\n".join(parts)


@mcp.tool()
async def list_account_tickets(
    account: str,
    stage: str = "OPEN",
    priority: str | None = None,
    user: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_merged: bool = False,
    sort: str = "edited",
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List tickets for a specific account (company/organization).

    Accepts both a company name (e.g. 'Notino') or an internal account ID.
    The tool resolves the name automatically. You do NOT need to call list_accounts first.

    Args:
        account: Company name (partial match, e.g. 'Notino', 'Siemens') or account ID.
        stage: Ticket stage filter (default: 'OPEN'). Values:
            'OPEN' = agent actively working on it (default),
            'WAIT' = reply sent, awaiting customer response,
            'CLOSE' = resolved/solved,
            'ARCHIVE' = resolved and archived,
            'ALL' = return tickets in any stage (slower for large accounts).
        priority: Filter by priority: LOW, MEDIUM, HIGH.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        category: Filter by category internal name (use list_ticket_categories to find valid names).
        date_from: Filter tickets created on or after this date (YYYY-MM-DD).
        date_to: Filter tickets created on or before this date (YYYY-MM-DD).
        include_merged: Include tickets that were merged into other tickets (default: false).
        sort: Field to sort by. Useful values: edited (default), created, sla_deadtime,
            sla_close_deadline, last_activity.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Number of records to skip for pagination (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort("tickets", sort)
    async with _get_client() as client:
        # Step 1: Resolve account — try exact ID first, then fuzzy title search
        account_data = await client.get("accounts", account)
        if account_data:
            account_id = account_data["name"]
            account_title = account_data.get("title", account_id)
        else:
            search_result = await client.list(
                "accounts",
                field_filters=[("title", "like", account)],
                take=1,
            )
            if not search_result["data"]:
                return f"No account found matching '{account}'."
            account_id = search_result["data"][0]["name"]
            account_title = search_result["data"][0].get("title", account_id)

        # Step 2: Get contacts belonging to this account
        contacts_result = await client.list(
            "contacts",
            field_filters=[("account", "eq", account_id)],
            take=1000,
            fields=["name"],
        )
        contact_names = [c["name"] for c in contacts_result["data"]]
        if not contact_names:
            return (
                f"Account: **{account_title}** ({account_id})\n\n"
                "No contacts found for this account, so no tickets can be retrieved."
            )

        # Step 3: Query tickets using 'in' operator with batched contacts (parallel)
        stage_filter = stage if stage and stage.upper() != "ALL" else None
        ticket_filters = _build_ticket_filters(
            category=category, stage=stage_filter, priority=priority,
            user=user, include_merged=include_merged,
            date_from=date_from, date_to=date_to,
        )

        batch_size = 50
        batches = [
            contact_names[i:i + batch_size]
            for i in range(0, len(contact_names), batch_size)
        ]

        async def _fetch_batch(batch: list[str]) -> list[dict]:
            filters = ticket_filters + [("contact", "in", batch)]
            result = await client.list(
                "tickets",
                field_filters=filters,
                skip=0,
                take=1000,
                sort=sort,
                sort_dir=sort_dir,
            )
            return result["data"]

        # Cap parallel batches to avoid hammering the API on huge accounts
        max_batches = 10
        batch_results = await asyncio.gather(*[_fetch_batch(b) for b in batches[:max_batches]])

        all_tickets: list[dict] = []
        seen: set = set()
        for tickets in batch_results:
            for ticket in tickets:
                tid = ticket.get("name", "")
                if tid not in seen:
                    seen.add(tid)
                    all_tickets.append(ticket)

    total = len(all_tickets)
    page = all_tickets[skip:skip + take]
    header = f"Account: **{account_title}** ({account_id})\n\n"
    return header + format_ticket_list(page, total, skip, take, base_url=_get_base_url())


@mcp.tool()
async def list_ticket_categories(
    skip: int = 0,
    take: int = 200,
) -> str:
    """List all ticket categories. Call this first to find valid category names for ticket filtering.
    The 'name' field of each category is what you pass as the 'category' parameter in list_tickets/count_tickets.

    Args:
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 200).
    """
    async with _get_client() as client:
        result = await client.list("ticketsCategories", skip=skip, take=take)
    return format_simple_list(result["data"], result["total"], skip, take, "categories")


# ---------------------------------------------------------------------------
# Generic activity tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_activities(
    type: str | None = None,
    action: str | None = None,
    queue: str | None = None,
    ticket: str | None = None,
    user: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List activities (calls, emails, chats, etc.) with optional filters.
    Always specify type and/or a date range to keep results focused.

    Args:
        type: Filter by activity channel type:
            CALL (phone), EMAIL, CHAT (web chat), SMS,
            FBM (Facebook Messenger), IGDM (Instagram DM),
            WAP (WhatsApp), VBR (Viber), CUSTOM.
        action: Filter by activity status/action:
            OPEN (in progress), WAIT (waiting), POSTPONE (postponed), CLOSE (closed).
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        ticket: Filter by ticket ID (numeric, e.g. '787979').
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        date_from: Filter by activity start time on or after this date (YYYY-MM-DD).
        date_to: Filter by activity start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: time (activity start time), duration, time_close.
            WARNING: only fields that exist on the activities endpoint work — do NOT use
            'created' or 'edited' (those are ticket fields, not activity fields).
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort("activities", sort)
    async with _get_client() as client:
        if user:
            user, _ = await _resolve_user(client, user)

        filters: list[tuple[str, str, str]] = []
        if type:
            filters.append(("type", "eq", type))
        if action:
            filters.append(("action", "eq", action))
        if queue:
            filters.append(("queue", "eq", queue))
        if ticket:
            filters.append(("ticket", "eq", ticket))
        if user:
            filters.append(("user", "eq", user))
        filters.extend(_date_filters("time", date_from, date_to))

        result = await client.list(
            "activities",
            field_filters=filters or None,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
        )
    return format_activity_list(result["data"], result["total"], skip, take, base_url=_get_base_url())


@mcp.tool()
async def get_activity(name: str) -> str:
    """Get full details of a single activity by its ID. Use this when you already know the activity ID.
    Returns the complete activity record including all channel-specific fields.

    Args:
        name: The activity ID (e.g. ACT00123). Always starts with 'ACT' followed by digits.
    """
    async with _get_client() as client:
        record = await client.get("activities", name)
    if record is None:
        return f"Activity '{name}' not found."
    return format_activity(record, base_url=_get_base_url(), detail=True)


# ---------------------------------------------------------------------------
# Channel-specific activity tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_calls(
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    direction: str | None = None,
    answered: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List phone calls with detailed call data (duration, CLID, missed calls, hold time).
    Use this instead of list_activities(type='CALL') when you need call-specific fields.

    Args:
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        direction: Filter by call direction: in (incoming), out (outgoing), internal.
        answered: Filter by whether the call was answered (true/false).
        date_from: Filter by call start time on or after this date (YYYY-MM-DD).
        date_to: Filter by call start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: call_time, duration, waiting_time, ringing_time.
            WARNING: only call-specific fields work — do NOT use 'created' or 'edited'.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort("activitiesCall", sort)
    async with _get_client() as client:
        if user:
            user, _ = await _resolve_user(client, user)

        filters: list[tuple[str, str, str]] = []
        if queue:
            filters.append(("id_queue", "eq", queue))
        if user:
            filters.append(("id_agent", "eq", user))
        if contact:
            filters.append(("contact", "eq", contact))
        if direction:
            filters.append(("direction", "eq", direction))
        if answered is not None:
            filters.append(("answered", "eq", str(answered).lower()))
        filters.extend(_date_filters("call_time", date_from, date_to))

        result = await client.list(
            "activitiesCall",
            field_filters=filters or None,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
            # Exclude heavy nested objects: activities (120 KB), contact (110 KB)
            # per record — 237 KB → 2.7 KB each. Use get_call for full details.
            fields=[
                "id_call", "call_time", "direction", "answered",
                "id_queue", "id_agent", "clid",
                "prefix_clid_name", "did", "waiting_time",
                "ringing_time", "hold_time", "duration",
                "disposition_cause", "disconnection_cause",
                "pressed_key", "missed_call", "missed_call_time",
                "missed_callback", "attempts",
            ],
        )
    return format_call_list(result["data"], result["total"], skip, take, base_url=_get_base_url())


@mcp.tool()
async def get_call(name: str) -> str:
    """Get full details of a single call by its call ID. Use this when you already know the call ID.
    Returns call-specific fields: CLID, duration, wait/ring/hold times, missed call status, disposition.

    Args:
        name: The call ID (the 'id_call' field from list_calls).
    """
    async with _get_client() as client:
        record = await client.get("activitiesCall", name)
    if record is None:
        return f"Call '{name}' not found."
    return format_call(record, base_url=_get_base_url())


@mcp.tool()
async def get_call_transcript(activity: str) -> str:
    """Get the full speech-to-text transcript of a specific call.

    Returns the spoken dialogue between customer and operator as a chronological
    transcript with timestamps. Not all calls have transcripts — missed calls,
    short calls, and calls on queues without speech-to-text will return
    "No transcript available".

    How to get the activity name:
    - From list_calls: the 'Activity' field in each call record
    - From list_activities: the 'name' field of a CALL activity
    - From get_call: the 'Activity' field in the call record

    Args:
        activity: The activity name/ID (e.g. 'activity_699351d84288a407003861').
            This is the 'Activity' field shown in list_calls/get_call output,
            or the 'name' field from list_activities.
    """
    async with _get_client() as client:
        result = await client.list(
            "activitiesCallTranscripts",
            field_filters=[("activity", "eq", activity)],
            skip=0,
            take=200,
            sort="start",
            sort_dir="asc",
        )
    return format_transcript(result["data"], activity_name=activity)


@mcp.tool()
async def list_call_transcripts(
    date_from: str | None = None,
    date_to: str | None = None,
    user: str | None = None,
    queue: str | None = None,
    skip: int = 0,
    take: int = 20,
) -> str:
    """List answered calls with their full speech-to-text transcripts inline.

    This is the primary tool for analyzing call quality, identifying calls requiring
    management attention, detecting escalations, or reviewing agent performance.
    Each call is returned with its complete dialogue (customer + operator).

    Fetches up to `take` answered calls and automatically retrieves their
    transcripts in parallel (server-side). Calls without transcripts are included
    but marked "No transcript available".

    For comprehensive analysis of a date range, paginate using skip:
    first call with skip=0, then skip=50, skip=100, etc. until all calls are covered.

    Args:
        date_from: Filter calls on or after this date (YYYY-MM-DD). Recommended: last 7 days.
        date_to: Filter calls on or before this date (YYYY-MM-DD).
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        skip: Number of calls to skip for pagination (default: 0).
        take: Number of calls to fetch per page (default: 20, max: 50). Each call includes
            its full transcript — transcripts are fetched in parallel server-side.
    """
    take = min(take, 50)

    async with _get_client() as client:
        if user:
            user, _ = await _resolve_user(client, user)

        # Step 1: Fetch answered calls
        filters: list[tuple[str, str, str]] = [("answered", "eq", "true")]
        if queue:
            filters.append(("id_queue", "eq", queue))
        if user:
            filters.append(("id_agent", "eq", user))
        filters.extend(_date_filters("call_time", date_from, date_to))

        # Request only lightweight fields to avoid OOM from huge nested objects
        # (contact=110KB, id_agent=10KB each — fully expanded by Daktela API).
        calls_result = await client.list(
            "activitiesCall",
            field_filters=filters,
            skip=skip,
            take=take,
            sort="call_time",
            sort_dir="desc",
            fields=[
                "id_call", "call_time", "direction", "answered",
                "id_queue", "id_agent", "clid", "duration",
                "activities",
            ],
        )
        calls = calls_result["data"]
        total = calls_result["total"]
        if not calls:
            return "No answered calls found matching the filters."

        # Step 2: Extract activity names from calls
        activity_names = []
        for call in calls:
            activities = call.get("activities")
            if activities and isinstance(activities, list) and activities:
                act_name = _extract_id(activities[0])
                if act_name:
                    activity_names.append(act_name)
                else:
                    activity_names.append(None)
            else:
                activity_names.append(None)

        # Step 3: Fetch transcripts in parallel (limited concurrency to avoid OOM)
        sem = asyncio.Semaphore(5)

        async def _fetch_transcript(act_name: str | None) -> list[dict]:
            if not act_name:
                return []
            async with sem:
                result = await client.list(
                    "activitiesCallTranscripts",
                    field_filters=[("activity", "eq", act_name)],
                    skip=0,
                    take=200,
                    sort="start",
                    sort_dir="asc",
                    fields=["text", "type", "start", "end"],
                )
                return result["data"]

        transcript_results = await asyncio.gather(
            *[_fetch_transcript(name) for name in activity_names]
        )

    # Step 4: Combine call metadata + transcripts
    base_url = _get_base_url()
    parts = [f"Showing {skip + 1}-{skip + len(calls)} of {total} answered calls with transcripts:\n"]

    for i, call in enumerate(calls):
        call_text = format_call(call, base_url=base_url)
        act_name = activity_names[i] if i < len(activity_names) else None
        segments = transcript_results[i] if i < len(transcript_results) else []
        transcript_text = format_transcript(segments, activity_name=act_name)
        parts.append(f"{call_text}\n{transcript_text}")

    result = "\n\n---\n\n".join(parts)
    if skip + len(calls) < total:
        result += f"\n\n(Use skip={skip + len(calls)} to see next page)"
    return result


@mcp.tool()
async def get_email(name: str) -> str:
    """Get full details of a single email activity by its ID.
    Returns email-specific fields including subject, address, body text, and timing.

    Args:
        name: The email activity ID (e.g. 'ACT00123' or the 'name' field from list_emails).
    """
    async with _get_client() as client:
        record = await client.get("activitiesEmail", name)
    if record is None:
        return f"Email '{name}' not found."
    return format_email(record, base_url=_get_base_url(), detail=True)


@mcp.tool()
async def get_web_chat(name: str) -> str:
    """Get full details of a single web chat activity by its ID.

    Args:
        name: The web chat activity ID (e.g. 'ACT00123' or the 'name' field from list_web_chats).
    """
    return await _get_channel_record("activitiesWeb", "Web chat", name)


@mcp.tool()
async def get_sms(name: str) -> str:
    """Get full details of a single SMS activity by its ID.

    Args:
        name: The SMS activity ID (e.g. 'ACT00123' or the 'name' field from list_sms_chats).
    """
    return await _get_channel_record("activitiesSms", "SMS", name)


@mcp.tool()
async def get_messenger_chat(name: str) -> str:
    """Get full details of a single Facebook Messenger activity by its ID.

    Args:
        name: The Messenger activity ID (e.g. 'ACT00123' or the 'name' field from list_messenger_chats).
    """
    return await _get_channel_record("activitiesFbm", "Messenger chat", name)


@mcp.tool()
async def get_instagram_chat(name: str) -> str:
    """Get full details of a single Instagram DM activity by its ID.

    Args:
        name: The Instagram activity ID (e.g. 'ACT00123' or the 'name' field from list_instagram_chats).
    """
    return await _get_channel_record("activitiesIgdm", "Instagram chat", name, channel="instagram")


@mcp.tool()
async def get_whatsapp_chat(name: str) -> str:
    """Get full details of a single WhatsApp activity by its ID.

    Args:
        name: The WhatsApp activity ID (e.g. 'ACT00123' or the 'name' field from list_whatsapp_chats).
    """
    return await _get_channel_record("activitiesWap", "WhatsApp chat", name)


@mcp.tool()
async def get_viber_chat(name: str) -> str:
    """Get full details of a single Viber activity by its ID.

    Args:
        name: The Viber activity ID (e.g. 'ACT00123' or the 'name' field from list_viber_chats).
    """
    return await _get_channel_record("activitiesVbr", "Viber chat", name)


@mcp.tool()
async def list_emails(
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    direction: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List email activities with email-specific fields (subject, address, state).
    Use this instead of list_activities(type='EMAIL') when you need email details.

    Args:
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        direction: Filter by direction: in (incoming) or out (outgoing).
        date_from: Filter by email start time on or after this date (YYYY-MM-DD).
        date_to: Filter by email start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: time (email time), duration, wait_time.
            WARNING: only email-specific fields work — do NOT use 'created' or 'edited'.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort("activitiesEmail", sort)
    direction = direction.lower() if direction else None
    async with _get_client() as client:
        if user:
            user, _ = await _resolve_user(client, user)

        filters: list[tuple[str, str, str]] = []
        if queue:
            filters.append(("queue", "eq", queue))
        if user:
            filters.append(("user", "eq", user))
        if contact:
            filters.append(("contact", "eq", contact))
        if direction:
            filters.append(("direction", "eq", direction))
        filters.extend(_date_filters("time", date_from, date_to))

        result = await client.list(
            "activitiesEmail",
            field_filters=filters or None,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
            # Exclude heavy nested objects: activities (198 KB), contact per
            # record — 221 KB → 27 KB each. Use get_email for full details.
            fields=[
                "name", "queue", "user", "title", "address",
                "direction", "wait_time", "duration", "answered",
                "text", "time", "state",
            ],
        )
    return format_email_list(result["data"], result["total"], skip, take, base_url=_get_base_url())


@mcp.tool()
async def list_web_chats(
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List web chat activities with chat-specific fields (state, disconnection, missed).

    Args:
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        date_from: Filter by activity start time on or after this date (YYYY-MM-DD).
        date_to: Filter by activity start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: time, duration, wait_time.
            WARNING: only fields that exist on this endpoint work — do NOT use 'created' or 'edited'.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    return await _list_channel_chats(
        "activitiesWeb", "web chats",
        queue=queue, user=user, contact=contact,
        date_from=date_from, date_to=date_to,
        sort=sort, sort_dir=sort_dir, skip=skip, take=take,
    )


@mcp.tool()
async def list_sms_chats(
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    direction: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List SMS activities with SMS-specific fields (sender phone, direction, state).

    Args:
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        direction: Filter by direction: IN or OUT.
        date_from: Filter by activity start time on or after this date (YYYY-MM-DD).
        date_to: Filter by activity start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: time, duration, wait_time.
            WARNING: only fields that exist on this endpoint work — do NOT use 'created' or 'edited'.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    return await _list_channel_chats(
        "activitiesSms", "SMS chats",
        queue=queue, user=user, contact=contact, direction=direction,
        date_from=date_from, date_to=date_to,
        sort=sort, sort_dir=sort_dir, skip=skip, take=take,
    )


@mcp.tool()
async def list_messenger_chats(
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    direction: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List Facebook Messenger activities with channel-specific fields.

    Args:
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        direction: Filter by direction: IN or OUT.
        date_from: Filter by activity start time on or after this date (YYYY-MM-DD).
        date_to: Filter by activity start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: time, duration, wait_time.
            WARNING: only fields that exist on this endpoint work — do NOT use 'created' or 'edited'.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    return await _list_channel_chats(
        "activitiesFbm", "Messenger chats",
        queue=queue, user=user, contact=contact, direction=direction,
        date_from=date_from, date_to=date_to,
        sort=sort, sort_dir=sort_dir, skip=skip, take=take,
    )


@mcp.tool()
async def list_instagram_chats(
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    direction: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List Instagram DM activities with channel-specific fields (type: DM/STORY_REPLY/STORY_MENTION).

    Args:
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        direction: Filter by direction: IN or OUT.
        date_from: Filter by activity start time on or after this date (YYYY-MM-DD).
        date_to: Filter by activity start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: time, duration, wait_time.
            WARNING: only fields that exist on this endpoint work — do NOT use 'created' or 'edited'.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    return await _list_channel_chats(
        "activitiesIgdm", "Instagram chats", channel="instagram",
        queue=queue, user=user, contact=contact, direction=direction,
        date_from=date_from, date_to=date_to,
        sort=sort, sort_dir=sort_dir, skip=skip, take=take,
    )


@mcp.tool()
async def list_whatsapp_chats(
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    direction: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List WhatsApp activities with channel-specific fields.

    Args:
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        direction: Filter by direction: IN or OUT.
        date_from: Filter by activity start time on or after this date (YYYY-MM-DD).
        date_to: Filter by activity start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: time, duration, wait_time.
            WARNING: only fields that exist on this endpoint work — do NOT use 'created' or 'edited'.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    return await _list_channel_chats(
        "activitiesWap", "WhatsApp chats",
        queue=queue, user=user, contact=contact, direction=direction,
        date_from=date_from, date_to=date_to,
        sort=sort, sort_dir=sort_dir, skip=skip, take=take,
    )


@mcp.tool()
async def list_viber_chats(
    queue: str | None = None,
    user: str | None = None,
    contact: str | None = None,
    direction: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List Viber activities with channel-specific fields.

    Args:
        queue: Filter by queue internal name (e.g. '10333'). Use list_queues to find names.
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        direction: Filter by direction: IN or OUT.
        date_from: Filter by activity start time on or after this date (YYYY-MM-DD).
        date_to: Filter by activity start time on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: time, duration, wait_time.
            WARNING: only fields that exist on this endpoint work — do NOT use 'created' or 'edited'.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    return await _list_channel_chats(
        "activitiesVbr", "Viber chats",
        queue=queue, user=user, contact=contact, direction=direction,
        date_from=date_from, date_to=date_to,
        sort=sort, sort_dir=sort_dir, skip=skip, take=take,
    )


# ---------------------------------------------------------------------------
# Contact tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_contacts(
    search: str | None = None,
    account: str | None = None,
    skip: int = 0,
    take: int = 50,
) -> str:
    """Search and list contacts. Each contact has firstname, lastname, title (full name), email, phone number.

    Args:
        search: Search by full name (partial match, e.g. 'John' or 'Smith'). Searches the 'title' field.
        account: Filter by account internal ID (e.g. 'account_674eda46162a8403430453').
            NOT a company name — call list_accounts(search='...') first to find the ID.
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    filters: list[tuple[str, str, str]] = []
    if search:
        filters.append(("title", "like", search))
    if account:
        filters.append(("account", "eq", account))

    async with _get_client() as client:
        result = await client.list(
            "contacts",
            field_filters=filters or None,
            skip=skip,
            take=take,
        )
    return format_contact_list(result["data"], result["total"], skip, take, base_url=_get_base_url())


@mcp.tool()
async def get_contact(name: str) -> str:
    """Get full details of a single contact by its ID. Use this when you already know the contact ID.

    Args:
        name: The contact ID (the 'name' field from list_contacts, e.g. CT00123).
    """
    async with _get_client() as client:
        record = await client.get("contacts", name)
    if record is None:
        return f"Contact '{name}' not found."
    return format_contact(record, base_url=_get_base_url())


# ---------------------------------------------------------------------------
# Account tools (CRM companies/organizations)
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_accounts(
    user: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "edited",
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List accounts (companies/organizations). Contacts belong to accounts.

    Args:
        user: Filter by account owner login name (e.g. 'john.doe'). Use list_users to find login names.
        search: Search by company name (partial match, e.g. 'Notino' or 'Siemens').
        date_from: Filter accounts created on or after this date (YYYY-MM-DD).
        date_to: Filter accounts created on or before this date (YYYY-MM-DD).
        sort: Field to sort by (default: edited).
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort("accounts", sort)
    async with _get_client() as client:
        if user:
            user, _ = await _resolve_user(client, user)

        filters: list[tuple[str, str, str]] = []
        if user:
            filters.append(("user", "eq", user))
        if search:
            filters.append(("title", "like", search))
        filters.extend(_date_filters("created", date_from, date_to))

        result = await client.list(
            "accounts",
            field_filters=filters or None,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
            # Exclude nested blobs — single account is 98 KB raw.
            fields=[
                "name", "title", "user", "description", "sla",
                "created", "edited",
            ],
        )
    return format_account_list(result["data"], result["total"], skip, take, base_url=_get_base_url())


@mcp.tool()
async def get_account(name: str) -> str:
    """Get full details of a single account by its internal ID.

    Args:
        name: The account internal ID (e.g. 'account_674eda46162a8403430453').
            Use list_accounts(search='...') to find the ID from a company name.
    """
    async with _get_client() as client:
        record = await client.get("accounts", name)
    if record is None:
        return f"Account '{name}' not found."
    return format_account(record, base_url=_get_base_url(), detail=True)


# ---------------------------------------------------------------------------
# CRM record tools (deals/opportunities)
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_crm_records(
    user: str | None = None,
    contact: str | None = None,
    account: str | None = None,
    stage: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "edited",
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List CRM records (deals, opportunities, or other CRM entities).

    Args:
        user: Filter by owner login name (e.g. 'john.doe'). Use list_users to find login names.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        account: Filter by account internal ID (e.g. 'account_674eda46162a8403430453').
            NOT a company name — call list_accounts(search='...') first to find the ID.
        stage: Filter by stage: OPEN or CLOSE.
        date_from: Filter records created on or after this date (YYYY-MM-DD).
        date_to: Filter records created on or before this date (YYYY-MM-DD).
        sort: Field to sort by (default: edited).
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort("crmRecords", sort)
    async with _get_client() as client:
        if user:
            user, _ = await _resolve_user(client, user)

        filters: list[tuple[str, str, str]] = []
        if user:
            filters.append(("user", "eq", user))
        if contact:
            filters.append(("contact", "eq", contact))
        if account:
            filters.append(("account", "eq", account))
        if stage:
            filters.append(("stage", "eq", stage))
        filters.extend(_date_filters("created", date_from, date_to))

        result = await client.list(
            "crmRecords",
            field_filters=filters or None,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
        )
    return format_crm_record_list(result["data"], result["total"], skip, take, base_url=_get_base_url())


# ---------------------------------------------------------------------------
# Campaign tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_campaign_records(
    user: str | None = None,
    contact: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str | None = None,
    sort_dir: str = "desc",
    skip: int = 0,
    take: int = 50,
) -> str:
    """List campaign records (outbound campaign activity — calls made, results).

    Args:
        user: Agent name — pass either a display name (e.g. 'John Doe') or login name
            (e.g. 'john.doe'). Resolved automatically.
        contact: Filter by contact internal ID (e.g. 'contact_674eda46162a8403430453').
            NOT a person's name — call list_contacts(search='...') first to find the ID.
        date_from: Filter records created on or after this date (YYYY-MM-DD).
        date_to: Filter records created on or before this date (YYYY-MM-DD).
        sort: Field to sort by. Useful values: created, edited, nextcall.
        sort_dir: Sort direction: asc or desc (default: desc).
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 50, max: 200).
    """
    take = min(take, _MAX_TAKE_DATA)
    sort = _validated_sort("campaignsRecords", sort)
    async with _get_client() as client:
        if user:
            user, _ = await _resolve_user(client, user)

        filters: list[tuple[str, str, str]] = []
        if user:
            filters.append(("user", "eq", user))
        if contact:
            filters.append(("contact", "eq", contact))
        filters.extend(_date_filters("created", date_from, date_to))

        result = await client.list(
            "campaignsRecords",
            field_filters=filters or None,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
        )
    return format_campaign_record_list(result["data"], result["total"], skip, take)


@mcp.tool()
async def list_campaign_types(
    skip: int = 0,
    take: int = 200,
) -> str:
    """List all campaign types (reference data for outbound campaigns).

    Args:
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 200).
    """
    async with _get_client() as client:
        result = await client.list("campaignsTypes", skip=skip, take=take)
    return format_simple_list(result["data"], result["total"], skip, take, "campaign types")


# ---------------------------------------------------------------------------
# Configuration / reference data tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_queues(
    skip: int = 0,
    take: int = 1000,
) -> str:
    """List all queues. The 'name' field of each queue is used as the 'queue' filter in list_activities.
    Queue types include: in (inbound calls), out (outbound calls), email, chat, sms, fbm, wap, vbr, etc.

    Args:
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 1000).
    """
    async with _get_client() as client:
        result = await client.list("queues", skip=skip, take=take)
    return format_simple_list(result["data"], result["total"], skip, take, "queues")


@mcp.tool()
async def list_users(
    search: str | None = None,
    skip: int = 0,
    take: int = 200,
) -> str:
    """List or search agents/users. The 'name' field is the login name, 'title' is the display name.

    NOTE: Most tools (list_tickets, count_tickets, list_activities, etc.) resolve agent names
    automatically — you do NOT need to call list_users first. Use this tool only when you need
    to browse the user directory or look up a specific agent's details.

    Args:
        search: Search by agent display name (partial match, e.g. 'John Doe' or 'Hajek').
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 200).
    """
    async with _get_client() as client:
        filters = None
        if search:
            filters = [("title", "like", search)]
        result = await client.list(
            "users", field_filters=filters, skip=skip, take=take,
        )
    return format_simple_list(result["data"], result["total"], skip, take, "users")


@mcp.tool()
async def list_groups(
    skip: int = 0,
    take: int = 200,
) -> str:
    """List all groups (used to organize categories, queues, users, or profiles).

    Args:
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 200).
    """
    async with _get_client() as client:
        result = await client.list("groups", skip=skip, take=take)
    return format_simple_list(result["data"], result["total"], skip, take, "groups")


@mcp.tool()
async def list_pauses(
    skip: int = 0,
    take: int = 200,
) -> str:
    """List all pause types available to agents (break reasons like wrap-up, DND, etc.).

    Args:
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 200).
    """
    async with _get_client() as client:
        result = await client.list("pauses", skip=skip, take=take)
    return format_simple_list(result["data"], result["total"], skip, take, "pauses")


@mcp.tool()
async def list_statuses(
    skip: int = 0,
    take: int = 200,
) -> str:
    """List all ticket/record statuses (reference data with name, title, color).

    Args:
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 200).
    """
    async with _get_client() as client:
        result = await client.list("statuses", skip=skip, take=take)
    return format_simple_list(result["data"], result["total"], skip, take, "statuses")


@mcp.tool()
async def list_templates(
    skip: int = 0,
    take: int = 200,
) -> str:
    """List all message templates (for email, SMS, chat, WhatsApp, etc.).

    Args:
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 200).
    """
    async with _get_client() as client:
        result = await client.list("templates", skip=skip, take=take)
    return format_simple_list(result["data"], result["total"], skip, take, "templates")


# ---------------------------------------------------------------------------
# Realtime tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_realtime_sessions(
    skip: int = 0,
    take: int = 200,
) -> str:
    """List currently active agent sessions (real-time snapshot).
    Shows which agents are online, their state (Idle/Paused/Session), extension, and pause reason.

    Args:
        skip: Pagination offset (default: 0).
        take: Number of records to return (default: 200).
    """
    async with _get_client() as client:
        result = await client.list("realtimeSessions", skip=skip, take=take)
    return format_realtime_session_list(result["data"], result["total"], skip, take)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
