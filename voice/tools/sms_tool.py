"""
voice/tools/sms_tool.py
------------------------
Twilio outbound SMS + scheduled reminders.
"""
import pendulum
from loguru import logger
from twilio.rest import Client

from voice.config import settings
from voice.tools.memory_tool import add_reminder


def _twilio() -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


async def tool_send_sms(message: str, to: str | None = None) -> str:
    target = to or settings.your_phone_number
    try:
        msg = _twilio().messages.create(
            body=message,
            from_=settings.twilio_phone_number,
            to=target,
        )
        logger.info(f"SMS sent: {msg.sid}")
        return "Message sent."
    except Exception as e:
        logger.error(f"SMS error: {e}")
        return f"Couldn't send the message: {e}"


async def tool_schedule_reminder(message: str, remind_at: str) -> str:
    try:
        fire_dt = pendulum.parse(remind_at, tz=settings.timezone)
        await add_reminder(message, fire_dt)
        time_str = fire_dt.format("dddd [the] Do [at] h:mm A")
        return f"Reminder set for {time_str}."
    except Exception as e:
        return f"Couldn't schedule that reminder: {e}"
