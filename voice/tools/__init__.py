"""
voice/tools/__init__.py
-----------------------
Central tool registry. Import handlers and schemas from here.
"""
import json
from typing import Any

from loguru import logger

from voice.tools.memory_tool import tool_remember, tool_recall
from voice.tools.calendar_tool import (
    tool_add_calendar_event,
    tool_get_calendar_events,
    tool_delete_calendar_event,
)
from voice.tools.sms_tool import tool_send_sms, tool_schedule_reminder
from voice.tools.weather_tool import tool_get_weather
from voice.tools.notes_tool import tool_take_note, tool_read_notes
from voice.tools.n8n_tool import tool_trigger_background_task


# ── Dispatcher ────────────────────────────────────────────────────────────────

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
    "trigger_background_task": tool_trigger_background_task,
}


async def dispatch(name: str, arguments: str | dict) -> str:
    if name not in TOOL_HANDLERS:
        return f"Unknown tool: {name}"
    handler = TOOL_HANDLERS[name]
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        result = await handler(**args)
        return result
    except Exception as e:
        logger.error(f"Tool '{name}' raised: {e}")
        return f"Tool error: {e}"


# ── Schemas (Anthropic-style function definitions) ─────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "remember",
        "description": "Store a fact or piece of information in long-term memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The information to remember."},
                "key": {"type": "string", "description": "Optional short key for structured lookup (e.g. 'user.birthday')."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "recall",
        "description": "Search long-term memory for information on a topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_calendar_event",
        "description": "Add an event to the user's Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_datetime": {"type": "string", "description": "ISO 8601 datetime."},
                "end_datetime": {"type": "string", "description": "ISO 8601 datetime."},
                "description": {"type": "string"},
                "location": {"type": "string"},
            },
            "required": ["title", "start_datetime", "end_datetime"],
        },
    },
    {
        "name": "get_calendar_events",
        "description": "Fetch upcoming calendar events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "How many days ahead to look (default 1 = today)."},
            },
        },
    },
    {
        "name": "delete_calendar_event",
        "description": "Delete a calendar event by searching for its title.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title_keyword": {"type": "string", "description": "Part of the event title to search for."},
            },
            "required": ["title_keyword"],
        },
    },
    {
        "name": "send_sms",
        "description": "Send the user a text message immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "schedule_reminder",
        "description": "Schedule a future SMS reminder for the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The reminder text to send."},
                "remind_at": {"type": "string", "description": "ISO 8601 datetime for when to send it."},
            },
            "required": ["message", "remind_at"],
        },
    },
    {
        "name": "get_weather",
        "description": "Get current weather or a short forecast.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name (defaults to user's home location)."},
                "forecast_days": {"type": "integer", "description": "Days ahead (1 = today only)."},
            },
        },
    },
    {
        "name": "take_note",
        "description": "Save a quick note.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
            },
            "required": ["note"],
        },
    },
    {
        "name": "read_notes",
        "description": "Read back recent notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many recent notes to return (default 5)."},
            },
        },
    },
    {
        "name": "trigger_background_task",
        "description": (
            "Trigger an async background task. Friday responds immediately; "
            "n8n runs the task and texts you when done. "
            "Use for: web research, data analysis, email drafting, "
            "or any multi-step task that takes more than 30 seconds."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_name": {
                    "type": "string",
                    "enum": ["research", "calendar_analysis", "draft_email", "custom"],
                    "description": "Which n8n workflow to trigger.",
                },
                "task_description": {
                    "type": "string",
                    "description": "Plain English description of what to do.",
                },
                "params": {
                    "type": "object",
                    "description": "Task-specific parameters (e.g. search query, topic, date range).",
                },
            },
            "required": ["task_name", "task_description"],
        },
    },
]
