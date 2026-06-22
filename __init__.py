"""
tools/
------
All tools available to Jarvis, each as a callable async function.
Tool schemas (for OpenAI function calling) are defined at the bottom.
"""

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
import pendulum
from loguru import logger

from config.settings import settings
from memory.store import store_memory, search_memories, set_fact, get_fact, add_reminder


# ── Memory tools ─────────────────────────────────────────────────────────────

async def tool_remember(text: str, key: str | None = None) -> str:
    """Store something in memory."""
    store_memory(text)
    if key:
        await set_fact(key, text)
    return f"Got it, I'll remember that."


async def tool_recall(query: str) -> str:
    """Search memory for something."""
    results = search_memories(query, n_results=5)
    if not results:
        return "I don't have anything stored about that."
    lines = [r["text"] for r in results]
    return "Here's what I remember: " + ". ".join(lines)


# ── Calendar tools ────────────────────────────────────────────────────────────

def _get_calendar_service():
    """Lazy-load Google Calendar service."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.google_credentials_path,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    return build("calendar", "v3", credentials=creds)


async def tool_add_calendar_event(
    title: str,
    start_datetime: str,   # ISO 8601
    end_datetime: str,     # ISO 8601
    description: str = "",
    location: str = "",
) -> str:
    try:
        service = _get_calendar_service()
        event = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_datetime, "timeZone": settings.timezone},
            "end": {"dateTime": end_datetime, "timeZone": settings.timezone},
        }
        created = service.events().insert(
            calendarId=settings.google_calendar_id, body=event
        ).execute()
        logger.info(f"Calendar event created: {title}")
        return f"Done. '{title}' added to your calendar."
    except Exception as e:
        logger.error(f"Calendar add error: {e}")
        return f"Sorry, I couldn't add that to your calendar: {e}"


async def tool_get_calendar_events(days_ahead: int = 1) -> str:
    try:
        service = _get_calendar_service()
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
        service = _get_calendar_service()
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
        event = events[0]  # delete first match
        service.events().delete(
            calendarId=settings.google_calendar_id, eventId=event["id"]
        ).execute()
        return f"Deleted '{event['summary']}' from your calendar."
    except Exception as e:
        return f"Couldn't delete that event: {e}"


# ── SMS tools ─────────────────────────────────────────────────────────────────

async def tool_send_sms(message: str) -> str:
    from twilio.rest import Client
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    try:
        msg = client.messages.create(
            body=message,
            from_=settings.twilio_phone_number,
            to=settings.your_phone_number,
        )
        logger.info(f"SMS sent: {msg.sid}")
        return "Message sent."
    except Exception as e:
        logger.error(f"SMS error: {e}")
        return f"Couldn't send the message: {e}"


async def tool_schedule_reminder(message: str, remind_at: str) -> str:
    """Schedule a future SMS. remind_at is ISO 8601."""
    try:
        fire_dt = pendulum.parse(remind_at, tz=settings.timezone)
        rem_id = await add_reminder(message, fire_dt)
        time_str = fire_dt.format("dddd [the] Do [at] h:mm A")
        return f"Reminder set for {time_str}."
    except Exception as e:
        return f"Couldn't schedule that reminder: {e}"


# ── Weather tool ──────────────────────────────────────────────────────────────

async def tool_get_weather(location: str = "", forecast_days: int = 1) -> str:
    if not settings.openweather_api_key:
        return "Weather is not configured — add an OpenWeatherMap API key."
    loc = location or await get_fact("user.location") or "London"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": loc,
                "appid": settings.openweather_api_key,
                "units": "metric",
                "cnt": forecast_days * 8,
            },
        )
    data = resp.json()
    if data.get("cod") != "200":
        return f"Couldn't get weather for {loc}."
    first = data["list"][0]
    temp = round(first["main"]["temp"])
    desc = first["weather"][0]["description"]
    return f"In {loc} right now: {temp}°C and {desc}."


# ── Notes tool ────────────────────────────────────────────────────────────────

import os
from pathlib import Path

NOTES_DIR = Path("./data/notes")


async def tool_take_note(note: str) -> str:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = NOTES_DIR / f"{ts}.md"
    path.write_text(f"# Note — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{note}\n")
    return "Note saved."


async def tool_read_notes(limit: int = 5) -> str:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(NOTES_DIR.glob("*.md"), reverse=True)[:limit]
    if not files:
        return "You have no notes yet."
    parts = []
    for f in files:
        content = f.read_text().strip()
        parts.append(content)
    return "\n\n---\n\n".join(parts)


# ── Tool registry + OpenAI schemas ───────────────────────────────────────────

TOOL_HANDLERS: dict[str, Any] = {
    "remember": tool_remember,
    "recall": tool_recall,
    "add_calendar_event": tool_add_calendar_event,
    "get_calendar_events": tool_get_calendar_events,
    "delete_calendar_event": tool_delete_calendar_event,
    "send_sms": tool_send_sms,
    "schedule_reminder": tool_schedule_reminder,
    "get_weather": tool_get_weather,
    "take_note": tool_take_note,
    "read_notes": tool_read_notes,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "remember",
        "description": "Store a fact or piece of information in long-term memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The information to remember."},
                "key": {"type": "string", "description": "Optional short key for structured lookup (e.g. 'user.birthday')."},
            },
            "required": ["text"],
        },
    },
    {
        "type": "function",
        "name": "recall",
        "description": "Search long-term memory for information on a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "add_calendar_event",
        "description": "Add an event to the user's Google Calendar.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_datetime": {"type": "string", "description": "ISO 8601 datetime"},
                "end_datetime": {"type": "string", "description": "ISO 8601 datetime"},
                "description": {"type": "string"},
                "location": {"type": "string"},
            },
            "required": ["title", "start_datetime", "end_datetime"],
        },
    },
    {
        "type": "function",
        "name": "get_calendar_events",
        "description": "Fetch upcoming calendar events.",
        "parameters": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "How many days to look ahead (default 1 = today only)."},
            },
        },
    },
    {
        "type": "function",
        "name": "delete_calendar_event",
        "description": "Delete a calendar event by searching for its title.",
        "parameters": {
            "type": "object",
            "properties": {
                "title_keyword": {"type": "string", "description": "Part of the event title to search for."},
            },
            "required": ["title_keyword"],
        },
    },
    {
        "type": "function",
        "name": "send_sms",
        "description": "Send the user a text message immediately.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
    {
        "type": "function",
        "name": "schedule_reminder",
        "description": "Schedule a future SMS reminder for the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The reminder text to send."},
                "remind_at": {"type": "string", "description": "ISO 8601 datetime for when to send it."},
            },
            "required": ["message", "remind_at"],
        },
    },
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather or a short forecast.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name (defaults to user's home location)."},
                "forecast_days": {"type": "integer", "description": "Days ahead (1 = today only)."},
            },
        },
    },
    {
        "type": "function",
        "name": "take_note",
        "description": "Save a quick note.",
        "parameters": {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
            },
            "required": ["note"],
        },
    },
    {
        "type": "function",
        "name": "read_notes",
        "description": "Read back recent notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many recent notes to return (default 5)."},
            },
        },
    },
]
