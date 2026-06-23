"""
voice/config.py
---------------
All configuration sourced from environment variables.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Persona ───────────────────────────────────────────────────────────────
    assistant_name: str = "Friday"
    your_name: str = "Alex"

    # ── Twilio ────────────────────────────────────────────────────────────────
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    your_phone_number: str
    allowed_phone_numbers: str = ""  # comma-separated; empty = allow all

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str

    # ── ElevenLabs ────────────────────────────────────────────────────────────
    elevenlabs_api_key: str
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model_id: str = "eleven_flash_v2"

    # ── Deepgram ──────────────────────────────────────────────────────────────
    deepgram_api_key: str

    # ── n8n Integration ───────────────────────────────────────────────────────
    n8n_webhook_url: str = "http://n8n:5678/webhook"
    n8n_task_token: str = ""

    # ── Google Calendar ───────────────────────────────────────────────────────
    google_credentials_path: str = "/data/google-credentials.json"
    google_calendar_id: str = "primary"

    # ── OpenWeatherMap ────────────────────────────────────────────────────────
    openweather_api_key: str = ""
    default_location: str = "New York"

    # ── Memory / Storage ──────────────────────────────────────────────────────
    chroma_persist_dir: str = "/data/chromadb"
    facts_db_path: str = "/data/facts.sqlite"
    notes_dir: str = "/data/notes"
    memory_top_k: int = 5

    # ── Scheduler ─────────────────────────────────────────────────────────────
    timezone: str = "America/New_York"
    morning_briefing_hour: int = 7
    morning_briefing_minute: int = 0
    evening_digest_hour: int = 18
    evening_digest_minute: int = 0
    enable_evening_digest: bool = False

    # ── Server ────────────────────────────────────────────────────────────────
    port: int = 8000
    public_url: str = "http://localhost:8000"

    @property
    def allowed_numbers(self) -> set[str]:
        if not self.allowed_phone_numbers.strip():
            return set()
        return {n.strip() for n in self.allowed_phone_numbers.split(",") if n.strip()}

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
