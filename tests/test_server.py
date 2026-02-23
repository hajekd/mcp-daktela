"""Tests for MCP server tool functions."""

from unittest.mock import AsyncMock, patch

import pytest

from mcp_daktela import server
from mcp_daktela.server import _date_filters


class TestDateFilters:
    def test_bare_date_to_gets_end_of_day(self):
        filters = _date_filters("time", None, "2026-02-17")
        assert filters == [("time", "lte", "2026-02-17 23:59:59")]

    def test_bare_date_from_unchanged(self):
        filters = _date_filters("time", "2026-02-17", None)
        assert filters == [("time", "gte", "2026-02-17")]

    def test_datetime_to_unchanged(self):
        filters = _date_filters("time", None, "2026-02-17 12:00:00")
        assert filters == [("time", "lte", "2026-02-17 12:00:00")]

    def test_iso8601_t_separator_normalized(self):
        filters = _date_filters("time", "2026-02-17T00:00:00", "2026-02-17T23:59:59")
        assert filters == [
            ("time", "gte", "2026-02-17 00:00:00"),
            ("time", "lte", "2026-02-17 23:59:59"),
        ]

    def test_both_none_returns_empty(self):
        assert _date_filters("time", None, None) == []

MOCK_CLIENT_PATH = "mcp_daktela.server._get_client"


def _make_mock_client(list_result=None, get_result=None):
    client = AsyncMock()
    client.list.return_value = list_result or {"data": [], "total": 0}
    client.get.return_value = get_result
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# Access the underlying async functions via .fn on the FunctionTool objects
_list_tickets = server.list_tickets.fn
_count_tickets = server.count_tickets.fn
_get_ticket = server.get_ticket.fn
_list_account_tickets = server.list_account_tickets.fn
_list_ticket_categories = server.list_ticket_categories.fn
_list_activities = server.list_activities.fn
_get_activity = server.get_activity.fn
_list_calls = server.list_calls.fn
_get_call = server.get_call.fn
_list_emails = server.list_emails.fn
_list_web_chats = server.list_web_chats.fn
_list_sms_chats = server.list_sms_chats.fn
_list_messenger_chats = server.list_messenger_chats.fn
_list_instagram_chats = server.list_instagram_chats.fn
_list_whatsapp_chats = server.list_whatsapp_chats.fn
_list_viber_chats = server.list_viber_chats.fn
_list_contacts = server.list_contacts.fn
_get_contact = server.get_contact.fn
_list_accounts = server.list_accounts.fn
_get_account = server.get_account.fn
_list_crm_records = server.list_crm_records.fn
_list_campaign_records = server.list_campaign_records.fn
_list_campaign_types = server.list_campaign_types.fn
_list_queues = server.list_queues.fn
_list_users = server.list_users.fn
_list_groups = server.list_groups.fn
_list_pauses = server.list_pauses.fn
_list_statuses = server.list_statuses.fn
_list_templates = server.list_templates.fn
_get_email = server.get_email.fn
_get_web_chat = server.get_web_chat.fn
_get_sms = server.get_sms.fn
_get_messenger_chat = server.get_messenger_chat.fn
_get_instagram_chat = server.get_instagram_chat.fn
_get_whatsapp_chat = server.get_whatsapp_chat.fn
_get_viber_chat = server.get_viber_chat.fn
_get_ticket_detail = server.get_ticket_detail.fn
_get_call_transcript = server.get_call_transcript.fn
_list_call_transcripts = server.list_call_transcripts.fn
_list_realtime_sessions = server.list_realtime_sessions.fn
_list_article_folders = server.list_article_folders.fn
_list_articles = server.list_articles.fn
_get_article = server.get_article.fn


class TestListTickets:
    async def test_returns_formatted_output(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "TK001", "title": "Test"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_tickets()

        assert "TK001" in result
        assert "Test" in result
        client.list.assert_called_once()

    async def test_passes_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_tickets(category="Sales", stage="OPEN")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("category", "eq", "Sales") in filters
        assert ("stage", "eq", "OPEN") in filters

    async def test_passes_date_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_tickets(date_from="2024-01-01", date_to="2024-01-31")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("created", "gte", "2024-01-01") in filters
        assert ("created", "lte", "2024-01-31 23:59:59") in filters

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_tickets()

        assert "No tickets found" in result

    async def test_passes_search_filter(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_tickets(search="refund")

        call_kwargs = client.list.call_args[1]
        assert ("title", "like", "refund") in call_kwargs["field_filters"]

    async def test_excludes_merged_by_default(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_tickets(stage="OPEN")

        call_kwargs = client.list.call_args[1]
        assert ("id_merge", "isnull", "true") in call_kwargs["field_filters"]

    async def test_include_merged_skips_filter(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_tickets(stage="OPEN", include_merged=True)

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        merge_filters = [f for f in filters if f[0] == "id_merge"]
        assert len(merge_filters) == 0


class TestCountTickets:
    async def test_returns_count(self):
        client = _make_mock_client(list_result={"data": [], "total": 42})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _count_tickets(category="Sales")

        assert "42" in result
        assert "Sales" in result

    async def test_uses_minimal_payload(self):
        client = _make_mock_client(list_result={"data": [], "total": 0})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _count_tickets()

        call_kwargs = client.list.call_args[1]
        assert call_kwargs["take"] == 1
        assert call_kwargs["fields"] == ["name"]

    async def test_no_filters(self):
        client = _make_mock_client(list_result={"data": [], "total": 100})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _count_tickets()

        assert "100" in result
        assert "Total tickets" in result

    async def test_passes_search_filter(self):
        client = _make_mock_client(list_result={"data": [], "total": 3})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _count_tickets(search="refund")

        call_kwargs = client.list.call_args[1]
        assert ("title", "like", "refund") in call_kwargs["field_filters"]
        assert "refund" in result

    async def test_excludes_merged_by_default(self):
        client = _make_mock_client(list_result={"data": [], "total": 5})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _count_tickets(stage="OPEN")

        call_kwargs = client.list.call_args[1]
        assert ("id_merge", "isnull", "true") in call_kwargs["field_filters"]

    async def test_include_merged_includes_all(self):
        client = _make_mock_client(list_result={"data": [], "total": 21})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _count_tickets(stage="OPEN", include_merged=True)

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        merge_filters = [f for f in filters if f[0] == "id_merge"]
        assert len(merge_filters) == 0


class TestGetTicket:
    async def test_found(self):
        client = _make_mock_client(get_result={
            "name": "TK001",
            "title": "Test ticket",
            "stage": "OPEN",
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_ticket(name="TK001")

        assert "TK001" in result
        assert "Test ticket" in result

    async def test_not_found(self):
        client = _make_mock_client(get_result=None)
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_ticket(name="NONEXISTENT")

        assert "not found" in result


class TestListAccountTickets:
    async def test_resolves_exact_account_id_and_returns_tickets(self):
        """When account ID is exact, get() finds it, then contacts → tickets."""
        call_count = 0

        async def list_side_effect(endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if endpoint == "contacts":
                return {"data": [{"name": "CT001"}], "total": 1}
            if endpoint == "tickets":
                return {"data": [{"name": "TK001", "title": "Issue"}], "total": 1}
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result={"name": "ACC001", "title": "Notino"})
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_account_tickets(account="ACC001")

        assert "TK001" in result
        assert "Notino" in result
        # Should have called get("accounts", "ACC001") first
        client.get.assert_called_once_with("accounts", "ACC001")

    async def test_fuzzy_search_by_company_name(self):
        """When exact ID not found, searches by title then uses contacts."""
        call_count = 0

        async def list_side_effect(endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if endpoint == "accounts":
                return {"data": [{"name": "ACC042", "title": "Notino, s.r.o."}], "total": 1}
            if endpoint == "contacts":
                return {"data": [{"name": "CT001"}, {"name": "CT002"}], "total": 2}
            if endpoint == "tickets":
                return {"data": [{"name": "TK001", "title": "Ticket A"}], "total": 1}
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result=None)  # exact lookup fails
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_account_tickets(account="Notino")

        assert "TK001" in result
        assert "Notino, s.r.o." in result

    async def test_passes_stage_filter_to_ticket_queries(self):
        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "contacts":
                return {"data": [{"name": "CT001"}], "total": 1}
            if endpoint == "tickets":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result={"name": "ACC001", "title": "Test"})
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_account_tickets(account="ACC001", stage="OPEN")

        # Find the tickets call and verify stage + contact 'in' filters
        for call in client.list.call_args_list:
            if call[0][0] == "tickets":
                filters = call[1].get("field_filters", [])
                assert ("stage", "eq", "OPEN") in filters
                assert ("contact", "in", ["CT001"]) in filters

    async def test_defaults_to_open_stage(self):
        """When stage is not specified, it defaults to OPEN."""
        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "contacts":
                return {"data": [{"name": "CT001"}], "total": 1}
            if endpoint == "tickets":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result={"name": "ACC001", "title": "Test"})
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_account_tickets(account="ACC001")

        for call in client.list.call_args_list:
            if call[0][0] == "tickets":
                filters = call[1].get("field_filters", [])
                assert ("stage", "eq", "OPEN") in filters

    async def test_stage_all_skips_stage_filter(self):
        """Passing stage='ALL' should not add any stage filter."""
        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "contacts":
                return {"data": [{"name": "CT001"}], "total": 1}
            if endpoint == "tickets":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result={"name": "ACC001", "title": "Test"})
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_account_tickets(account="ACC001", stage="ALL")

        for call in client.list.call_args_list:
            if call[0][0] == "tickets":
                filters = call[1].get("field_filters", [])
                stage_filters = [f for f in filters if f[0] == "stage"]
                assert len(stage_filters) == 0

    async def test_excludes_merged_by_default(self):
        """By default, merged tickets should be excluded."""
        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "contacts":
                return {"data": [{"name": "CT001"}], "total": 1}
            if endpoint == "tickets":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result={"name": "ACC001", "title": "Test"})
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_account_tickets(account="ACC001")

        for call in client.list.call_args_list:
            if call[0][0] == "tickets":
                filters = call[1].get("field_filters", [])
                assert ("id_merge", "isnull", "true") in filters

    async def test_include_merged_skips_filter(self):
        """Passing include_merged=True should not add the id_merge filter."""
        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "contacts":
                return {"data": [{"name": "CT001"}], "total": 1}
            if endpoint == "tickets":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result={"name": "ACC001", "title": "Test"})
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_account_tickets(account="ACC001", include_merged=True)

        for call in client.list.call_args_list:
            if call[0][0] == "tickets":
                filters = call[1].get("field_filters", [])
                merge_filters = [f for f in filters if f[0] == "id_merge"]
                assert len(merge_filters) == 0

    async def test_no_contacts_returns_message(self):
        async def list_side_effect(endpoint, **kwargs):
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result={"name": "ACC001", "title": "Empty Co"})
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_account_tickets(account="ACC001")

        assert "No contacts" in result

    async def test_no_account_found(self):
        async def list_side_effect(endpoint, **kwargs):
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result=None)
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_account_tickets(account="UnknownCo")

        assert "No account found" in result

    async def test_deduplicates_tickets_across_contacts(self):
        """Same ticket linked to multiple contacts should appear only once."""
        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "contacts":
                return {"data": [{"name": "CT001"}, {"name": "CT002"}], "total": 2}
            if endpoint == "tickets":
                # Both contacts return the same ticket
                return {"data": [{"name": "TK001", "title": "Shared ticket"}], "total": 1}
            return {"data": [], "total": 0}

        client = _make_mock_client(get_result={"name": "ACC001", "title": "Test"})
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_account_tickets(account="ACC001")

        # "Shared ticket" should appear only once despite being returned for 2 contacts
        assert result.count("Shared ticket") == 1


class TestListTicketCategories:
    async def test_returns_categories(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "sales", "title": "Sales"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_ticket_categories()

        assert "sales" in result
        client.list.assert_called_once_with("ticketsCategories", skip=0, take=200)


class TestListActivities:
    async def test_with_type_filter(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_activities(type="CALL")

        call_kwargs = client.list.call_args[1]
        assert ("type", "eq", "CALL") in call_kwargs["field_filters"]


class TestGetActivity:
    async def test_found(self):
        client = _make_mock_client(get_result={
            "name": "ACT001",
            "title": "Inbound call",
            "type": "CALL",
            "direction": "in",
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_activity(name="ACT001")

        assert "ACT001" in result
        client.get.assert_called_once_with("activities", "ACT001")

    async def test_not_found(self):
        client = _make_mock_client(get_result=None)
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_activity(name="NONEXISTENT")

        assert "not found" in result


class TestListCalls:
    async def test_returns_formatted_output(self):
        client = _make_mock_client(list_result={
            "data": [{"id_call": "CALL001", "direction": "in", "answered": True, "clid": "+420123"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_calls()

        assert "CALL001" in result
        assert "in" in result

    async def test_passes_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_calls(direction="in", user="john", answered=True)

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("direction", "eq", "in") in filters
        assert ("id_agent", "eq", "john") in filters
        assert ("answered", "eq", "true") in filters

    async def test_passes_queue_and_date_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_calls(queue="10333", date_from="2026-02-08", date_to="2026-02-15")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("id_queue", "eq", "10333") in filters
        assert ("call_time", "gte", "2026-02-08") in filters
        assert ("call_time", "lte", "2026-02-15 23:59:59") in filters

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_calls()

        assert "No calls found" in result

    async def test_uses_correct_endpoint(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_calls()

        assert client.list.call_args[0][0] == "activitiesCall"


class TestListEmails:
    async def test_returns_formatted_output(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "EM001", "title": "Re: Hello", "direction": "in"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_emails()

        assert "EM001" in result
        assert "Re: Hello" in result

    async def test_passes_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_emails(direction="out", queue="email_q")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("direction", "eq", "out") in filters
        assert ("queue", "eq", "email_q") in filters

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_emails()

        assert "No emails found" in result

    async def test_uses_correct_endpoint(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_emails()

        assert client.list.call_args[0][0] == "activitiesEmail"


_CHAT_CHANNELS = [
    # (tool_fn, endpoint, record_name, entity_label, has_direction)
    (_list_web_chats, "activitiesWeb", "WEB001", "web chats", False),
    (_list_sms_chats, "activitiesSms", "SMS001", "SMS chats", True),
    (_list_messenger_chats, "activitiesFbm", "FBM001", "Messenger chats", True),
    (_list_instagram_chats, "activitiesIgdm", "IG001", "Instagram chats", True),
    (_list_whatsapp_chats, "activitiesWap", "WAP001", "WhatsApp chats", True),
    (_list_viber_chats, "activitiesVbr", "VBR001", "Viber chats", True),
]


class TestListChannelChats:
    @pytest.mark.parametrize("tool_fn,endpoint,record_name,entity,has_dir", _CHAT_CHANNELS)
    async def test_returns_formatted_output(self, tool_fn, endpoint, record_name, entity, has_dir):
        client = _make_mock_client(list_result={
            "data": [{"name": record_name, "title": "Chat session"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await tool_fn()
        assert record_name in result

    @pytest.mark.parametrize("tool_fn,endpoint,record_name,entity,has_dir", _CHAT_CHANNELS)
    async def test_passes_user_and_date_filters(self, tool_fn, endpoint, record_name, entity, has_dir):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await tool_fn(user="agent1", date_from="2024-01-01")
        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("user", "eq", "agent1") in filters
        assert ("time", "gte", "2024-01-01") in filters

    @pytest.mark.parametrize("tool_fn,endpoint,record_name,entity,has_dir",
                             [c for c in _CHAT_CHANNELS if c[4]])
    async def test_passes_direction_filter(self, tool_fn, endpoint, record_name, entity, has_dir):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await tool_fn(direction="IN")
        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("direction", "eq", "IN") in filters

    @pytest.mark.parametrize("tool_fn,endpoint,record_name,entity,has_dir", _CHAT_CHANNELS)
    async def test_empty_result(self, tool_fn, endpoint, record_name, entity, has_dir):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await tool_fn()
        assert f"No {entity} found" in result

    @pytest.mark.parametrize("tool_fn,endpoint,record_name,entity,has_dir", _CHAT_CHANNELS)
    async def test_uses_correct_endpoint(self, tool_fn, endpoint, record_name, entity, has_dir):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await tool_fn()
        assert client.list.call_args[0][0] == endpoint


class TestListContacts:
    async def test_with_search(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_contacts(search="John")

        call_kwargs = client.list.call_args[1]
        assert ("title", "like", "John") in call_kwargs["field_filters"]


class TestGetContact:
    async def test_found(self):
        client = _make_mock_client(get_result={
            "name": "CT001",
            "title": "Doe",
            "firstname": "John",
            "email": "john.doe@example.com",
            "number": "+420123456789",
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_contact(name="CT001")

        assert "CT001" in result
        assert "John" in result
        client.get.assert_called_once_with("contacts", "CT001")

    async def test_not_found(self):
        client = _make_mock_client(get_result=None)
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_contact(name="NONEXISTENT")

        assert "not found" in result


class TestListAccounts:
    async def test_returns_formatted_output(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "ACC001", "title": "Acme Corp"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_accounts()

        assert "ACC001" in result
        assert "Acme Corp" in result

    async def test_passes_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_accounts(user="john", search="Acme")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("user", "eq", "john") in filters
        assert ("title", "like", "Acme") in filters

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_accounts()

        assert "No accounts found" in result

    async def test_uses_correct_endpoint(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_accounts()

        assert client.list.call_args[0][0] == "accounts"


class TestGetAccount:
    async def test_found(self):
        client = _make_mock_client(get_result={
            "name": "ACC001",
            "title": "Acme Corp",
            "user": "john",
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_account(name="ACC001")

        assert "ACC001" in result
        assert "Acme Corp" in result

    async def test_not_found(self):
        client = _make_mock_client(get_result=None)
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_account(name="NONEXISTENT")

        assert "not found" in result


class TestListCrmRecords:
    async def test_returns_formatted_output(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "CRM001", "title": "Big Deal", "stage": "OPEN"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_crm_records()

        assert "CRM001" in result
        assert "Big Deal" in result

    async def test_passes_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_crm_records(user="john", stage="OPEN", account="ACC001")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("user", "eq", "john") in filters
        assert ("stage", "eq", "OPEN") in filters
        assert ("account", "eq", "ACC001") in filters

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_crm_records()

        assert "No CRM records found" in result

    async def test_uses_correct_endpoint(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_crm_records()

        assert client.list.call_args[0][0] == "crmRecords"


class TestListCampaignRecords:
    async def test_returns_formatted_output(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "CR001", "user": "john", "action": "called"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_campaign_records()

        assert "CR001" in result

    async def test_passes_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_campaign_records(user="john", date_from="2024-01-01")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("user", "eq", "john") in filters
        assert ("created", "gte", "2024-01-01") in filters

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_campaign_records()

        assert "No campaign records found" in result

    async def test_uses_correct_endpoint(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_campaign_records()

        assert client.list.call_args[0][0] == "campaignsRecords"


class TestListCampaignTypes:
    async def test_returns_types(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "ct_sales", "title": "Sales Campaign"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_campaign_types()

        assert "ct_sales" in result
        client.list.assert_called_once_with("campaignsTypes", skip=0, take=200)


class TestListQueues:
    async def test_returns_queues(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "q_sales", "title": "Sales Queue"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_queues()

        assert "q_sales" in result


class TestResolveUser:
    async def test_exact_title_match(self):
        client = _make_mock_client()
        client.list.return_value = {
            "data": [
                {"name": "john.doebo", "title": "John Doe - Backoffice"},
                {"name": "john.doe", "title": "John Doe"},
            ],
            "total": 2,
        }
        login, display = await server._resolve_user(client, "John Doe")
        assert login == "john.doe"
        assert display == "John Doe"

    async def test_partial_match_returns_first(self):
        client = _make_mock_client()
        client.list.return_value = {
            "data": [{"name": "john.doebo", "title": "John Doe - Backoffice"}],
            "total": 1,
        }
        login, display = await server._resolve_user(client, "John Doe")
        assert login == "john.doebo"

    async def test_falls_back_to_name_search(self):
        call_count = 0

        async def list_side_effect(endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Title search returns nothing
                return {"data": [], "total": 0}
            # Name search returns result
            return {"data": [{"name": "john.doe", "title": "John Doe"}], "total": 1}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        login, display = await server._resolve_user(client, "john.doe")
        assert login == "john.doe"
        assert display == "John Doe"

    async def test_returns_input_when_not_found(self):
        client = _make_mock_client()
        client.list.return_value = {"data": [], "total": 0}
        login, display = await server._resolve_user(client, "nonexistent")
        assert login == "nonexistent"
        assert display is None


class TestListUsers:
    async def test_returns_users(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "john", "title": "John Doe"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_users()

        assert "john" in result

    async def test_search_by_name(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "john.doe", "title": "John Doe"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_users(search="John Doe")

        assert "john.doe" in result
        # Verify it passes the title filter
        call_kwargs = client.list.call_args[1]
        assert call_kwargs["field_filters"] == [("title", "like", "John Doe")]


class TestCountTicketsUserResolution:
    async def test_resolves_display_name(self):
        call_count = 0

        async def list_side_effect(endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if endpoint == "users":
                return {"data": [{"name": "john.doe", "title": "John Doe"}], "total": 1}
            return {"data": [], "total": 21}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _count_tickets(user="John Doe", stage="OPEN")

        assert "21" in result
        assert "John Doe" in result
        # Verify the ticket query used the resolved login name
        ticket_call = [c for c in client.list.call_args_list if c[0][0] == "tickets"][0]
        filters = ticket_call[1]["field_filters"]
        assert ("user", "eq", "john.doe") in filters


class TestListGroups:
    async def test_returns_groups(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "grp1", "title": "Support Group"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_groups()

        assert "grp1" in result
        client.list.assert_called_once_with("groups", skip=0, take=200)

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_groups()

        assert "No groups found" in result


class TestListPauses:
    async def test_returns_pauses(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "break", "title": "Coffee Break"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_pauses()

        assert "break" in result
        client.list.assert_called_once_with("pauses", skip=0, take=200)

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_pauses()

        assert "No pauses found" in result


class TestListStatuses:
    async def test_returns_statuses(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "new", "title": "New"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_statuses()

        assert "new" in result
        client.list.assert_called_once_with("statuses", skip=0, take=200)

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_statuses()

        assert "No statuses found" in result


class TestListTemplates:
    async def test_returns_templates(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "tpl_welcome", "title": "Welcome Email"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_templates()

        assert "tpl_welcome" in result
        client.list.assert_called_once_with("templates", skip=0, take=200)

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_templates()

        assert "No templates found" in result


class TestListRealtimeSessions:
    async def test_returns_sessions(self):
        client = _make_mock_client(list_result={
            "data": [{"id_agent": "john", "state": "Idle", "exten": "100"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_realtime_sessions()

        assert "john" in result
        assert "Idle" in result

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_realtime_sessions()

        assert "No active sessions found" in result

    async def test_uses_correct_endpoint(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_realtime_sessions()

        assert client.list.call_args[0][0] == "realtimeSessions"


class TestGetCall:
    async def test_found(self):
        client = _make_mock_client(get_result={
            "id_call": "CALL001",
            "direction": "in",
            "answered": True,
            "clid": "+420123456789",
            "duration": 120,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_call(name="CALL001")

        assert "CALL001" in result
        assert "+420123456789" in result
        client.get.assert_called_once_with("activitiesCall", "CALL001")

    async def test_not_found(self):
        client = _make_mock_client(get_result=None)
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_call(name="NONEXISTENT")

        assert "not found" in result


class TestGetEmail:
    async def test_found(self):
        client = _make_mock_client(get_result={
            "name": "ACT001",
            "title": "Re: Inquiry",
            "address": "user@example.com",
            "direction": "in",
            "text": "Hello, I need help.",
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_email(name="ACT001")

        assert "ACT001" in result
        assert "user@example.com" in result
        assert "Hello, I need help" in result
        client.get.assert_called_once_with("activitiesEmail", "ACT001")

    async def test_not_found(self):
        client = _make_mock_client(get_result=None)
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_email(name="NONEXISTENT")

        assert "not found" in result


_GET_CHANNELS = [
    # (tool_fn, endpoint, record_name, entity_label)
    (_get_web_chat, "activitiesWeb", "ACT002", "Web chat"),
    (_get_sms, "activitiesSms", "ACT003", "SMS"),
    (_get_messenger_chat, "activitiesFbm", "ACT004", "Messenger chat"),
    (_get_instagram_chat, "activitiesIgdm", "ACT005", "Instagram chat"),
    (_get_whatsapp_chat, "activitiesWap", "ACT006", "WhatsApp chat"),
    (_get_viber_chat, "activitiesVbr", "ACT007", "Viber chat"),
]


class TestGetChannelChat:
    @pytest.mark.parametrize("tool_fn,endpoint,record_name,entity", _GET_CHANNELS)
    async def test_found(self, tool_fn, endpoint, record_name, entity):
        client = _make_mock_client(get_result={
            "name": record_name,
            "state": "closed",
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await tool_fn(name=record_name)
        assert record_name in result
        client.get.assert_called_once_with(endpoint, record_name)

    @pytest.mark.parametrize("tool_fn,endpoint,record_name,entity", _GET_CHANNELS)
    async def test_not_found(self, tool_fn, endpoint, record_name, entity):
        client = _make_mock_client(get_result=None)
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await tool_fn(name="NONEXISTENT")
        assert "not found" in result


class TestGetTicketDetail:
    async def test_returns_ticket_and_activities(self):
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get.return_value = {
            "name": 123,
            "title": "Test ticket",
            "stage": "OPEN",
        }
        client.list.return_value = {
            "data": [
                {"name": "ACT001", "type": "EMAIL", "title": "Re: Help", "time": "2024-01-01"},
                {"name": "ACT002", "type": "CALL", "title": "Follow-up", "time": "2024-01-02"},
            ],
            "total": 2,
        }
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_ticket_detail(name="TK00000123")

        assert "Test ticket" in result
        assert "ACT001" in result
        assert "ACT002" in result
        assert "Activities (2 of 2)" in result
        client.get.assert_called_once_with("tickets", "123")

    async def test_ticket_not_found(self):
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get.return_value = None
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_ticket_detail(name="999999")

        assert "not found" in result

    async def test_no_activities(self):
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get.return_value = {"name": 1, "title": "Ticket"}
        client.list.return_value = {"data": [], "total": 0}
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_ticket_detail(name="1")

        assert "No activities" in result


class TestStatusFilter:
    async def test_list_tickets_with_status(self):
        client = _make_mock_client(list_result={
            "data": [{"name": "TK001", "title": "Lead"}],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_tickets(status="S1-Discovery")

        assert "TK001" in result
        # Verify the status filter was passed
        call_kwargs = client.list.call_args
        filters = call_kwargs.kwargs.get("field_filters") or call_kwargs[1].get("field_filters")
        assert ("statuses", "eq", "S1-Discovery") in filters

    async def test_count_tickets_with_status(self):
        client = _make_mock_client(list_result={"data": [], "total": 5})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _count_tickets(status="S0-Qualify")

        assert "5" in result
        assert "S0-Qualify" in result


class TestGetCallTranscript:
    async def test_returns_formatted_transcript(self):
        client = _make_mock_client(list_result={
            "data": [
                {"name": "t1", "activity": "act_001", "start": "5.0", "end": "10.0",
                 "text": "Hello", "type": "customer"},
                {"name": "t2", "activity": "act_001", "start": "12.0", "end": "18.0",
                 "text": "Hi, how can I help?", "type": "operator"},
            ],
            "total": 2,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_call_transcript(activity="act_001")

        assert "Customer: Hello" in result
        assert "Operator: Hi, how can I help?" in result
        assert "act_001" in result

    async def test_no_transcript(self):
        client = _make_mock_client(list_result={"data": [], "total": 0})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_call_transcript(activity="act_nonexistent")

        assert "No transcript available" in result

    async def test_uses_correct_endpoint_and_filters(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _get_call_transcript(activity="act_001")

        call_args = client.list.call_args
        assert call_args[0][0] == "activitiesCallTranscripts"
        filters = call_args[1]["field_filters"]
        assert ("activity", "eq", "act_001") in filters
        assert call_args[1]["sort"] == "start"
        assert call_args[1]["sort_dir"] == "asc"


class TestListCallTranscripts:
    async def test_returns_calls_with_transcripts(self):
        call_count = 0

        async def list_side_effect(endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if endpoint == "activitiesCall":
                return {
                    "data": [{
                        "id_call": "CALL001",
                        "call_time": "2026-02-10 10:00:00",
                        "direction": "in",
                        "answered": True,
                        "activities": [{"name": "act_001"}],
                    }],
                    "total": 1,
                }
            if endpoint == "activitiesCallTranscripts":
                return {
                    "data": [
                        {"start": "0", "end": "5", "text": "Hi", "type": "customer"},
                        {"start": "6", "end": "12", "text": "Hello!", "type": "operator"},
                    ],
                    "total": 2,
                }
            return {"data": [], "total": 0}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_call_transcripts(date_from="2026-02-09")

        assert "CALL001" in result
        assert "Customer: Hi" in result
        assert "Operator: Hello!" in result

    async def test_no_answered_calls(self):
        client = _make_mock_client(list_result={"data": [], "total": 0})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_call_transcripts(date_from="2026-02-09")

        assert "No answered calls found" in result

    async def test_calls_without_transcripts(self):
        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "activitiesCall":
                return {
                    "data": [{
                        "id_call": "CALL002",
                        "answered": True,
                        "activities": [{"name": "act_002"}],
                    }],
                    "total": 1,
                }
            if endpoint == "activitiesCallTranscripts":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_call_transcripts()

        assert "CALL002" in result
        assert "No transcript available" in result

    async def test_caps_take_at_50(self):
        client = _make_mock_client(list_result={"data": [], "total": 0})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_call_transcripts(take=100)

        call_kwargs = client.list.call_args[1]
        assert call_kwargs["take"] == 50

    async def test_passes_skip_to_api(self):
        client = _make_mock_client(list_result={"data": [], "total": 0})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_call_transcripts(skip=50)

        call_kwargs = client.list.call_args[1]
        assert call_kwargs["skip"] == 50

    async def test_pagination_hint_when_more_results(self):
        calls_data = [
            {"id_call": f"CALL{i}", "answered": True,
             "call_time": "2026-02-10 10:00:00",
             "activities": [{"name": f"act_{i}"}]}
            for i in range(2)
        ]

        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "activitiesCall":
                return {"data": calls_data, "total": 5}
            if endpoint == "activitiesCallTranscripts":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_call_transcripts(take=2)

        assert "Showing 1-2 of 5" in result
        assert "Use skip=2 to see next page" in result

    async def test_no_pagination_hint_on_last_page(self):
        calls_data = [
            {"id_call": "CALL1", "answered": True,
             "call_time": "2026-02-10 10:00:00",
             "activities": [{"name": "act_1"}]}
        ]

        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "activitiesCall":
                return {"data": calls_data, "total": 1}
            if endpoint == "activitiesCallTranscripts":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_call_transcripts()

        assert "Use skip=" not in result

    async def test_passes_user_and_queue_filters(self):
        client = _make_mock_client(list_result={"data": [], "total": 0})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_call_transcripts(user="agent1", queue="10333")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("id_agent", "eq", "agent1") in filters
        assert ("id_queue", "eq", "10333") in filters

    async def test_parallel_transcript_fetches(self):
        """Verify multiple calls trigger parallel transcript fetches."""
        calls_data = [
            {"id_call": f"CALL{i}", "answered": True,
             "activities": [{"name": f"act_{i}"}]}
            for i in range(3)
        ]
        transcript_calls = []

        async def list_side_effect(endpoint, **kwargs):
            if endpoint == "activitiesCall":
                return {"data": calls_data, "total": 3}
            if endpoint == "activitiesCallTranscripts":
                transcript_calls.append(kwargs)
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_call_transcripts()

        # Should have fetched transcripts for all 3 calls
        assert len(transcript_calls) == 3


class TestListArticleFolders:
    async def test_returns_formatted_output(self):
        client = _make_mock_client(list_result={
            "data": [
                {"name": "folder_1", "title": "General", "parent": None, "article_count": 5},
            ],
            "total": 1,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_article_folders()

        assert "folder_1" in result
        assert "General" in result
        client.list.assert_called_once_with("articlesFolders", skip=0, take=200)

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_article_folders()

        assert "No article folders found" in result


class TestListArticles:
    async def test_search_uses_q_parameter(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles(search="sip trunk")

        call_kwargs = client.list.call_args[1]
        assert call_kwargs["search"] == "sip trunk"

    async def test_folder_resolution(self):
        call_count = 0

        async def list_side_effect(endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if endpoint == "articlesFolders":
                return {"data": [{"name": "folder_tel", "title": "Telephony"}], "total": 1}
            if endpoint == "articles":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles(folder="Telephony")

        # The articles call should use the resolved folder ID
        articles_call = [c for c in client.list.call_args_list if c[0][0] == "articles"][0]
        filters = articles_call[1]["field_filters"]
        assert ("folder", "eq", "folder_tel") in filters

    async def test_folder_id_passed_directly(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles(folder="folder_abc")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("folder", "eq", "folder_abc") in filters
        # Should NOT have called articlesFolders endpoint
        assert all(c[0][0] != "articlesFolders" for c in client.list.call_args_list)

    async def test_tag_resolution(self):
        call_count = 0

        async def list_side_effect(endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if endpoint == "articlesTags":
                return {"data": [{"name": "tag_sip", "title": "SIP"}], "total": 1}
            if endpoint == "articles":
                return {"data": [], "total": 0}
            return {"data": [], "total": 0}

        client = _make_mock_client()
        client.list.side_effect = list_side_effect
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles(tag="SIP")

        articles_call = [c for c in client.list.call_args_list if c[0][0] == "articles"][0]
        filters = articles_call[1]["field_filters"]
        assert ("tags", "eq", "tag_sip") in filters

    async def test_published_filter(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles(published="true")

        call_kwargs = client.list.call_args[1]
        filters = call_kwargs["field_filters"]
        assert ("published", "eq", "true") in filters

    async def test_default_take_is_10(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles()

        call_kwargs = client.list.call_args[1]
        assert call_kwargs["take"] == 10

    async def test_take_capped_at_max(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles(take=500)

        call_kwargs = client.list.call_args[1]
        assert call_kwargs["take"] == 200

    async def test_uses_correct_endpoint(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles()

        assert client.list.call_args[0][0] == "articles"

    async def test_empty_result(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _list_articles()

        assert "No articles found" in result

    async def test_requests_correct_fields(self):
        client = _make_mock_client()
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _list_articles()

        call_kwargs = client.list.call_args[1]
        fields = call_kwargs["fields"]
        assert "name" in fields
        assert "title" in fields
        assert "content" not in fields  # NOT in list mode


class TestGetArticle:
    async def test_found(self):
        client = _make_mock_client(get_result={
            "name": "article_001",
            "title": "SIP Trunk Setup",
            "content": "<h1>Setup</h1><p>Instructions here.</p>",
            "seen_count": 10,
        })
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_article(name="article_001")

        assert "article_001" in result
        assert "SIP Trunk Setup" in result
        assert "Setup" in result
        assert "Instructions here" in result
        client.get.assert_called_once_with("articles", "article_001")

    async def test_not_found(self):
        client = _make_mock_client(get_result=None)
        with patch(MOCK_CLIENT_PATH, return_value=client):
            result = await _get_article(name="nonexistent")

        assert "not found" in result

    async def test_uses_correct_endpoint(self):
        client = _make_mock_client(get_result={"name": "a1", "title": "Test"})
        with patch(MOCK_CLIENT_PATH, return_value=client):
            await _get_article(name="a1")

        client.get.assert_called_once_with("articles", "a1")


class TestToolRegistration:
    """Verify all tools are registered with the MCP server."""

    def test_tool_count(self):
        tools = server.mcp._tool_manager._tools
        assert len(tools) == 45

    def test_tool_names(self):
        tools = server.mcp._tool_manager._tools
        expected = {
            "list_tickets",
            "count_tickets",
            "get_ticket",
            "get_ticket_detail",
            "list_account_tickets",
            "list_ticket_categories",
            "list_activities",
            "get_activity",
            "list_calls",
            "get_call",
            "get_call_transcript",
            "list_call_transcripts",
            "list_emails",
            "get_email",
            "list_web_chats",
            "get_web_chat",
            "list_sms_chats",
            "get_sms",
            "list_messenger_chats",
            "get_messenger_chat",
            "list_instagram_chats",
            "get_instagram_chat",
            "list_whatsapp_chats",
            "get_whatsapp_chat",
            "list_viber_chats",
            "get_viber_chat",
            "list_contacts",
            "get_contact",
            "list_accounts",
            "get_account",
            "list_crm_records",
            "list_campaign_records",
            "list_campaign_types",
            "list_queues",
            "list_users",
            "list_groups",
            "list_pauses",
            "list_statuses",
            "list_templates",
            "list_realtime_sessions",
            "scan_calls",
            "scan_emails",
            "list_article_folders",
            "list_articles",
            "get_article",
        }
        assert set(tools.keys()) == expected
