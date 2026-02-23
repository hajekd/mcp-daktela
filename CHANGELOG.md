# Changelog

## 1.1.0

### New features

- **Server-side AI scanning** (`scan_calls`, `scan_emails`): Score large volumes of calls and emails server-side using configurable LLM providers (OpenRouter or Anthropic). Paginated with 100 records/page; Claude calls remaining pages in parallel. Ideal for quality review, escalation detection, and agent coaching.
- **Knowledge base tools** (`list_article_folders`, `list_articles`, `get_article`): Browse and search Daktela knowledge base articles. HTML content is converted to Markdown for clean display.
- **Client search parameter**: `client.list()` now supports a `search` keyword for Daktela's global search (`?q=`).
- **Email body cleaning**: Strip reply chains, signatures, and HTML boilerplate from email bodies for cleaner display in list views.
- **Drill-down workflow guidance**: Instructions now guide Claude through the scan result → transcript → ticket → account investigation chain.

### Bug fixes

- **OAuth token expiry**: `_parse_daktela_datetime()` now correctly treats Daktela timestamps as Europe/Prague (CET/CEST) instead of UTC. Previously the JWT `exp` was set 1 hour too late, causing tokens to expire before the MCP client triggered a refresh.
- **Proactive refresh buffer**: Widened from 5 minutes to 10 minutes as defense-in-depth against delayed refresh scheduling.
- **Scorer error messages**: Generic `"Scoring temporarily unavailable"` returned to clients instead of leaking exception type names.

### Dependencies

- Added `anthropic>=0.40` (Anthropic scoring provider)
- Added `markdownify>=0.13` (HTML-to-Markdown for KB articles)

## 1.0.1

- Fix `date_to` filter: bare date now includes full day (appends `23:59:59`)
- Fix OAuth token refresh: validate JWT at HTTP level, add `expires_in` buffer

## 1.0.0

- Initial release: read-only MCP server for Daktela REST API v6
- 42 tools: tickets, activities, calls, emails, chats, contacts, accounts, CRM, campaigns, realtime
- OAuth 2.0 + header-based auth, deployed on Cloud Run
