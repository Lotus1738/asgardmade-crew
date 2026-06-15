"""
Google Suite skill pack — Gmail, Calendar, Drive, Sheets operations as runnable skills.
Only registers if Google credentials are available.
"""

from skills import SkillMeta, SkillResult, register
from datetime import datetime


async def _read_inbox(args: dict) -> SkillResult:
    from integrations.google.gmail import get_inbox, gmail_available
    if not gmail_available():
        return SkillResult(success=False, output=None, error="Gmail not configured (set GMAIL_USER + GMAIL_APP_PASSWORD)")
    limit = int(args.get("limit", 10))
    emails = get_inbox(limit=limit)
    return SkillResult(
        success=True,
        output=emails,
        summary=f"Retrieved {len(emails)} emails from inbox",
    )


async def _search_email(args: dict) -> SkillResult:
    from integrations.google.gmail import search_emails, gmail_available
    if not gmail_available():
        return SkillResult(success=False, output=None, error="Gmail not configured")
    query = args.get("query", "")
    if not query:
        return SkillResult(success=False, output=None, error="query is required")
    results = search_emails(query, limit=int(args.get("limit", 5)))
    return SkillResult(success=True, output=results, summary=f"Found {len(results)} emails matching '{query}'")


async def _send_email(args: dict) -> SkillResult:
    from integrations.google.gmail import send_email, gmail_available
    if not gmail_available():
        return SkillResult(success=False, output=None, error="Gmail not configured")
    to = args.get("to", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    if not to or not subject or not body:
        return SkillResult(success=False, output=None, error="to, subject, and body are required")
    ok = await send_email(to, subject, body)
    return SkillResult(success=ok, output={"sent": ok, "to": to, "subject": subject},
                       summary=f"Email {'sent' if ok else 'FAILED'}: '{subject}' to {to}")


async def _get_calendar(args: dict) -> SkillResult:
    from integrations.google.calendar import get_upcoming_events, calendar_available
    if not calendar_available():
        return SkillResult(success=False, output=None, error="Google Calendar not configured (set GOOGLE_SERVICE_ACCOUNT_JSON)")
    days = int(args.get("days", 7))
    events = get_upcoming_events(days=days)
    return SkillResult(success=True, output=events, summary=f"Found {len(events)} upcoming events")


async def _create_event(args: dict) -> SkillResult:
    from integrations.google.calendar import create_event, calendar_available
    if not calendar_available():
        return SkillResult(success=False, output=None, error="Google Calendar not configured")
    title = args.get("title", "")
    start_str = args.get("start", "")
    if not title or not start_str:
        return SkillResult(success=False, output=None, error="title and start (ISO datetime) are required")
    try:
        start = datetime.fromisoformat(start_str)
    except Exception:
        return SkillResult(success=False, output=None, error=f"Invalid start datetime: {start_str}")
    event = create_event(title, start, description=args.get("description", ""))
    if event:
        return SkillResult(success=True, output=event, summary=f"Created event: '{title}'")
    return SkillResult(success=False, output=None, error="Failed to create event")


async def _list_drive_files(args: dict) -> SkillResult:
    from integrations.google.drive import list_files, drive_available
    if not drive_available():
        return SkillResult(success=False, output=None, error="Google Drive not configured")
    files = list_files(limit=int(args.get("limit", 20)), query=args.get("query", ""))
    return SkillResult(success=True, output=files, summary=f"Found {len(files)} files in Drive")


async def _upload_to_drive(args: dict) -> SkillResult:
    from integrations.google.drive import upload_text, drive_available
    if not drive_available():
        return SkillResult(success=False, output=None, error="Google Drive not configured")
    name = args.get("name", "")
    content = args.get("content", "")
    if not name or not content:
        return SkillResult(success=False, output=None, error="name and content are required")
    result = upload_text(name, content)
    if result:
        return SkillResult(success=True, output=result, summary=f"Uploaded '{name}' to Drive")
    return SkillResult(success=False, output=None, error="Upload failed")


async def _read_sheet(args: dict) -> SkillResult:
    from integrations.google.sheets import read_range, sheets_available
    if not sheets_available():
        return SkillResult(success=False, output=None, error="Google Sheets not configured (set GOOGLE_SERVICE_ACCOUNT_JSON + GOOGLE_SHEETS_ID)")
    range_ = args.get("range", "Sheet1!A1:Z100")
    data = read_range(range_)
    return SkillResult(success=True, output=data, summary=f"Read {len(data)} rows from {range_}")


async def _append_to_sheet(args: dict) -> SkillResult:
    from integrations.google.sheets import append_rows, sheets_available
    if not sheets_available():
        return SkillResult(success=False, output=None, error="Google Sheets not configured")
    sheet = args.get("sheet", "Sheet1")
    rows = args.get("rows", [])
    if not rows:
        return SkillResult(success=False, output=None, error="rows is required")
    ok = append_rows(sheet, rows)
    return SkillResult(success=ok, output={"appended": ok, "rows": len(rows)},
                       summary=f"{'Appended' if ok else 'FAILED'} {len(rows)} rows to '{sheet}'")


def register_all():
    register(SkillMeta(
        name="gmail_inbox",
        description="Read recent emails from your Gmail inbox",
        pack="google",
        fn=_read_inbox,
        args_schema={"limit": "Number of emails to fetch (default 10)"},
        tags=["gmail", "email", "inbox"],
        icon="📬",
    ))
    register(SkillMeta(
        name="gmail_search",
        description="Search your Gmail by keyword",
        pack="google",
        fn=_search_email,
        args_schema={"query": "Search query", "limit": "Max results"},
        tags=["gmail", "search"],
        icon="📭",
    ))
    register(SkillMeta(
        name="gmail_send",
        description="Send an email via Gmail",
        pack="google",
        fn=_send_email,
        args_schema={"to": "Recipient email", "subject": "Subject line", "body": "Email body"},
        tags=["gmail", "send", "email"],
        icon="📤",
    ))
    register(SkillMeta(
        name="calendar_upcoming",
        description="Get upcoming Google Calendar events",
        pack="google",
        fn=_get_calendar,
        args_schema={"days": "Days ahead to look (default 7)"},
        tags=["calendar", "schedule"],
        icon="📅",
    ))
    register(SkillMeta(
        name="calendar_create",
        description="Create a new Google Calendar event",
        pack="google",
        fn=_create_event,
        args_schema={"title": "Event title", "start": "ISO datetime (e.g. 2025-06-15T14:00:00)",
                     "description": "Optional description"},
        tags=["calendar", "event", "schedule"],
        icon="📆",
    ))
    register(SkillMeta(
        name="drive_list",
        description="List files in your Google Drive",
        pack="google",
        fn=_list_drive_files,
        args_schema={"limit": "Max files to list", "query": "Optional name filter"},
        tags=["drive", "files"],
        icon="💾",
    ))
    register(SkillMeta(
        name="drive_upload",
        description="Upload a text file to Google Drive",
        pack="google",
        fn=_upload_to_drive,
        args_schema={"name": "File name (e.g. 'report.md')", "content": "Text content"},
        tags=["drive", "upload"],
        icon="⬆️",
    ))
    register(SkillMeta(
        name="sheets_read",
        description="Read data from a Google Sheets range",
        pack="google",
        fn=_read_sheet,
        args_schema={"range": "Sheet range (e.g. 'Sheet1!A1:D10')"},
        tags=["sheets", "data"],
        icon="📊",
    ))
    register(SkillMeta(
        name="sheets_append",
        description="Append rows to a Google Sheet",
        pack="google",
        fn=_append_to_sheet,
        args_schema={"sheet": "Sheet tab name", "rows": "List of row arrays"},
        tags=["sheets", "data", "write"],
        icon="📋",
    ))
