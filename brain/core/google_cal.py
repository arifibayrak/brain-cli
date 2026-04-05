"""
Google Calendar integration.

Setup:
1. Go to https://console.cloud.google.com/
2. Create a project → enable Google Calendar API
3. Create OAuth2 credentials (Desktop app) → download JSON
4. Run `brain setup` and provide the path to the downloaded JSON

The first run will open a browser for OAuth consent.
Token is cached at ~/.brain/credentials/google_token.json
"""
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from brain import config

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _get_service():
    creds_path = Path(config.get("google_credentials_path", ""))
    token_path = Path(config.get("google_token_path", ""))

    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google OAuth credentials not found at {creds_path}.\n"
            "Run: brain setup --google"
        )

    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def is_enabled() -> bool:
    return bool(config.get("google_calendar_enabled", False))


def get_today_events() -> list[dict]:
    """Return today's calendar events sorted by start time."""
    if not is_enabled():
        return []
    try:
        service = _get_service()
        today = date.today()
        time_min = datetime(today.year, today.month, today.day,
                            tzinfo=timezone.utc).isoformat()
        time_max = datetime(today.year, today.month, today.day, 23, 59, 59,
                            tzinfo=timezone.utc).isoformat()

        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = []
        for e in result.get("items", []):
            start = e["start"].get("dateTime", e["start"].get("date", ""))
            end = e["end"].get("dateTime", e["end"].get("date", ""))
            events.append({
                "id": e["id"],
                "summary": e.get("summary", "(no title)"),
                "start": start,
                "end": end,
                "description": e.get("description", ""),
                "location": e.get("location", ""),
            })
        return events
    except Exception as e:
        return []


def get_upcoming_events(days: int = 7) -> list[dict]:
    """Return upcoming events for the next N days."""
    if not is_enabled():
        return []
    try:
        service = _get_service()
        now = datetime.now(timezone.utc)
        time_max = (now + timedelta(days=days)).isoformat()

        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        ).execute()

        events = []
        for e in result.get("items", []):
            start = e["start"].get("dateTime", e["start"].get("date", ""))
            events.append({
                "id": e["id"],
                "summary": e.get("summary", "(no title)"),
                "start": start,
                "end": e["end"].get("dateTime", e["end"].get("date", "")),
            })
        return events
    except Exception:
        return []


def create_event(summary: str, date_str: str, start_time: str = "",
                 end_time: str = "", description: str = "", location: str = "") -> dict:
    """
    Create a calendar event.
    date_str: YYYY-MM-DD
    start_time / end_time: HH:MM (if omitted, creates an all-day event)
    Returns the created event dict with id, summary, start.
    """
    service = _get_service()

    if start_time:
        # Timed event — use local timezone
        import subprocess
        try:
            tz = subprocess.check_output(
                ["readlink", "/etc/localtime"], text=True
            ).strip().split("zoneinfo/")[-1]
        except Exception:
            tz = "UTC"

        start_dt = f"{date_str}T{start_time}:00"
        end_dt = f"{date_str}T{end_time}:00" if end_time else f"{date_str}T{start_time}:00"
        body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_dt, "timeZone": tz},
            "end": {"dateTime": end_dt, "timeZone": tz},
        }
    else:
        # All-day event
        body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"date": date_str},
            "end": {"date": date_str},
        }

    event = service.events().insert(calendarId="primary", body=body).execute()
    return {
        "id": event["id"],
        "summary": event.get("summary", ""),
        "start": event["start"].get("dateTime", event["start"].get("date", "")),
        "link": event.get("htmlLink", ""),
    }


def format_event_time(start: str) -> str:
    """Format an event start time as 'HH:MM' or 'All day'."""
    if "T" in start:
        try:
            dt = datetime.fromisoformat(start)
            return dt.strftime("%H:%M")
        except Exception:
            return start
    return "All day"
