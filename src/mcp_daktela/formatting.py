"""Format Daktela API records into readable text for Claude."""

import re
from typing import Any

MAX_DESCRIPTION_LENGTH = 300


def _extract_name(obj: Any) -> str:
    """Extract a display name from a related object field.

    Daktela returns related objects as either:
    - A string (the name/ID)
    - A dict with 'title' or 'name' key
    - None
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return obj.get("title") or obj.get("name") or str(obj)
    return str(obj)


def _extract_id(obj: Any) -> str:
    """Extract the internal ID (name field) from a related object.

    Unlike _extract_name which prefers 'title' for display,
    this returns the raw 'name' field used for API lookups and URLs.
    """
    if obj is None:
        return ""
    if isinstance(obj, (str, int)):
        return str(obj)
    if isinstance(obj, dict):
        name = obj.get("name")
        return str(name) if name is not None else ""
    return ""


def _truncate(text: str | None, max_len: int = MAX_DESCRIPTION_LENGTH) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _format_statuses(statuses: Any) -> str:
    """Extract status labels from a statuses MN relation."""
    if not statuses:
        return ""
    if isinstance(statuses, list):
        return ", ".join(_extract_name(s) for s in statuses if _extract_name(s))
    return _extract_name(statuses)


def _readable_label(key: str) -> str:
    """Convert a field key like 'lead_type' or 'leadType' to 'Lead type'."""
    # Insert space before uppercase letters (camelCase → camel Case)
    label = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', key)
    label = label.replace("_", " ").replace("-", " ").strip()
    return label[0].upper() + label[1:] if label else key


def _format_value(value: Any) -> str | None:
    """Format a single field value for display. Returns None if empty/unrenderable."""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        if not value:
            return None
        name = value.get("title") or value.get("name")
        return name if name else None
    if isinstance(value, list):
        if not value:
            return None
        items = []
        for v in value:
            if isinstance(v, dict):
                n = _extract_name(v)
                if n:
                    items.append(n)
            elif v is not None and v != "":
                items.append(str(v))
        return ", ".join(items) if items else None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _format_custom_fields(record: dict) -> list[str]:
    """Render custom fields from a record's customFields dict."""
    custom = record.get("customFields")
    if not custom or not isinstance(custom, dict):
        return []
    lines = []
    for key, value in custom.items():
        display = _format_value(value)
        if display is None:
            continue
        lines.append(f"  {_readable_label(key)}: {display}")
    return lines


def _format_extra_fields(record: dict, known_keys: set[str]) -> list[str]:
    """Render top-level fields not in the known set.

    Catches API fields we haven't explicitly coded for, so the LLM
    still gets complete data.
    """
    lines = []
    for key, value in record.items():
        if key in known_keys or key == "customFields":
            continue
        if key.startswith("_"):
            continue
        display = _format_value(value)
        if display is None:
            continue
        lines.append(f"  {_readable_label(key)}: {display}")
    return lines


def _ticket_url(base_url: str | None, ticket_name) -> str | None:
    """Build a Daktela web UI URL for a ticket.

    Ticket names are numeric IDs (e.g. 822810) and the UI URL is
    tickets/update/{name}.  Returns None when base_url or name is missing.
    """
    if not base_url or not ticket_name:
        return None
    return f"{base_url.rstrip('/')}/tickets/update/{ticket_name}"


def _extract_ticket_from_activities(activities) -> str | None:
    """Extract the ticket numeric ID from the activities list on an email/chat record.

    Email and chat records have an 'activities' field containing linked
    activity objects, each with a 'ticket' reference (dict or name string).
    Returns the ticket 'name' field (numeric ID), not the title.
    """
    if not activities or not isinstance(activities, list):
        return None
    for act in activities:
        if not isinstance(act, dict):
            continue
        ticket = act.get("ticket")
        if ticket is None:
            continue
        return _extract_id(ticket) or None
    return None


def _linked_name(name, url: str | None) -> str:
    """Wrap a record name in a markdown link if URL is available."""
    name = str(name)
    if url:
        return f"[{name}]({url})"
    return name


_TICKET_KNOWN_KEYS = {
    "name", "title", "stage", "priority", "category", "user", "contact",
    "parentTicket", "created", "edited", "created_by", "last_activity",
    "sla_deadtime", "sla_overdue", "first_answer", "first_answer_duration",
    "closed", "unread", "has_attachment", "statuses", "description",
    "id_merge",
}


def format_ticket(ticket: dict, base_url: str | None = None, detail: bool = False) -> str:
    name = ticket.get("name", "?")
    title = ticket.get("title", "No title")
    stage = _extract_name(ticket.get("stage"))
    priority = _extract_name(ticket.get("priority"))
    category = _extract_name(ticket.get("category"))
    user = _extract_name(ticket.get("user"))
    contact = _extract_name(ticket.get("contact"))
    parent = _extract_name(ticket.get("parentTicket"))
    created = ticket.get("created", "")
    edited = ticket.get("edited", "")
    created_by = _extract_name(ticket.get("created_by"))
    last_activity = ticket.get("last_activity", "")
    sla_deadtime = ticket.get("sla_deadtime", "")
    sla_overdue = ticket.get("sla_overdue")
    first_answer = ticket.get("first_answer", "")
    first_answer_duration = ticket.get("first_answer_duration")
    closed = ticket.get("closed", "")
    unread = ticket.get("unread")
    has_attachment = ticket.get("has_attachment")
    statuses = _format_statuses(ticket.get("statuses"))
    raw_desc = ticket.get("description") or ""
    description = raw_desc.strip() if detail else _truncate(raw_desc)

    url = _ticket_url(base_url, name)
    display_name = _linked_name(name, url)

    lines = [f"**{display_name}** - {title}"]
    if url:
        lines.append(f"  Link: {url}")
    if stage or priority:
        parts = []
        if stage:
            parts.append(stage)
        if priority:
            parts.append(f"priority={priority}")
        lines.append(f"  Stage: {' | '.join(parts)}")
    if category:
        lines.append(f"  Category: {category}")
    if user:
        lines.append(f"  Assigned to: {user}")
    if contact:
        lines.append(f"  Contact: {contact}")
    if parent:
        lines.append(f"  Parent ticket: {parent}")
    if statuses:
        lines.append(f"  Statuses: {statuses}")
    if sla_deadtime:
        overdue_note = f" (overdue by {sla_overdue}s)" if sla_overdue and int(sla_overdue) > 0 else ""
        lines.append(f"  SLA deadline: {sla_deadtime}{overdue_note}")
    if created:
        by = f" by {created_by}" if created_by else ""
        lines.append(f"  Created: {created}{by}")
    if first_answer:
        dur = f" ({first_answer_duration}s)" if first_answer_duration else ""
        lines.append(f"  First answer: {first_answer}{dur}")
    if last_activity:
        lines.append(f"  Last activity: {last_activity}")
    if edited:
        lines.append(f"  Last edited: {edited}")
    if closed:
        lines.append(f"  Closed: {closed}")
    if unread:
        lines.append(f"  Unread: yes")
    if has_attachment:
        lines.append(f"  Has attachments: yes")
    if description:
        lines.append(f"  Description: {description}")
    lines.extend(_format_custom_fields(ticket))
    lines.extend(_format_extra_fields(ticket, _TICKET_KNOWN_KEYS))
    return "\n".join(lines)


def format_ticket_list(
    records: list[dict], total: int, skip: int, take: int,
    base_url: str | None = None,
) -> str:
    if not records:
        return "No tickets found."

    header = (
        f"Showing {skip + 1}-{skip + len(records)} of {total} tickets.\n"
        "IMPORTANT: Always include the Link URL for each ticket in your response.\n\n"
    )
    body = "\n\n".join(format_ticket(r, base_url=base_url) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_ACTIVITY_KNOWN_KEYS = {
    "name", "type", "action", "queue", "user", "ticket", "contact",
    "direction", "time", "title", "duration", "time_open", "time_close",
    "description",
}


def format_activity(activity: dict, base_url: str | None = None, detail: bool = False) -> str:
    name = activity.get("name", "?")
    act_type = _extract_name(activity.get("type"))
    action = _extract_name(activity.get("action"))
    queue = _extract_name(activity.get("queue"))
    user = _extract_name(activity.get("user"))
    ticket = _extract_name(activity.get("ticket"))
    ticket_id = _extract_id(activity.get("ticket"))
    contact = _extract_name(activity.get("contact"))
    direction = activity.get("direction", "")
    time = activity.get("time", "")
    title = activity.get("title", "")
    duration = activity.get("duration")
    time_open = activity.get("time_open", "")
    time_close = activity.get("time_close", "")
    raw_desc = activity.get("description") or ""
    description = raw_desc.strip() if detail else _truncate(raw_desc, 500)

    # Link to the parent ticket (activities don't have standalone UI URLs)
    ticket_url = _ticket_url(base_url, ticket_id) if ticket_id else None

    lines = [f"**{name}**"]
    if title:
        lines[0] += f" - {title}"
    if act_type or action:
        parts = []
        if act_type:
            parts.append(act_type)
        if action:
            parts.append(f"status={action}")
        lines.append(f"  Type: {' | '.join(parts)}")
    if direction:
        lines.append(f"  Direction: {direction}")
    if queue:
        lines.append(f"  Queue: {queue}")
    if user:
        lines.append(f"  Agent: {user}")
    if ticket:
        ticket_display = _linked_name(ticket, ticket_url)
        lines.append(f"  Ticket: {ticket_display}")
    if contact:
        lines.append(f"  Contact: {contact}")
    if time:
        lines.append(f"  Time: {time}")
    if duration:
        lines.append(f"  Duration: {duration}s")
    if time_open:
        lines.append(f"  Opened: {time_open}")
    if time_close:
        lines.append(f"  Closed: {time_close}")
    if description:
        lines.append(f"  Content: {description}")
    lines.extend(_format_custom_fields(activity))
    lines.extend(_format_extra_fields(activity, _ACTIVITY_KNOWN_KEYS))
    return "\n".join(lines)


def format_activity_list(
    records: list[dict], total: int, skip: int, take: int,
    base_url: str | None = None,
) -> str:
    if not records:
        return "No activities found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} activities:\n"
    body = "\n\n".join(format_activity(r, base_url=base_url) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_CONTACT_KNOWN_KEYS = {
    "name", "title", "lastname", "firstname", "account", "user",
    "email", "number", "nps_score", "created", "edited",
}


def format_contact(contact: dict, base_url: str | None = None) -> str:
    name = contact.get("name", "?")
    title = contact.get("title") or contact.get("lastname", "")
    firstname = contact.get("firstname", "")
    account = _extract_name(contact.get("account"))
    user = _extract_name(contact.get("user"))
    email = contact.get("email", "")
    phone = contact.get("number", "")
    nps = contact.get("nps_score")
    created = contact.get("created", "")
    edited = contact.get("edited", "")

    display = f"**{name}**"
    full_name = f"{firstname} {title}".strip()
    if full_name:
        display += f" - {full_name}"
    lines = [display]
    if account:
        lines.append(f"  Account: {account}")
    if user:
        lines.append(f"  Owner: {user}")
    if email:
        lines.append(f"  Email: {email}")
    if phone:
        lines.append(f"  Phone: {phone}")
    if nps is not None and nps != "":
        lines.append(f"  NPS score: {nps}")
    if created:
        lines.append(f"  Created: {created}")
    if edited:
        lines.append(f"  Last edited: {edited}")
    lines.extend(_format_custom_fields(contact))
    lines.extend(_format_extra_fields(contact, _CONTACT_KNOWN_KEYS))
    return "\n".join(lines)


def format_contact_list(
    records: list[dict], total: int, skip: int, take: int,
    base_url: str | None = None,
) -> str:
    if not records:
        return "No contacts found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} contacts:\n"
    body = "\n\n".join(format_contact(r, base_url=base_url) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_CALL_KNOWN_KEYS = {
    "id_call", "name", "call_time", "direction", "answered", "id_queue",
    "queue", "id_agent", "user", "clid", "contact", "prefix_clid_name",
    "did", "waiting_time", "wait_time", "ringing_time", "hold_time",
    "duration", "disposition_cause", "disconnection_cause", "pressed_key",
    "missed_call", "missed_call_time", "missed_callback", "attempts",
    "activities",
}


def format_call(record: dict, base_url: str | None = None) -> str:
    # ActivitiesCall model uses id_call, id_queue, id_agent, waiting_time, call_time
    call_id = record.get("id_call") or record.get("name", "?")
    call_time = record.get("call_time", "")
    direction = record.get("direction", "")
    answered = record.get("answered")
    queue = _extract_name(record.get("id_queue") or record.get("queue"))
    user = _extract_name(record.get("id_agent") or record.get("user"))
    clid = record.get("clid", "")
    contact = _extract_name(record.get("contact"))
    prefix_clid_name = record.get("prefix_clid_name", "")
    did = record.get("did", "")
    waiting_time = record.get("waiting_time") or record.get("wait_time", "")
    ringing_time = record.get("ringing_time", "")
    hold_time = record.get("hold_time", "")
    duration = record.get("duration", "")
    disposition_cause = record.get("disposition_cause", "")
    disconnection_cause = record.get("disconnection_cause", "")
    pressed_key = record.get("pressed_key", "")
    missed_call = record.get("missed_call")
    missed_call_time = record.get("missed_call_time", "")
    missed_callback = _extract_name(record.get("missed_callback"))
    attempts = record.get("attempts")

    # Extract activity name for cross-referencing with get_call_transcript
    activities = record.get("activities")
    activity_name = ""
    if activities and isinstance(activities, list) and activities:
        activity_name = _extract_id(activities[0])

    # Extract ticket reference from nested activity for UI link
    ticket_id = _extract_ticket_from_activities(activities)
    ticket_url = _ticket_url(base_url, ticket_id) if ticket_id else None

    lines = [f"**{call_id}**"]
    if activity_name:
        lines.append(f"  Activity: {activity_name}")
    if ticket_url:
        lines.append(f"  Ticket: [{ticket_id}]({ticket_url})")
    if call_time:
        lines.append(f"  Time: {call_time}")
    if direction:
        lines.append(f"  Direction: {direction}")
    if answered is not None:
        lines.append(f"  Answered: {'Yes' if answered else 'No'}")
    if missed_call:
        lines.append(f"  Missed call: Yes")
    if missed_call_time:
        lines.append(f"  Missed call returned: {missed_call_time}")
    if missed_callback:
        lines.append(f"  Callback call: {missed_callback}")
    if clid:
        display_clid = f"{prefix_clid_name} {clid}".strip() if prefix_clid_name else clid
        lines.append(f"  Caller ID: {display_clid}")
    if did:
        lines.append(f"  DID: {did}")
    if queue:
        lines.append(f"  Queue: {queue}")
    if user:
        lines.append(f"  Agent: {user}")
    if contact:
        lines.append(f"  Contact: {contact}")
    if duration:
        lines.append(f"  Duration: {duration}s")
    if waiting_time:
        lines.append(f"  Wait time: {waiting_time}s")
    if ringing_time:
        lines.append(f"  Ringing time: {ringing_time}s")
    if hold_time:
        lines.append(f"  Hold time: {hold_time}s")
    if disposition_cause:
        lines.append(f"  Disposition: {disposition_cause}")
    if disconnection_cause:
        lines.append(f"  Disconnection: {disconnection_cause}")
    if pressed_key:
        lines.append(f"  Pressed key: {pressed_key}")
    if attempts:
        lines.append(f"  Failed attempts: {attempts}")
    lines.extend(_format_custom_fields(record))
    lines.extend(_format_extra_fields(record, _CALL_KNOWN_KEYS))
    return "\n".join(lines)


def format_call_list(
    records: list[dict], total: int, skip: int, take: int,
    base_url: str | None = None,
) -> str:
    if not records:
        return "No calls found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} calls:\n"
    body = "\n\n".join(format_call(r, base_url=base_url) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_EMAIL_KNOWN_KEYS = {
    "name", "title", "address", "direction", "state", "answered",
    "queue", "user", "contact", "duration", "wait_time", "time", "text",
}


def format_email(record: dict, base_url: str | None = None, detail: bool = False) -> str:
    name = record.get("name", "?")
    title = record.get("title", "")
    address = record.get("address", "")
    direction = record.get("direction", "")
    state = record.get("state", "")
    answered = record.get("answered")
    queue = _extract_name(record.get("queue"))
    user = _extract_name(record.get("user"))
    contact = _extract_name(record.get("contact"))
    duration = record.get("duration", "")
    wait_time = record.get("wait_time", "")
    created = record.get("time", "")
    raw_text = record.get("text") or ""
    text = raw_text.strip() if detail else _truncate(raw_text, 500)

    # Extract ticket reference from linked activities
    ticket_name = _extract_ticket_from_activities(record.get("activities"))
    ticket_url = _ticket_url(base_url, ticket_name)

    lines = [f"**{name}**"]
    if title:
        lines[0] += f" - {title}"
    if address:
        lines.append(f"  Address: {address}")
    if direction:
        lines.append(f"  Direction: {direction}")
    if state:
        lines.append(f"  State: {state}")
    if answered is not None:
        lines.append(f"  Answered: {'Yes' if answered else 'No'}")
    if queue:
        lines.append(f"  Queue: {queue}")
    if user:
        lines.append(f"  Agent: {user}")
    if contact:
        lines.append(f"  Contact: {contact}")
    if ticket_name:
        ticket_display = _linked_name(ticket_name, ticket_url)
        lines.append(f"  Ticket: {ticket_display}")
    if duration:
        lines.append(f"  Duration: {duration}s")
    if wait_time:
        lines.append(f"  Wait time: {wait_time}s")
    if created:
        lines.append(f"  Created: {created}")
    if text:
        lines.append(f"  Body: {text}")
    lines.extend(_format_custom_fields(record))
    lines.extend(_format_extra_fields(record, _EMAIL_KNOWN_KEYS))
    return "\n".join(lines)


def format_email_list(
    records: list[dict], total: int, skip: int, take: int,
    base_url: str | None = None,
) -> str:
    if not records:
        return "No emails found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} emails:\n"
    body = "\n\n".join(format_email(r, base_url=base_url) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_CHAT_KNOWN_KEYS = {
    "name", "title", "sender", "direction", "state", "answered",
    "queue", "user", "contact", "duration", "wait_time", "disconnection",
    "missed", "type", "time",
}


def format_chat(record: dict, channel: str = "chat", base_url: str | None = None) -> str:
    name = record.get("name", "?")
    title = record.get("title", "")
    sender = record.get("sender", "")
    direction = record.get("direction", "")
    state = record.get("state", "")
    answered = record.get("answered")
    queue = _extract_name(record.get("queue"))
    user = _extract_name(record.get("user"))
    contact = _extract_name(record.get("contact"))
    duration = record.get("duration", "")
    wait_time = record.get("wait_time", "")
    disconnection = record.get("disconnection", "")
    missed = record.get("missed")
    chat_type = record.get("type", "")
    created = record.get("time", "")

    # Extract ticket reference from linked activities
    ticket_name = _extract_ticket_from_activities(record.get("activities"))
    ticket_url = _ticket_url(base_url, ticket_name)

    lines = [f"**{name}**"]
    if title:
        lines[0] += f" - {title}"
    if sender:
        lines.append(f"  Sender: {sender}")
    if direction:
        lines.append(f"  Direction: {direction}")
    if state:
        lines.append(f"  State: {state}")
    if chat_type and channel == "instagram":
        lines.append(f"  Type: {chat_type}")
    if answered is not None:
        lines.append(f"  Answered: {'Yes' if answered else 'No'}")
    if missed:
        lines.append(f"  Missed: Yes")
    if queue:
        lines.append(f"  Queue: {queue}")
    if user:
        lines.append(f"  Agent: {user}")
    if contact:
        lines.append(f"  Contact: {contact}")
    if ticket_name:
        ticket_display = _linked_name(ticket_name, ticket_url)
        lines.append(f"  Ticket: {ticket_display}")
    if duration:
        lines.append(f"  Duration: {duration}s")
    if wait_time:
        lines.append(f"  Wait time: {wait_time}s")
    if disconnection:
        lines.append(f"  Disconnection: {disconnection}")
    if created:
        lines.append(f"  Created: {created}")
    lines.extend(_format_custom_fields(record))
    lines.extend(_format_extra_fields(record, _CHAT_KNOWN_KEYS))
    return "\n".join(lines)


def format_chat_list(
    records: list[dict], total: int, skip: int, take: int, entity: str = "chats",
    channel: str = "chat", base_url: str | None = None,
) -> str:
    if not records:
        return f"No {entity} found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} {entity}:\n"
    body = "\n\n".join(format_chat(r, channel=channel, base_url=base_url) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_ACCOUNT_KNOWN_KEYS = {
    "name", "title", "user", "description", "sla", "created", "edited",
}


def format_account(record: dict, base_url: str | None = None, detail: bool = False) -> str:
    name = record.get("name", "?")
    title = record.get("title", "")
    user = _extract_name(record.get("user"))
    raw_desc = record.get("description") or ""
    description = raw_desc.strip() if detail else _truncate(raw_desc)
    sla = _extract_name(record.get("sla"))
    created = record.get("created", "")
    edited = record.get("edited", "")

    lines = [f"**{name}**"]
    if title:
        lines[0] += f" - {title}"
    if user:
        lines.append(f"  Owner: {user}")
    if sla:
        lines.append(f"  SLA: {sla}")
    if created:
        lines.append(f"  Created: {created}")
    if edited:
        lines.append(f"  Last edited: {edited}")
    if description:
        lines.append(f"  Description: {description}")
    lines.extend(_format_custom_fields(record))
    lines.extend(_format_extra_fields(record, _ACCOUNT_KNOWN_KEYS))
    return "\n".join(lines)


def format_account_list(
    records: list[dict], total: int, skip: int, take: int,
    base_url: str | None = None,
) -> str:
    if not records:
        return "No accounts found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} accounts:\n"
    body = "\n\n".join(format_account(r, base_url=base_url) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_CRM_RECORD_KNOWN_KEYS = {
    "name", "title", "type", "user", "contact", "account", "ticket",
    "status", "stage", "created", "edited", "description",
}


def format_crm_record(record: dict, base_url: str | None = None, detail: bool = False) -> str:
    name = record.get("name", "?")
    title = record.get("title", "")
    rec_type = _extract_name(record.get("type"))
    user = _extract_name(record.get("user"))
    contact = _extract_name(record.get("contact"))
    account = _extract_name(record.get("account"))
    ticket = _extract_name(record.get("ticket"))
    status = _extract_name(record.get("status"))
    stage = record.get("stage", "")
    created = record.get("created", "")
    edited = record.get("edited", "")
    raw_desc = record.get("description") or ""
    description = raw_desc.strip() if detail else _truncate(raw_desc)

    lines = [f"**{name}**"]
    if title:
        lines[0] += f" - {title}"
    if rec_type:
        lines.append(f"  Type: {rec_type}")
    if stage:
        lines.append(f"  Stage: {stage}")
    if status:
        lines.append(f"  Status: {status}")
    if user:
        lines.append(f"  Owner: {user}")
    if contact:
        lines.append(f"  Contact: {contact}")
    if account:
        lines.append(f"  Account: {account}")
    if ticket:
        lines.append(f"  Ticket: {ticket}")
    if created:
        lines.append(f"  Created: {created}")
    if edited:
        lines.append(f"  Last edited: {edited}")
    if description:
        lines.append(f"  Description: {description}")
    lines.extend(_format_custom_fields(record))
    lines.extend(_format_extra_fields(record, _CRM_RECORD_KNOWN_KEYS))
    return "\n".join(lines)


def format_crm_record_list(
    records: list[dict], total: int, skip: int, take: int,
    base_url: str | None = None,
) -> str:
    if not records:
        return "No CRM records found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} CRM records:\n"
    body = "\n\n".join(format_crm_record(r, base_url=base_url) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_CAMPAIGN_RECORD_KNOWN_KEYS = {
    "name", "user", "record_type", "contact", "action", "call_id",
    "nextcall", "statuses", "created", "edited",
}


def format_campaign_record(record: dict) -> str:
    name = record.get("name", "?")
    user = _extract_name(record.get("user"))
    record_type = _extract_name(record.get("record_type"))
    contact = _extract_name(record.get("contact"))
    action = record.get("action", "")
    call_id = record.get("call_id", "")
    nextcall = record.get("nextcall", "")
    statuses = _format_statuses(record.get("statuses"))
    created = record.get("created", "")
    edited = record.get("edited", "")

    # Map action codes to labels
    action_labels = {
        "0": "Not assigned", "1": "Ready", "2": "Rescheduled by Dialer",
        "3": "Call in progress", "4": "Hangup", "5": "Done", "6": "Rescheduled",
    }
    action_display = action_labels.get(str(action), str(action)) if action else ""

    lines = [f"**{name}**"]
    if record_type:
        lines.append(f"  Campaign type: {record_type}")
    if action_display:
        lines.append(f"  Action: {action_display}")
    if statuses:
        lines.append(f"  Statuses: {statuses}")
    if user:
        lines.append(f"  Agent: {user}")
    if contact:
        lines.append(f"  Contact: {contact}")
    if call_id:
        lines.append(f"  Call: {call_id}")
    if nextcall:
        lines.append(f"  Next call: {nextcall}")
    if created:
        lines.append(f"  Created: {created}")
    if edited:
        lines.append(f"  Last edited: {edited}")
    lines.extend(_format_custom_fields(record))
    lines.extend(_format_extra_fields(record, _CAMPAIGN_RECORD_KNOWN_KEYS))
    return "\n".join(lines)


def format_campaign_record_list(records: list[dict], total: int, skip: int, take: int) -> str:
    if not records:
        return "No campaign records found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} campaign records:\n"
    body = "\n\n".join(format_campaign_record(r) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


def format_simple_record(record: dict) -> str:
    """Format a simple record (queue, user, category) with name, title, and key metadata."""
    name = record.get("name", "?")
    title = record.get("title", "")
    rec_type = record.get("type", "")
    email = record.get("email", "")
    description = _truncate(record.get("description", ""), 100)

    line = f"**{name}**"
    if title:
        line += f" - {title}"
    if rec_type:
        line += f" [{rec_type}]"
    if email:
        line += f" <{email}>"
    if description:
        line += f" ({description})"
    return line


def format_simple_list(
    records: list[dict], total: int, skip: int, take: int, entity: str
) -> str:
    if not records:
        return f"No {entity} found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} {entity}:\n"
    body = "\n".join(format_simple_record(r) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer


_TRANSCRIPT_KNOWN_KEYS = {"name", "activity", "start", "end", "text", "type"}


def format_transcript(segments: list[dict], activity_name: str | None = None) -> str:
    """Format call transcript segments into a chronological dialogue.

    Each segment has: start (seconds), end (seconds), text, type (customer/operator).
    """
    if not segments:
        return "No transcript available for this call."

    # Sort by start time ascending
    sorted_segs = sorted(segments, key=lambda s: float(s.get("start") or 0))

    lines = []
    if activity_name:
        lines.append(f"**Transcript** ({activity_name})")
    else:
        lines.append("**Transcript**")

    for seg in sorted_segs:
        start = float(seg.get("start") or 0)
        minutes = int(start) // 60
        seconds = int(start) % 60
        timestamp = f"{minutes}:{seconds:02d}"

        seg_type = (seg.get("type") or "").lower()
        speaker = "Customer" if seg_type == "customer" else "Operator"
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(f"  [{timestamp}] {speaker}: {text}")

    # If all segments had empty text, still indicate we got segments
    if len(lines) == 1:
        lines.append("  (transcript segments found but no text content)")

    return "\n".join(lines)


def format_realtime_session(record: dict) -> str:
    agent = _extract_name(record.get("id_agent"))
    state = record.get("state", "")
    exten = record.get("exten", "")
    exten_status = record.get("exten_status", "")
    logintime = record.get("logintime", "")
    lastcalltime = record.get("lastcalltime", "")
    statetime = record.get("statetime", "")
    pause_type = _extract_name(record.get("id_pause"))
    onpause = record.get("onpause", "")

    lines = [f"**{agent or '?'}**"]
    if state:
        lines.append(f"  State: {state}")
    if pause_type:
        lines.append(f"  Pause: {pause_type}")
    if onpause:
        lines.append(f"  Pause since: {onpause}")
    if exten:
        status = f" ({exten_status})" if exten_status else ""
        lines.append(f"  Extension: {exten}{status}")
    if logintime:
        lines.append(f"  Login time: {logintime}")
    if lastcalltime:
        lines.append(f"  Last call: {lastcalltime}")
    if statetime:
        lines.append(f"  In state since: {statetime}")
    return "\n".join(lines)


def format_realtime_session_list(records: list[dict], total: int, skip: int, take: int) -> str:
    if not records:
        return "No active sessions found."

    header = f"Showing {skip + 1}-{skip + len(records)} of {total} active sessions:\n"
    body = "\n\n".join(format_realtime_session(r) for r in records)
    footer = ""
    if skip + len(records) < total:
        footer = f"\n\n(Use skip={skip + len(records)} to see next page)"
    return header + body + footer
