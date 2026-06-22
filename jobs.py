"""
scheduler/jobs.py
-----------------
APScheduler jobs that run in the background:
  - Morning briefing SMS
  - Reminder poll (fires pending reminders)
  - Evening digest (optional)
"""

from datetime import datetime, timedelta

import pendulum
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from config.settings import settings
from memory.store import get_pending_reminders, mark_reminder_sent
from tools import tool_send_sms, tool_get_calendar_events, tool_get_weather


scheduler = AsyncIOScheduler(timezone=settings.timezone)


async def send_morning_briefing():
    logger.info("Sending morning briefing SMS...")
    tz = settings.timezone
    today = pendulum.now(tz).format("dddd, MMMM Do")

    parts = [f"Good morning! Here's your briefing for {today}."]

    # Calendar
    try:
        cal = await tool_get_calendar_events(days_ahead=1)
        parts.append(cal)
    except Exception as e:
        logger.warning(f"Calendar in briefing failed: {e}")

    # Weather
    try:
        weather = await tool_get_weather()
        parts.append(weather)
    except Exception as e:
        logger.warning(f"Weather in briefing failed: {e}")

    message = " ".join(parts)
    await tool_send_sms(message)
    logger.info("Morning briefing sent.")


async def fire_pending_reminders():
    """Poll every minute for reminders that are due."""
    now = datetime.utcnow()
    pending = await get_pending_reminders(before=now)
    for reminder in pending:
        logger.info(f"Firing reminder: {reminder['message']}")
        await tool_send_sms(f"⏰ Reminder: {reminder['message']}")
        await mark_reminder_sent(reminder["id"])


async def send_evening_digest():
    if not settings.enable_evening_digest:
        return
    cal = await tool_get_calendar_events(days_ahead=2)
    message = f"Evening heads-up — here's tomorrow: {cal}"
    await tool_send_sms(message)


def start_scheduler():
    scheduler.add_job(
        send_morning_briefing,
        "cron",
        hour=settings.morning_briefing_hour,
        minute=settings.morning_briefing_minute,
        id="morning_briefing",
        replace_existing=True,
    )
    scheduler.add_job(
        fire_pending_reminders,
        "interval",
        minutes=1,
        id="reminder_poll",
        replace_existing=True,
    )
    scheduler.add_job(
        send_evening_digest,
        "cron",
        hour=settings.evening_digest_hour,
        minute=settings.evening_digest_minute,
        id="evening_digest",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started.")


def stop_scheduler():
    scheduler.shutdown()
