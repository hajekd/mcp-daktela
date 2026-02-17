# mcp-daktela

Read-only [MCP](https://modelcontextprotocol.io/) server for the [Daktela](https://www.daktela.com/) contact center REST API v6. Gives any MCP-compatible LLM client (Claude, Cursor, etc.) full read access to tickets, calls, emails, chats, contacts, CRM records, campaigns, and real-time agent status.

## Why

A contact center generates thousands of interactions daily — calls, emails, chats across multiple channels. The raw data is all in Daktela, but extracting insight from it requires either manual review or custom reporting. This server bridges Daktela to an LLM, letting you run analysis that would be impractical to do by hand:

**Email quality audit** — "Analyze all emails from the last 72 hours. Flag any interactions with negative customer sentiment, lost deals where the customer chose a competitor, or unprofessional agent tone. For each flagged email, show metadata, a link to the ticket, and a description of the issue."

**Call transcript analysis** — "Review call transcripts from the last week. Identify calls where the customer escalated, the agent struggled with product knowledge, or a commitment was made but not followed up. Summarize each with the agent name, customer, and recommended action."

**Sales pipeline review** — "Look at all open sales tickets in S1-Discovery and S2-Qualification stages. For each lead, read the latest email thread and assess whether the deal is progressing, stalled, or at risk. Rank by MRR and recommend which ones need attention this week."

The LLM reads the actual conversation content — email bodies, chat messages, call transcripts — and applies judgment that no dashboard or filter can replicate.

## Tools

40 read-only tools organized by domain:

| Category | Tools |
|---|---|
| **Tickets** | `list_tickets`, `count_tickets`, `get_ticket`, `get_ticket_detail`, `list_account_tickets`, `list_ticket_categories` |
| **Activities** | `list_activities`, `get_activity` |
| **Calls** | `list_calls`, `get_call`, `get_call_transcript`, `list_call_transcripts` |
| **Emails** | `list_emails`, `get_email` |
| **Messaging** | `list_web_chats`, `get_web_chat`, `list_sms_chats`, `get_sms`, `list_messenger_chats`, `get_messenger_chat`, `list_instagram_chats`, `get_instagram_chat`, `list_whatsapp_chats`, `get_whatsapp_chat`, `list_viber_chats`, `get_viber_chat` |
| **Contacts & CRM** | `list_contacts`, `get_contact`, `list_accounts`, `get_account`, `list_crm_records` |
| **Campaigns** | `list_campaign_records`, `list_campaign_types` |
| **Reference data** | `list_queues`, `list_users`, `list_groups`, `list_pauses`, `list_statuses`, `list_templates` |
| **Real-time** | `list_realtime_sessions` |

All list tools support pagination (`skip`, `take`), sorting, and contextual filters (stage, priority, date range, user, queue, etc.). The server includes detailed `instructions` metadata that teaches the LLM how to use filters, resolve entity names, and navigate relationships between tickets, contacts, and accounts.

## Getting started

### Prerequisites

- Python 3.12+
- A Daktela instance with a user account that has API access
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install

```bash
git clone https://github.com/hajekd/mcp-daktela.git
cd mcp-daktela
uv venv && uv pip install -e ".[dev]"
```

### Run locally with Claude Desktop

Set your Daktela credentials and point Claude Desktop at the server:

```json
{
  "mcpServers": {
    "daktela": {
      "command": "python",
      "args": ["-m", "mcp_daktela"],
      "env": {
        "DAKTELA_URL": "https://your-instance.daktela.com",
        "DAKTELA_USERNAME": "your-username",
        "DAKTELA_PASSWORD": "your-password"
      }
    }
  }
}
```

That's it. The server authenticates against your Daktela instance using the same credentials you use to log in. You can also use `DAKTELA_ACCESS_TOKEN` instead of username/password if you have a static API token.

### Deploy as HTTP server

For shared or remote deployments (e.g., Cloud Run), the server runs in streamable-http mode where each client passes credentials via HTTP headers:

```bash
gcloud run deploy mcp-daktela \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --memory 1Gi
```

The server also includes a built-in OAuth 2.0 provider for use as a remote MCP server on Claude.ai.

## Architecture

```
src/mcp_daktela/
├── server.py              MCP tool definitions (40 tools)
├── formatting.py          Format API records into readable markdown
├── client.py              Async HTTP client for Daktela REST API
├── filters.py             Build query parameters (filter/sort/pagination)
├── oauth.py               OAuth 2.0 provider for Claude.ai remote MCP
├── auth.py                Per-request credential middleware
├── config.py              Credential resolution (ContextVar → env vars)
├── cache.py               In-process TTL cache for reference data
├── logging_middleware.py   Structured JSON logging for tool calls
└── __main__.py            Entry point
```

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `DAKTELA_URL` | — | Daktela instance URL |
| `DAKTELA_USERNAME` | — | Daktela username |
| `DAKTELA_PASSWORD` | — | Daktela password |
| `DAKTELA_ACCESS_TOKEN` | — | Static API token (alternative to username/password) |
| `MCP_TRANSPORT` | `stdio` | Transport: `stdio` or `streamable-http` |
| `PORT` | `8080` | HTTP port (streamable-http mode) |
| `CACHE_ENABLED` | `true` | Enable reference data cache |
| `CACHE_TTL_SECONDS` | `3600` | Cache TTL in seconds |

## Development

```bash
# Unit tests (333 tests, ~1s)
.venv/bin/python -m pytest

# Lint
.venv/bin/python -m ruff check src/ tests/
```

Integration tests run every tool against a live Daktela instance via the deployed server:

```bash
.venv/bin/python scripts/integration_test.py \
  --url https://your-instance.daktela.com \
  --username your-user \
  --password your-password
```

## License

MIT
