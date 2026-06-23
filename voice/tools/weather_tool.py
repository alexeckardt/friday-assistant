"""
voice/tools/weather_tool.py
---------------------------
OpenWeatherMap integration.
"""
import httpx
from loguru import logger

from voice.config import settings
from voice.tools.memory_tool import get_fact


async def tool_get_weather(location: str = "", forecast_days: int = 1) -> str:
    if not settings.openweather_api_key:
        return "Weather is not configured — add an OpenWeatherMap API key."

    loc = location or await get_fact("user.location") or settings.default_location

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": loc,
                "appid": settings.openweather_api_key,
                "units": "imperial",
                "cnt": forecast_days * 8,
            },
        )

    data = resp.json()
    if data.get("cod") != "200":
        return f"Couldn't get weather for {loc}."

    first = data["list"][0]
    temp = round(first["main"]["temp"])
    desc = first["weather"][0]["description"]
    return f"In {loc} right now: {temp}°F and {desc}."
