"""
voice/tools/calendar_tool.py
-----------------------------
Google Calendar read/write via service account credentials.
"""
from datetime import datetime, timedelta

import pendulum
from loguru import logger

from voice.config import settings


def _get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.google_credentials_path,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


async def tool_add_calendar_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    description: str = "",
    location: str = "",
) -> str:
    try:
        service = _get_service()
        event = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_datetime, "timeZone": settings.timezone},
            "end": {"dateTime": end_datetime, "timeZone": settings.timezone},
        }
        service.events().insert(calendarId=settings.google_calendar_id, body=event).execute()
        return f"Done. '{title}' added to your calendar."
    except Exception as e:
        logger.error(f"Calendar add error: {e}")
        return f"Sorry, I couldn't add that to your calendar: {e}"


async def tool_get_calendar_events(days_ahead: int = 1) -> str:
    try:
        service = _get_service()
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
        result = service.events().list(
            calendarId=settings.google_calendar_id,
            timeMin=now,
            timeMax=end,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = result.get("items", [])
        if not events:
            word = "today" if days_ahead == 1 else f"the next {days_ahead} days"
            return f"You have nothing scheduled for {word}."
        lines = []
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", ""))
            try:
                dt = pendulum.parse(start, tz=settings.timezone)
                time_str = dt.format("dddd [the] Do [at] h:mm A")
            except Exception:
                time_str = start
            lines.append(f"{time_str}: {e['summary']}")
        return "Here's what's on: " + ". ".join(lines)
    except Exception as e:
        logger.error(f"Calendar get error: {e}")
        return f"Couldn't fetch your calendar: {e}"


async def tool_delete_calendar_event(title_keyword: str) -> str:
    try:
        service = _get_service()
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
        result = service.events().list(
            calendarId=settings.google_calendar_id,
            timeMin=now,
            timeMax=end,
            q=title_keyword,
            singleEvents=True,
        ).execute()
        events = result.get("items", [])
        if not events:
            return f"I couldn't find any event matching '{title_keyword}'."
        event = events[0]
        service.events().delete(
            calendarId=settings.google_calendar_id, eventId=event["id"]
        ).execute()
        return f"Deleted '{event['summary']}' from your calendar."
    except Exception as e:
        return f"Couldn't delete that event: {e}"
