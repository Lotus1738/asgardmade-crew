"""
Google Calendar integration — list events, create events, get today's schedule.

Uses Google Calendar API with service account or OAuth credentials.
Service account must be granted access to the calendar (share the calendar with the SA email).
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = lambda: os.getenv("GOOGLE_CALENDAR_ID", "primary")


def _get_service():
    from integrations.google import get_credentials
    from googleapiclient.discovery import build
    creds = get_credentials(SCOPES)
    if not creds:
        return None
    try:
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"[CALENDAR] build error: {e}")
        return None


def get_today_events() -> list[dict]:
    """Return today's events from Google Calendar."""
    svc = _get_service()
    if not svc:
        return []
    try:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        result = svc.events().list(
            calendarId=CALENDAR_ID(),
            timeMin=start_of_day,
            timeMax=end_of_day,
            maxResults=20,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return _format_events(result.get("items", []))
    except Exception as e:
        print(f"[CALENDAR] get_today error: {e}")
        return []


def get_upcoming_events(days: int = 7, limit: int = 10) -> list[dict]:
    """Return upcoming events for the next N days."""
    svc = _get_service()
    if not svc:
        return []
    try:
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)
        result = svc.events().list(
            calendarId=CALENDAR_ID(),
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=limit,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return _format_events(result.get("items", []))
    except Exception as e:
        print(f"[CALENDAR] get_upcoming error: {e}")
        return []


def create_event(
    title: str,
    start: datetime,
    end: Optional[datetime] = None,
    description: str = "",
    location: str = "",
) -> Optional[dict]:
    """Create a calendar event. Returns the created event or None."""
    svc = _get_service()
    if not svc:
        return None
    if end is None:
        end = start + timedelta(hours=1)
    try:
        body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start.isoformat(), "timeZone": "America/New_York"},
            "end": {"dateTime": end.isoformat(), "timeZone": "America/New_York"},
        }
        event = svc.events().insert(calendarId=CALENDAR_ID(), body=body).execute()
        return {
            "id": event.get("id"),
            "title": event.get("summary"),
            "start": event.get("start", {}).get("dateTime"),
            "link": event.get("htmlLink"),
        }
    except Exception as e:
        print(f"[CALENDAR] create_event error: {e}")
        return None


def create_reminder(title: str, when: datetime, description: str = "") -> Optional[dict]:
    """Create a 15-minute reminder event."""
    return create_event(title, when, when + timedelta(minutes=15), description)


def _format_events(items: list) -> list[dict]:
    events = []
    for item in items:
        start = item.get("start", {})
        time_str = start.get("dateTime", start.get("date", ""))
        events.append({
            "id": item.get("id"),
            "title": item.get("summary", "Untitled"),
            "start": time_str,
            "end": item.get("end", {}).get("dateTime", ""),
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "link": item.get("htmlLink", ""),
        })
    return events


def calendar_available() -> bool:
    from integrations.google import has_any_credentials
    return has_any_credentials()
