"""
voice/tools/n8n_tool.py
------------------------
Triggers async background workflows in n8n.
Friday responds immediately ("I'll text you when done"); n8n runs the task
and sends an SMS on completion via its notify-complete sub-workflow.
"""
import httpx
from loguru import logger

from voice.config import settings


async def tool_trigger_background_task(
    task_name: str,
    task_description: str,
    params: dict | None = None,
) -> str:
    """
    Fire-and-forget: POST to n8n webhook and return immediately.
    n8n will SMS the user when the task finishes.
    """
    payload = {
        "task_name": task_name,
        "task_description": task_description,
        "params": params or {},
        "callback_phone": settings.your_phone_number,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.n8n_webhook_url}/trigger-task",
                json=payload,
                headers={"X-Task-Token": settings.n8n_task_token},
            )
            resp.raise_for_status()
        logger.info(f"n8n task triggered: {task_name}")
    except Exception as e:
        logger.warning(f"n8n trigger failed (task will not run): {e}")
        return "Sorry, I couldn't queue that task right now."

    return "I'm on it — I'll text you when it's finished."
