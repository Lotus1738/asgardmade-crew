"""
Seasonal / holiday calendar for AsgardMade POD niche research.
HEIMDALL uses this to shift research toward upcoming demand spikes
so listings go live 4-6 weeks before peak search volume.
"""
from __future__ import annotations


from datetime import date, timedelta

CALENDAR = [
    {"name": "Valentine's Day",     "month": 2,  "day": 14, "lead_weeks": 5, "emoji": "❤️",
     "niches": ["love", "couples", "heart", "romantic gifts", "galentines"]},
    {"name": "St. Patrick's Day",   "month": 3,  "day": 17, "lead_weeks": 3, "emoji": "☘️",
     "niches": ["irish", "lucky", "shamrock", "green aesthetic"]},
    {"name": "Easter",              "month": 4,  "day": 20, "lead_weeks": 4, "emoji": "🐣",
     "niches": ["spring", "pastel", "bunny", "easter gifts"]},
    {"name": "Mother's Day",        "month": 5,  "day": 11, "lead_weeks": 5, "emoji": "🌸",
     "niches": ["mom gifts", "mama bear", "floral", "mothers day"]},
    {"name": "Teacher Appreciation","month": 5,  "day": 6,  "lead_weeks": 3, "emoji": "🍎",
     "niches": ["teacher gifts", "back to school", "educator"]},
    {"name": "Nurse Week",          "month": 5,  "day": 12, "lead_weeks": 3, "emoji": "🏥",
     "niches": ["nurse gifts", "healthcare worker", "nurse life", "rn"]},
    {"name": "Graduation Season",   "month": 5,  "day": 15, "lead_weeks": 6, "emoji": "🎓",
     "niches": ["graduation gifts", "class of 2026", "congrats grad", "senior year"]},
    {"name": "Father's Day",        "month": 6,  "day": 15, "lead_weeks": 5, "emoji": "🎣",
     "niches": ["dad gifts", "fishing", "grilling", "fathers day"]},
    {"name": "4th of July",         "month": 7,  "day": 4,  "lead_weeks": 4, "emoji": "🇺🇸",
     "niches": ["patriotic", "american flag", "summer bbq", "freedom"]},
    {"name": "Back to School",      "month": 8,  "day": 15, "lead_weeks": 5, "emoji": "📚",
     "niches": ["school supplies", "student life", "college dorm", "back to school"]},
    {"name": "Halloween",           "month": 10, "day": 31, "lead_weeks": 6, "emoji": "🎃",
     "niches": ["halloween", "spooky", "witch aesthetic", "gothic", "skull"]},
    {"name": "Thanksgiving",        "month": 11, "day": 27, "lead_weeks": 4, "emoji": "🍂",
     "niches": ["thankful", "fall aesthetic", "pumpkin spice", "harvest"]},
    {"name": "Christmas",           "month": 12, "day": 25, "lead_weeks": 8, "emoji": "🎄",
     "niches": ["christmas gifts", "holiday", "winter cozy", "santa", "ugly sweater"]},
    {"name": "New Year",            "month": 1,  "day": 1,  "lead_weeks": 3, "emoji": "🎆",
     "niches": ["new year new me", "resolution", "2026", "fresh start"]},
]


def _event_date(event: dict, today: date | None = None) -> date:
    """Return the next occurrence of this event's month/day on or after today."""
    if today is None:
        today = date.today()
    year = today.year
    d = date(year, event["month"], event["day"])
    if d < today:
        d = date(year + 1, event["month"], event["day"])
    return d


def get_upcoming_events(weeks_ahead: int = 8) -> list[dict]:
    """
    Return events whose peak date falls within the next `weeks_ahead` weeks,
    sorted by urgency (soonest first). Each returned dict includes the original
    event fields plus 'weeks_away' and 'peak_date'.
    """
    today = date.today()
    cutoff = today + timedelta(weeks=weeks_ahead)
    upcoming = []
    for event in CALENDAR:
        peak = _event_date(event, today)
        if peak <= cutoff:
            weeks_away = (peak - today).days / 7
            upcoming.append({**event, "peak_date": peak, "weeks_away": round(weeks_away, 1)})
    upcoming.sort(key=lambda e: e["peak_date"])
    return upcoming


def get_seasonal_niches_for_prompt() -> str:
    """
    Format upcoming events as a text block for HEIMDALL's context.
    Example output:
        🎣 Father's Day (0.1 weeks away) — push: dad gifts, fishing, grilling, fathers day
        🇺🇸 4th of July (2.9 weeks away) — push: patriotic, american flag, summer bbq, freedom
    """
    events = get_upcoming_events(weeks_ahead=8)
    if not events:
        return ""
    lines = []
    for e in events:
        niche_list = ", ".join(e["niches"])
        emoji = e.get("emoji", "📅")
        lines.append(
            f"{emoji} {e['name']} ({e['weeks_away']} weeks away) — push: {niche_list}"
        )
    return "\n".join(lines)


def get_priority_boost(niche: str) -> float:
    """
    Return a score multiplier (1.0–2.0) if the niche matches an upcoming event.
    2.0  = event is within 4 weeks (urgent)
    1.5  = event is 4–6 weeks away
    1.2  = event is 6–8 weeks away
    1.0  = no seasonal match or event >8 weeks away
    Matching is case-insensitive substring check against event niche keywords.
    """
    boost, _ = get_boost_details(niche)
    return boost


def get_boost_details(niche: str) -> tuple[float, str]:
    """
    Return (boost_multiplier, event_name) for a given niche string.
    boost_multiplier is 1.0 if no seasonal match.
    event_name is "" if no match.
    """
    niche_lower = niche.lower()
    events = get_upcoming_events(weeks_ahead=8)
    best_boost = 1.0
    best_event = ""
    for event in events:
        # Check if any of the event's niche keywords appear in the given niche string
        for keyword in event["niches"]:
            if keyword.lower() in niche_lower or niche_lower in keyword.lower():
                weeks = event["weeks_away"]
                if weeks <= 4:
                    boost = 2.0
                elif weeks <= 6:
                    boost = 1.5
                else:
                    boost = 1.2
                if boost > best_boost:
                    best_boost = boost
                    best_event = event["name"]
                break
    return best_boost, best_event
