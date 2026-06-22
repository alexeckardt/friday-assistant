# JARVIS — Personal AI Voice Assistant

> "Sometimes you gotta run before you can walk." — Tony Stark

A self-hosted, phone-callable AI secretary with persistent memory, calendar control, and proactive SMS reminders. Runs on a Raspberry Pi (or any always-on Linux server).

---

## What It Does

- 📞 **Call a real phone number** → have a voice conversation with your AI
- 🧠 **Persistent memory** → tell it things, it remembers them across calls
- 📅 **Calendar management** → "add a dentist appointment Friday at 3pm"
- 📲 **Proactive SMS** → texts you reminders throughout the day
- 🔧 **Extensible tools** → weather, notes, timers, web search, and more

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    YOU (caller)                      │
└────────────────────┬────────────────────────────────┘
                     │ phone call
                     ▼
┌─────────────────────────────────────────────────────┐
│                   TWILIO                             │
│  - Holds your phone number                           │
│  - Streams audio via WebSocket (Media Streams)       │
│  - Sends/receives SMS                                │
└────────────────────┬────────────────────────────────┘
                     │ WebSocket (raw audio, μ-law)
                     ▼
┌─────────────────────────────────────────────────────┐
│              JARVIS BACKEND (your Pi)                │
│                                                      │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  Voice Layer │    │      Tool Dispatcher      │   │
│  │  (pipecat)   │───▶│  routes AI tool calls to  │   │
│  │              │    │  calendar / memory / SMS   │   │
│  └──────┬───────┘    └──────────────────────────┘   │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │  OpenAI      │    │     Memory Store          │   │
│  │  Realtime    │    │  (ChromaDB, local vector  │   │
│  │  API (brain) │    │   DB on disk)             │   │
│  └──────────────┘    └──────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │           Scheduler (APScheduler)             │   │
│  │  - Morning briefing SMS                       │   │
│  │  - Reminder fire-and-forget jobs              │   │
│  │  - Daily calendar digest                      │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────┐  ┌──────────────────────┐
│  Google Calendar │  │  ChromaDB (memory)   │
│  API             │  │  local SQLite facts  │
└──────────────────┘  └──────────────────────┘
```

---

## Project Structure

```
jarvis/
├── main.py                  # Entry point — starts FastAPI + pipecat pipeline
├── config/
│   ├── settings.py          # All env vars and config constants
│   └── prompts.py           # System prompt for Jarvis's personality
├── voice/
│   ├── pipeline.py          # Pipecat pipeline: Twilio → OpenAI Realtime → Twilio
│   ├── twilio_handler.py    # FastAPI routes for Twilio webhooks
│   └── audio_utils.py       # μ-law conversion helpers
├── core/
│   ├── agent.py             # Tool registration + OpenAI function calling setup
│   └── dispatcher.py        # Routes tool calls to the right handler
├── tools/
│   ├── calendar_tool.py     # Google Calendar read/write
│   ├── memory_tool.py       # Remember / recall via ChromaDB
│   ├── sms_tool.py          # Send SMS via Twilio REST
│   ├── weather_tool.py      # OpenWeatherMap (optional)
│   └── notes_tool.py        # Quick scratchpad notes (local markdown files)
├── memory/
│   ├── store.py             # ChromaDB client + embedding helpers
│   ├── facts.py             # Structured fact storage (SQLite for key facts)
│   └── retrieval.py         # Semantic search over memories
├── scheduler/
│   ├── jobs.py              # APScheduler job definitions
│   └── briefing.py          # Morning SMS digest builder
├── tests/
│   ├── test_memory.py
│   ├── test_calendar.py
│   └── test_pipeline.py
├── requirements.txt
├── .env.example
├── setup.sh                 # One-shot Pi setup script
└── Makefile                 # Common dev commands
```

---

## Memory Design

Memory is split into two layers:

### Layer 1 — Semantic Memory (ChromaDB)
Long-form, fuzzy-searchable. When you say anything worth remembering, it's embedded and stored.

- "Remember that my sister's birthday is March 12th"
- "My car insurance renews in October"
- "I prefer morning meetings over afternoon ones"

Retrieval is automatic — before each response, Jarvis runs a semantic search against your input and injects relevant memories into context.

### Layer 2 — Structured Facts (SQLite)
Key-value facts that need exact retrieval:
- `user.name`, `user.phone`, `user.timezone`
- Named entities: people, places, recurring events
- Preferences: communication style, reminder frequency

Both layers are queried on every turn and the top results are injected into the LLM's system context.

---

## Tools Available to Jarvis

| Tool | What it does |
|------|-------------|
| `remember` | Stores a memory (semantic + optionally structured) |
| `recall` | Explicitly searches memory for something |
| `add_calendar_event` | Creates a Google Calendar event |
| `get_calendar_events` | Reads upcoming events (today, this week, etc.) |
| `delete_calendar_event` | Removes an event by name/time |
| `send_sms` | Sends you a text message |
| `schedule_reminder` | Schedules a future SMS reminder |
| `get_weather` | Fetches current weather / forecast |
| `take_note` | Saves a quick markdown note to disk |
| `read_notes` | Reads back recent notes |

---

## Voice Pipeline (pipecat)

The realtime voice loop works like this:

1. Twilio opens a WebSocket to your Pi on `/ws/call`
2. Pipecat receives raw μ-law audio, decodes it
3. Audio is streamed to **OpenAI Realtime API** (handles STT + LLM + TTS in one connection)
4. OpenAI emits text deltas + audio deltas simultaneously
5. Audio is re-encoded to μ-law and streamed back to Twilio → your ear
6. When OpenAI emits a `tool_call`, the dispatcher runs the tool and returns results
7. Latency target: < 800ms to first audio byte

---

## Scheduler / Proactive SMS

APScheduler runs inside the same process:

- **7:00 AM daily** — Morning briefing: today's calendar events + weather + any pending reminders
- **Ad-hoc** — When you say "remind me at 3pm to call the dentist," a one-off job is created
- **Evening digest (optional)** — 6pm summary of what's tomorrow

---

## Setup Guide

### Prerequisites
- Raspberry Pi 4/5 (or any Linux machine with Python 3.11+)
- A domain or ngrok URL (Twilio needs a public HTTPS endpoint)
- Accounts: Twilio, OpenAI, Google Cloud (Calendar API)

### Quick Start

```bash
git clone https://github.com/you/jarvis
cd jarvis
cp .env.example .env
# Fill in your API keys in .env
bash setup.sh        # installs deps, sets up ChromaDB, runs DB migrations
make dev             # starts the server with ngrok tunnel
```

### Pi-specific (systemd service)

```bash
sudo cp jarvis.service /etc/systemd/system/
sudo systemctl enable jarvis
sudo systemctl start jarvis
```

---

## Environment Variables

```
OPENAI_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=       # your Twilio number e.g. +14155551234
YOUR_PHONE_NUMBER=         # your personal number for SMS
GOOGLE_CALENDAR_ID=        # e.g. primary
GOOGLE_CREDENTIALS_PATH=   # path to google service account JSON
OPENWEATHER_API_KEY=       # optional
PUBLIC_URL=                # your Pi's public URL e.g. https://jarvis.yourdomain.com
TIMEZONE=                  # e.g. Europe/London
JARVIS_NAME=Jarvis         # change to Friday, EDITH, whatever you like
```

---

## Cost Estimate (monthly, light use)

| Service | Cost |
|---------|------|
| Twilio number | ~$1 |
| Twilio voice (30 min calls) | ~$1.80 |
| Twilio SMS (50 messages) | ~$0.40 |
| OpenAI Realtime API (30 min) | ~$1.80 |
| Raspberry Pi (electricity) | ~$0.50 |
| **Total** | **~$5–6/month** |

---

## Roadmap

- [ ] v0.1 — Voice call works, basic Q&A
- [ ] v0.2 — Memory (remember + recall)
- [ ] v0.3 — Calendar read/write
- [ ] v0.4 — Proactive SMS + scheduler
- [ ] v0.5 — Weather + notes tools
- [ ] v1.0 — Stable, Pi systemd service, setup script
- [ ] v1.1 — Web dashboard to view/edit memories
- [ ] v1.2 — WhatsApp support (Twilio WhatsApp sandbox)
