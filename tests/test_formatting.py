from mcp_daktela.formatting import (
    _clean_email_body,
    _extract_name,
    _format_custom_fields,
    _format_extra_fields,
    _format_value,
    _html_to_markdown,
    _linked_name,
    _readable_label,
    _ticket_url,
    _truncate,
    format_account,
    format_activity,
    format_activity_list,
    format_article,
    format_article_folder_tree,
    format_article_list,
    format_call,
    format_campaign_record,
    format_chat,
    format_contact,
    format_contact_list,
    format_crm_record,
    format_email,
    format_simple_list,
    format_simple_record,
    format_ticket,
    format_ticket_list,
    format_transcript,
)


class TestExtractName:
    def test_string(self):
        assert _extract_name("Sales") == "Sales"

    def test_dict_with_title(self):
        assert _extract_name({"title": "Sales Queue", "name": "q_sales"}) == "Sales Queue"

    def test_dict_with_name_only(self):
        assert _extract_name({"name": "q_sales"}) == "q_sales"

    def test_none(self):
        assert _extract_name(None) == ""

    def test_other_type(self):
        assert _extract_name(42) == "42"


class TestTruncate:
    def test_short_text(self):
        assert _truncate("hello") == "hello"

    def test_long_text(self):
        text = "a" * 400
        result = _truncate(text, 300)
        assert len(result) == 303  # 300 + "..."
        assert result.endswith("...")

    def test_none(self):
        assert _truncate(None) == ""

    def test_empty(self):
        assert _truncate("") == ""


class TestCleanEmailBody:
    def test_none(self):
        assert _clean_email_body(None) == ""

    def test_empty(self):
        assert _clean_email_body("") == ""

    def test_plain_text_passthrough(self):
        assert _clean_email_body("Hello, how are you?") == "Hello, how are you?"

    def test_strips_html_tags(self):
        html = "<p>Hello <b>world</b></p>"
        result = _clean_email_body(html)
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_br_to_newline(self):
        result = _clean_email_body("line1<br>line2<br/>line3")
        assert "line1\nline2\nline3" in result

    def test_block_elements_to_newline(self):
        result = _clean_email_body("<div>block1</div><div>block2</div>")
        assert "block1" in result
        assert "block2" in result
        assert "<div>" not in result

    def test_strips_style_blocks(self):
        html = "<style>.foo { color: red; }</style><p>Content here</p>"
        result = _clean_email_body(html)
        assert "Content here" in result
        assert "color" not in result
        assert ".foo" not in result

    def test_strips_script_blocks(self):
        html = "<script>alert('xss')</script><p>Safe content</p>"
        result = _clean_email_body(html)
        assert "Safe content" in result
        assert "alert" not in result

    def test_decodes_html_entities(self):
        result = _clean_email_body("Tom &amp; Jerry &lt;3")
        assert "Tom & Jerry <3" in result

    def test_removes_quoted_reply_on_wrote(self):
        body = "Thanks for the update.\n\nOn Mon, Feb 17, 2026 John Doe wrote:\n> Original message\n> More quoted text"
        result = _clean_email_body(body)
        assert "Thanks for the update" in result
        assert "Original message" not in result

    def test_removes_quoted_reply_czech_variant(self):
        body = "Dekuji za info.\n\nDne 17.2.2026 Jan Novak napsal:\n> Puvodni zprava"
        result = _clean_email_body(body)
        assert "Dekuji za info" in result
        assert "Puvodni zprava" not in result

    def test_removes_gt_quoted_lines(self):
        body = "My reply\n> quoted line 1\n> quoted line 2\nMore of my reply"
        result = _clean_email_body(body)
        assert "My reply" in result
        assert "More of my reply" in result
        assert "quoted line" not in result

    def test_removes_signature(self):
        body = "Please see attached.\n\n-- \nJohn Doe\nSales Manager\n+1 555 1234"
        result = _clean_email_body(body)
        assert "Please see attached" in result
        assert "Sales Manager" not in result
        assert "+1 555 1234" not in result

    def test_truncates_to_max_len(self):
        body = "x" * 2000
        result = _clean_email_body(body, max_len=1500)
        assert len(result) == 1503  # 1500 + "..."
        assert result.endswith("...")

    def test_no_truncation_when_under_limit(self):
        body = "Short email body"
        result = _clean_email_body(body, max_len=1500)
        assert result == "Short email body"
        assert "..." not in result

    def test_no_truncation_with_max_len_zero(self):
        body = "x" * 3000
        result = _clean_email_body(body, max_len=0)
        assert len(result) == 3000
        assert "..." not in result

    def test_collapses_excessive_whitespace(self):
        body = "para1\n\n\n\n\npara2"
        result = _clean_email_body(body)
        assert "para1\n\npara2" == result

    def test_realistic_html_email(self):
        html = """<html><head><style>.ExternalClass { width: 100%; }</style></head>
        <body><div style="font-family: Arial;">
        <p>Hi David,</p>
        <p>I wanted to follow up on our conversation about the <b>contract renewal</b>.
        The deadline is approaching and we haven't received a response yet.</p>
        <p>Could you please confirm by Friday?</p>
        <p>Best regards,</p>
        </div>
        <div class="gmail_quote">
        <div>On Mon, Feb 10, 2026 at 3:15 PM David Hajek wrote:</div>
        <blockquote>
        <p>Thanks for sending over the proposal.</p>
        </blockquote>
        </div></body></html>"""
        result = _clean_email_body(html)
        assert "contract renewal" in result
        assert "confirm by Friday" in result
        assert "ExternalClass" not in result
        assert "<p>" not in result

    def test_default_max_len_is_1500(self):
        body = "a" * 2000
        result = _clean_email_body(body)
        assert len(result) == 1503  # 1500 + "..."


class TestTicketUrl:
    def test_numeric_name(self):
        assert _ticket_url("https://x.daktela.com", 822205) == \
            "https://x.daktela.com/tickets/update/822205"

    def test_numeric_str(self):
        assert _ticket_url("https://x.daktela.com", "822205") == \
            "https://x.daktela.com/tickets/update/822205"

    def test_no_base_url(self):
        assert _ticket_url(None, "822205") is None

    def test_no_name(self):
        assert _ticket_url("https://x.daktela.com", "") is None

    def test_none_name(self):
        assert _ticket_url("https://x.daktela.com", None) is None

    def test_trailing_slash_stripped(self):
        assert _ticket_url("https://x.daktela.com/", 123) == \
            "https://x.daktela.com/tickets/update/123"


class TestLinkedName:
    def test_with_url(self):
        assert _linked_name("TK001", "https://x.daktela.com/tickets/update/1") == \
            "[TK001](https://x.daktela.com/tickets/update/1)"

    def test_without_url(self):
        assert _linked_name("TK001", None) == "TK001"

    def test_int_name(self):
        assert _linked_name(822205, "https://x.daktela.com/tickets/update/822205") == \
            "[822205](https://x.daktela.com/tickets/update/822205)"


class TestFormatTicket:
    def test_full_ticket(self):
        ticket = {
            "name": "TK001",
            "title": "Test",
            "stage": "OPEN",
            "category": {"title": "Sales"},
            "user": {"title": "John"},
            "contact": "C001",
            "created": "2024-01-01",
            "edited": "2024-01-02",
            "description": "Some description",
        }
        result = format_ticket(ticket)
        assert "**TK001** - Test" in result
        assert "Stage: OPEN" in result
        assert "Category: Sales" in result
        assert "Assigned to: John" in result
        assert "Contact: C001" in result

    def test_minimal_ticket(self):
        result = format_ticket({"name": "TK001", "title": "Test"})
        assert "**TK001** - Test" in result

    def test_int_name_with_base_url(self):
        ticket = {"name": 822205, "title": "Test ticket", "stage": "OPEN"}
        result = format_ticket(ticket, base_url="https://example.daktela.com")
        assert "[822205](https://example.daktela.com/tickets/update/822205)" in result
        assert "Test ticket" in result

    def test_link_field_shown_with_base_url(self):
        ticket = {"name": 822205, "title": "Test", "stage": "OPEN"}
        result = format_ticket(ticket, base_url="https://example.daktela.com")
        assert "Link: https://example.daktela.com/tickets/update/822205" in result

    def test_no_link_field_without_base_url(self):
        ticket = {"name": "TK001", "title": "Test"}
        result = format_ticket(ticket)
        assert "Link:" not in result


class TestFormatTicketList:
    def test_empty(self):
        assert format_ticket_list([], 0, 0, 50) == "No tickets found."

    def test_with_records(self):
        records = [
            {"name": "TK001", "title": "First"},
            {"name": "TK002", "title": "Second"},
        ]
        result = format_ticket_list(records, 10, 0, 50)
        assert "Showing 1-2 of 10 tickets" in result
        assert "**TK001**" in result
        assert "**TK002**" in result

    def test_pagination_hint(self):
        records = [{"name": "TK001", "title": "First"}]
        result = format_ticket_list(records, 100, 0, 1)
        assert "skip=1" in result

    def test_no_pagination_hint_on_last_page(self):
        records = [{"name": "TK001", "title": "First"}]
        result = format_ticket_list(records, 1, 0, 50)
        assert "skip=" not in result


class TestFormatActivity:
    def test_full_activity(self):
        activity = {
            "name": "ACT001",
            "title": "Call",
            "type": "CALL",
            "direction": "IN",
            "queue": {"title": "Support"},
            "user": {"title": "Jane"},
            "ticket": "TK001",
            "contact": "C001",
            "created": "2024-01-01",
        }
        result = format_activity(activity)
        assert "**ACT001** - Call" in result
        assert "Type: CALL" in result
        assert "Direction: IN" in result


class TestFormatActivityList:
    def test_empty(self):
        assert format_activity_list([], 0, 0, 50) == "No activities found."


class TestFormatContact:
    def test_full_contact(self):
        contact = {
            "name": "C001",
            "firstname": "John",
            "lastname": "Doe",
            "account": {"title": "Acme Corp"},
            "email": "john@example.com",
            "number": "+1234567890",
        }
        result = format_contact(contact)
        assert "**C001** - John Doe" in result
        assert "Account: Acme Corp" in result
        assert "Email: john@example.com" in result
        assert "Phone: +1234567890" in result


class TestFormatContactList:
    def test_empty(self):
        assert format_contact_list([], 0, 0, 50) == "No contacts found."


class TestFormatSimple:
    def test_simple_record(self):
        result = format_simple_record({"name": "q_sales", "title": "Sales Queue"})
        assert "**q_sales** - Sales Queue" in result

    def test_simple_list_empty(self):
        assert format_simple_list([], 0, 0, 50, "queues") == "No queues found."

    def test_simple_list_with_records(self):
        records = [
            {"name": "q1", "title": "Queue 1"},
            {"name": "q2", "title": "Queue 2"},
        ]
        result = format_simple_list(records, 2, 0, 50, "queues")
        assert "Showing 1-2 of 2 queues" in result
        assert "**q1**" in result
        assert "**q2**" in result


class TestReadableLabel:
    def test_snake_case(self):
        assert _readable_label("lead_type") == "Lead type"

    def test_camel_case(self):
        assert _readable_label("leadType") == "Lead Type"

    def test_simple(self):
        assert _readable_label("status") == "Status"

    def test_empty(self):
        assert _readable_label("") == ""


class TestFormatValue:
    def test_none(self):
        assert _format_value(None) is None

    def test_empty_string(self):
        assert _format_value("") is None

    def test_string(self):
        assert _format_value("hello") == "hello"

    def test_int(self):
        assert _format_value(42) == "42"

    def test_zero(self):
        assert _format_value(0) == "0"

    def test_bool_true(self):
        assert _format_value(True) == "Yes"

    def test_bool_false(self):
        assert _format_value(False) == "No"

    def test_dict_with_title(self):
        assert _format_value({"title": "Sales", "name": "q_sales"}) == "Sales"

    def test_dict_no_name(self):
        assert _format_value({}) is None

    def test_list(self):
        assert _format_value(["a", "b"]) == "a, b"

    def test_empty_list(self):
        assert _format_value([]) is None

    def test_list_of_dicts(self):
        result = _format_value([{"title": "S1"}, {"title": "S2"}])
        assert result == "S1, S2"


class TestFormatCustomFields:
    def test_renders_custom_fields(self):
        record = {
            "name": "TK001",
            "customFields": {
                "lead_type": "Inbound",
                "mrr": "5000",
                "empty_field": "",
                "none_field": None,
            },
        }
        lines = _format_custom_fields(record)
        assert "  Lead type: Inbound" in lines
        assert "  Mrr: 5000" in lines
        assert len(lines) == 2  # empty and None skipped

    def test_no_custom_fields(self):
        assert _format_custom_fields({"name": "TK001"}) == []

    def test_custom_fields_not_dict(self):
        assert _format_custom_fields({"customFields": "bad"}) == []

    def test_dict_value_in_custom_fields(self):
        record = {"customFields": {"agent": {"title": "John Doe", "name": "jd"}}}
        lines = _format_custom_fields(record)
        assert "  Agent: John Doe" in lines


class TestFormatExtraFields:
    def test_renders_unknown_fields(self):
        record = {
            "name": "TK001",
            "title": "Test",
            "unknown_field": "surprise",
        }
        lines = _format_extra_fields(record, {"name", "title"})
        assert "  Unknown field: surprise" in lines

    def test_skips_known_keys(self):
        record = {"name": "TK001", "title": "Test"}
        assert _format_extra_fields(record, {"name", "title"}) == []

    def test_skips_internal_fields(self):
        record = {"_links": {"self": "/api/..."}, "_type": "ticket"}
        assert _format_extra_fields(record, set()) == []

    def test_skips_custom_fields_key(self):
        record = {"customFields": {"a": "b"}}
        assert _format_extra_fields(record, set()) == []

    def test_renders_dict_value(self):
        record = {"some_fk": {"title": "Related Object"}}
        lines = _format_extra_fields(record, set())
        assert "  Some fk: Related Object" in lines


class TestTicketCustomFields:
    def test_custom_fields_in_ticket(self):
        ticket = {
            "name": "TK001",
            "title": "Sales Lead",
            "customFields": {
                "lead_source": "Website",
                "mrr": "10000",
            },
        }
        result = format_ticket(ticket)
        assert "Lead source: Website" in result
        assert "Mrr: 10000" in result

    def test_extra_fields_in_ticket(self):
        ticket = {
            "name": "TK001",
            "title": "Test",
            "some_new_api_field": "new_value",
        }
        result = format_ticket(ticket)
        assert "Some new api field: new_value" in result


class TestActivityContent:
    def test_description_shown(self):
        activity = {
            "name": "ACT001",
            "type": "EMAIL",
            "description": "Customer asked about pricing",
        }
        result = format_activity(activity)
        assert "Content: Customer asked about pricing" in result

    def test_description_truncated(self):
        activity = {
            "name": "ACT001",
            "description": "x" * 600,
        }
        result = format_activity(activity)
        assert "Content: " in result
        assert "..." in result
        # 500 x's from truncation, no "x" in other parts of the output
        assert result.count("x") == 500

    def test_custom_fields_in_activity(self):
        activity = {
            "name": "ACT001",
            "customFields": {"sentiment": "positive"},
        }
        result = format_activity(activity)
        assert "Sentiment: positive" in result


class TestEmailText:
    def test_body_shown(self):
        email = {
            "name": "ACT001",
            "title": "Re: Help",
            "text": "Dear support, I need assistance.",
        }
        result = format_email(email)
        assert "Body: Dear support, I need assistance." in result

    def test_body_truncated_at_1500(self):
        email = {
            "name": "ACT001",
            "text": "z" * 2000,
        }
        result = format_email(email)
        assert "Body: " in result
        assert "..." in result
        assert result.count("z") == 1500

    def test_html_body_cleaned(self):
        email = {
            "name": "ACT001",
            "text": "<p>Hello <b>world</b></p><style>.x{}</style>",
        }
        result = format_email(email)
        assert "Body: " in result
        assert "Hello" in result
        assert "world" in result
        assert "<p>" not in result
        assert "<style>" not in result

    def test_custom_fields_in_email(self):
        email = {
            "name": "ACT001",
            "customFields": {"priority_override": "urgent"},
        }
        result = format_email(email)
        assert "Priority override: urgent" in result


class TestDetailMode:
    """Verify detail=True disables truncation on formatters that support it."""

    def test_ticket_description_not_truncated(self):
        long_desc = "w" * 600
        ticket = {"name": "TK001", "title": "Test", "description": long_desc}
        result = format_ticket(ticket, detail=True)
        assert "..." not in result
        assert result.count("w") == 600

    def test_ticket_description_truncated_by_default(self):
        long_desc = "w" * 600
        ticket = {"name": "TK001", "title": "Test", "description": long_desc}
        result = format_ticket(ticket)
        assert "..." in result
        assert result.count("w") == 300

    def test_activity_description_not_truncated(self):
        long_desc = "q" * 700
        activity = {"name": "ACT001", "description": long_desc}
        result = format_activity(activity, detail=True)
        assert "..." not in result
        assert result.count("q") == 700

    def test_activity_description_truncated_by_default(self):
        long_desc = "q" * 700
        activity = {"name": "ACT001", "description": long_desc}
        result = format_activity(activity)
        assert "..." in result
        assert result.count("q") == 500

    def test_email_body_not_truncated_in_detail(self):
        long_text = "m" * 2000
        email = {"name": "ACT001", "text": long_text}
        result = format_email(email, detail=True)
        assert "..." not in result
        assert result.count("m") == 2000

    def test_email_body_truncated_at_1500_by_default(self):
        long_text = "m" * 2000
        email = {"name": "ACT001", "text": long_text}
        result = format_email(email)
        assert "..." in result
        assert result.count("m") == 1500

    def test_email_html_cleaned_in_detail(self):
        html = "<p>Important <b>message</b></p><style>.x{}</style>"
        email = {"name": "ACT001", "text": html}
        result = format_email(email, detail=True)
        assert "Important" in result
        assert "message" in result
        assert "<p>" not in result

    def test_account_description_not_truncated(self):
        long_desc = "v" * 500
        account = {"name": "ACC001", "description": long_desc}
        result = format_account(account, detail=True)
        assert "..." not in result
        assert result.count("v") == 500

    def test_crm_record_description_not_truncated(self):
        long_desc = "j" * 500
        crm = {"name": "CRM001", "description": long_desc}
        result = format_crm_record(crm, detail=True)
        assert "..." not in result
        assert result.count("j") == 500


class TestCustomFieldsOnAllFormatters:
    """Verify custom fields and extra fields work across all entity formatters."""

    def test_contact(self):
        result = format_contact({
            "name": "C001",
            "customFields": {"vip": "yes"},
            "loyalty_tier": "gold",
        })
        assert "Vip: yes" in result
        assert "Loyalty tier: gold" in result

    def test_call(self):
        result = format_call({
            "id_call": "CALL001",
            "customFields": {"recording_reviewed": "true"},
        })
        assert "Recording reviewed: true" in result

    def test_chat(self):
        result = format_chat({
            "name": "ACT001",
            "customFields": {"bot_handled": "yes"},
        })
        assert "Bot handled: yes" in result

    def test_account(self):
        result = format_account({
            "name": "ACC001",
            "customFields": {"industry": "SaaS"},
        })
        assert "Industry: SaaS" in result

    def test_crm_record(self):
        result = format_crm_record({
            "name": "CRM001",
            "customFields": {"deal_size": "50000"},
        })
        assert "Deal size: 50000" in result

    def test_campaign_record(self):
        result = format_campaign_record({
            "name": "CAMP001",
            "customFields": {"outcome": "interested"},
        })
        assert "Outcome: interested" in result


class TestFormatTranscript:
    def test_empty_segments(self):
        result = format_transcript([])
        assert result == "No transcript available for this call."

    def test_single_segment(self):
        segments = [{"start": "5.0", "end": "8.0", "text": "Hello", "type": "customer"}]
        result = format_transcript(segments)
        assert "[0:05] Customer: Hello" in result
        assert "**Transcript**" in result

    def test_multiple_segments_sorted(self):
        segments = [
            {"start": "30.0", "end": "35.0", "text": "How can I help?", "type": "operator"},
            {"start": "5.0", "end": "10.0", "text": "Hi there", "type": "customer"},
            {"start": "15.0", "end": "20.0", "text": "I have an issue", "type": "customer"},
        ]
        result = format_transcript(segments)
        lines = result.split("\n")
        # First dialogue line should be the earliest (5s)
        assert "[0:05] Customer: Hi there" in lines[1]
        assert "[0:15] Customer: I have an issue" in lines[2]
        assert "[0:30] Operator: How can I help?" in lines[3]

    def test_time_formatting_minutes(self):
        segments = [{"start": "125.0", "end": "130.0", "text": "Still here", "type": "customer"}]
        result = format_transcript(segments)
        assert "[2:05] Customer: Still here" in result

    def test_activity_name_in_header(self):
        segments = [{"start": "0", "end": "5", "text": "Hi", "type": "operator"}]
        result = format_transcript(segments, activity_name="activity_abc123")
        assert "**Transcript** (activity_abc123)" in result

    def test_no_activity_name(self):
        segments = [{"start": "0", "end": "5", "text": "Hi", "type": "operator"}]
        result = format_transcript(segments)
        assert "**Transcript**" in result
        assert "activity" not in result.split("\n")[0]

    def test_empty_text_segments(self):
        segments = [
            {"start": "0", "end": "5", "text": "", "type": "customer"},
            {"start": "5", "end": "10", "text": "", "type": "operator"},
        ]
        result = format_transcript(segments)
        assert "no text content" in result


class TestFormatCallActivity:
    """Verify format_call extracts activity name from the activities list."""

    def test_activity_name_shown(self):
        record = {
            "id_call": "CALL001",
            "activities": [{"name": "activity_abc123", "title": "Call Activity"}],
        }
        result = format_call(record)
        assert "Activity: activity_abc123" in result

    def test_no_activities(self):
        record = {"id_call": "CALL001"}
        result = format_call(record)
        assert "Activity:" not in result

    def test_empty_activities_list(self):
        record = {"id_call": "CALL001", "activities": []}
        result = format_call(record)
        assert "Activity:" not in result

    def test_ticket_link_from_activity(self):
        record = {
            "id_call": "CALL001",
            "activities": [{"name": "act_123", "ticket": {"name": 822786, "title": "Some ticket"}}],
        }
        result = format_call(record, base_url="https://example.daktela.com")
        assert "[822786](https://example.daktela.com/tickets/update/822786)" in result

    def test_no_ticket_link_without_base_url(self):
        record = {
            "id_call": "CALL001",
            "activities": [{"name": "act_123", "ticket": {"name": 822786, "title": "X"}}],
        }
        result = format_call(record)
        assert "Ticket:" not in result

    def test_no_ticket_link_when_activity_has_no_ticket(self):
        record = {
            "id_call": "CALL001",
            "activities": [{"name": "act_123"}],
        }
        result = format_call(record, base_url="https://example.daktela.com")
        assert "Ticket:" not in result


class TestHtmlToMarkdown:
    def test_simple_html(self):
        result = _html_to_markdown("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<p>" not in result

    def test_relative_urls_prepended(self):
        html = '<a href="/kb/article/123">Link</a>'
        result = _html_to_markdown(html, base_url="https://example.daktela.com")
        assert "https://example.daktela.com/kb/article/123" in result

    def test_absolute_urls_unchanged(self):
        html = '<a href="https://other.com/page">Link</a>'
        result = _html_to_markdown(html, base_url="https://example.daktela.com")
        assert "https://other.com/page" in result

    def test_lists_converted(self):
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = _html_to_markdown(html)
        assert "Item 1" in result
        assert "Item 2" in result

    def test_empty_input(self):
        assert _html_to_markdown("") == ""
        assert _html_to_markdown(None) == ""

    def test_strips_style_blocks(self):
        html = "<style>.foo { color: red; }</style><p>Content</p>"
        result = _html_to_markdown(html)
        assert "Content" in result
        assert "color" not in result

    def test_strips_script_blocks(self):
        html = "<script>alert('x')</script><p>Safe</p>"
        result = _html_to_markdown(html)
        assert "Safe" in result
        assert "alert" not in result

    def test_collapses_whitespace(self):
        html = "<p>First</p>\n\n\n\n<p>Second</p>"
        result = _html_to_markdown(html)
        assert "\n\n\n" not in result
        assert "First" in result
        assert "Second" in result


class TestFormatArticle:
    def test_list_mode(self):
        record = {
            "name": "article_001",
            "title": "How to configure SIP trunk",
            "folder": {"title": "Telephony", "name": "folder_tel"},
            "tags": [{"title": "SIP"}, {"title": "VoIP"}],
            "description": "Step by step guide for SIP trunk configuration",
            "created": "2025-01-01",
            "edited": "2025-06-15",
        }
        result = format_article(record)
        assert "**article_001** - How to configure SIP trunk" in result
        assert "Folder: Telephony" in result
        assert "Tags: SIP, VoIP" in result
        assert "Description:" in result
        assert "Created: 2025-01-01" in result
        # Should NOT have URL in list mode
        assert "URL:" not in result

    def test_detail_mode(self):
        record = {
            "name": "article_001",
            "title": "SIP Guide",
            "content": "<h1>Setup</h1><p>Follow these steps.</p>",
            "seen_count": 42,
            "created": "2025-01-01",
        }
        result = format_article(record, base_url="https://x.daktela.com", detail=True)
        assert "URL: https://x.daktela.com/articles/update/article_001" in result
        assert "Views: 42" in result
        assert "Setup" in result
        assert "Follow these steps" in result
        assert "<h1>" not in result

    def test_empty_fields(self):
        record = {"name": "article_002", "title": "Empty"}
        result = format_article(record)
        assert "**article_002** - Empty" in result
        assert "Folder:" not in result
        assert "Tags:" not in result

    def test_nested_folder_object(self):
        record = {
            "name": "a1",
            "title": "Test",
            "folder": {"title": "Docs", "name": "folder_docs"},
        }
        result = format_article(record)
        assert "Folder: Docs" in result

    def test_string_folder(self):
        record = {"name": "a1", "title": "Test", "folder": "folder_123"}
        result = format_article(record)
        assert "Folder: folder_123" in result

    def test_detail_without_content_shows_description(self):
        record = {
            "name": "a1",
            "title": "Test",
            "description": "Some description text",
            "content": "",
        }
        result = format_article(record, detail=True)
        assert "Description: Some description text" in result

    def test_custom_fields(self):
        record = {
            "name": "a1",
            "title": "Test",
            "customFields": {"priority": "high"},
        }
        result = format_article(record)
        assert "Priority: high" in result


class TestFormatArticleList:
    def test_empty(self):
        assert format_article_list([], 0, 0, 10) == "No articles found."

    def test_with_records(self):
        records = [
            {"name": "a1", "title": "First Article"},
            {"name": "a2", "title": "Second Article"},
        ]
        result = format_article_list(records, 5, 0, 10)
        assert "Showing 1-2 of 5 articles" in result
        assert "**a1**" in result
        assert "**a2**" in result

    def test_pagination_hint(self):
        records = [{"name": "a1", "title": "First"}]
        result = format_article_list(records, 50, 0, 10)
        assert "skip=1" in result

    def test_no_pagination_on_last_page(self):
        records = [{"name": "a1", "title": "First"}]
        result = format_article_list(records, 1, 0, 10)
        assert "skip=" not in result


class TestFormatArticleFolderTree:
    def test_empty(self):
        assert format_article_folder_tree([]) == "No article folders found."

    def test_flat_folders(self):
        records = [
            {"name": "folder_1", "title": "General", "parent": None, "article_count": 5},
            {"name": "folder_2", "title": "Technical", "parent": None, "article_count": 3},
        ]
        result = format_article_folder_tree(records)
        assert "folder_1" in result
        assert "General" in result
        assert "(5 articles)" in result
        assert "folder_2" in result
        assert "Technical" in result

    def test_hierarchical_tree(self):
        records = [
            {"name": "folder_root", "title": "Root", "parent": None, "article_count": 0},
            {"name": "folder_child", "title": "Child", "parent": {"name": "folder_root"}, "article_count": 2},
        ]
        result = format_article_folder_tree(records)
        lines = result.split("\n")
        # Root should not be indented, child should be
        root_line = [l for l in lines if "folder_root" in l][0]
        child_line = [l for l in lines if "folder_child" in l][0]
        assert root_line.startswith("- ")
        assert child_line.startswith("  - ")

    def test_orphan_folders(self):
        """Folders whose parent is not in the list should appear as roots."""
        records = [
            {"name": "folder_orphan", "title": "Orphan", "parent": {"name": "folder_missing"}, "article_count": 1},
        ]
        result = format_article_folder_tree(records)
        assert "folder_orphan" in result
        assert "Orphan" in result

    def test_no_article_count(self):
        records = [{"name": "folder_1", "title": "Empty"}]
        result = format_article_folder_tree(records)
        assert "folder_1" in result
        assert "articles)" not in result

    def test_total_count(self):
        records = [
            {"name": "f1", "title": "A"},
            {"name": "f2", "title": "B"},
            {"name": "f3", "title": "C"},
        ]
        result = format_article_folder_tree(records)
        assert "3 total" in result
