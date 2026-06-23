"""
voice/scheduler.py
------------------
APScheduler background jobs:
  - Morning briefing SMS
  - Reminder poll (every minute — fires pending SQLite reminders)
  - Evening digest (optional)
"""
from datetime import datetime

import pendulum
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from voice.config import settings
from voice.tools.memory_tool import get_pending_reminders, mark_reminder_sent
from voice.tools.sms_tool import tool_send_sms
from voice.tools.calendar_tool import tool_get_calendar_events
from voice.tools.weather_tool import tool_get_weather


_scheduler = AsyncIOScheduler(timezone=settings.timezone)


async def _morning_briefing() -> None:
    logger.info("Sending morning briefing...")
    today = pendulum.now(settings.timezone).format("dddd, MMMM Do")
    parts = [f"Good morning! Briefing for {today}."]

    try:
        parts.append(await tool_get_calendar_events(days_ahead=1))
    except Exception as e:
        logger.warning(f"Calendar in briefing failed: {e}")

    try:
        parts.append(await tool_get_weather())
    except Exception as e:
        logger.warning(f"Weather in briefing failed: {e}")

    await tool_send_sms(" ".join(parts))
    logger.info("Morning briefing sent.")


async def _reminder_poll() -> None:
    now = datetime.utcnow()
    pending = await get_pending_reminders(before=now)
    for r in pending:
        logger.info(f"Firing reminder: {r['message']}")
        await tool_send_sms(f"Reminder: {r['message']}")
        await mark_reminder_sent(r["id"])


async def _evening_digest() -> None:
    if not settings.enable_evening_digest:
        return
    cal = await tool_get_calendar_events(days_ahead=2)
    await tool_send_sms(f"Evening heads-up — here's tomorrow: {cal}")


def start_scheduler() -> None:
    _scheduler.add_job(
        _morning_briefing, "cron",
        hour=settings.morning_briefing_hour,
        minute=settings.morning_briefing_minute,
        id="morning_briefing", replace_existing=True,
    )
    _scheduler.add_job(
        _reminder_poll, "interval",
        minutes=1,
        id="reminder_poll", replace_existing=True,
    )
    _scheduler.add_job(
        _evening_digest, "cron",
        hour=settings.evening_digest_hour,
        minute=settings.evening_digest_minute,
        id="evening_digest", replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started.")


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
