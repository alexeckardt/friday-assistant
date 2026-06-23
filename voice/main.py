"""
voice/main.py
-------------
FastAPI server exposing:
  POST /twiml          — Twilio voice webhook; returns Media Streams TwiML
  WS   /ws/call        — Twilio WebSocket for audio streaming (Pipecat)
  POST /tools/*        — HTTP tool endpoints for n8n workflows
  GET  /health         — Liveness check
"""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from loguru import logger
from twilio.request_validator import RequestValidator

from voice.config import settings
from voice.pipeline import run_call_pipeline
from voice.scheduler import start_scheduler, stop_scheduler
from voice.tools import dispatch


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"{settings.assistant_name} starting...")
    start_scheduler()
    yield
    stop_scheduler()
    logger.info(f"{settings.assistant_name} shut down.")


app = FastAPI(title=f"{settings.assistant_name} — AI Assistant", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Twilio signature validation ───────────────────────────────────────────────

_validator = RequestValidator(settings.twilio_auth_token)


async def validate_twilio(request: Request) -> None:
    """Reject requests that don't carry a valid Twilio signature."""
    sig = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    form = dict(await request.form())
    if not _validator.validate(url, form, sig):
        logger.warning(f"Invalid Twilio signature from {request.client.host}")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def _caller_allowed(from_number: str) -> bool:
    allowed = settings.allowed_numbers
    return not allowed or from_number in allowed


# ── Voice webhook (returns TwiML to start Media Streams) ──────────────────────

TWIML_CONNECT = """\
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://{host}/ws/call" />
  </Connect>
</Response>"""

TWIML_REJECT = """\
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Reject reason="busy"/>
</Response>"""


@app.post("/twiml", dependencies=[Depends(validate_twilio)])
async def twiml_handler(request: Request):
    form = dict(await request.form())
    caller = form.get("From", "")

    if not _caller_allowed(caller):
        logger.warning(f"Rejected call from {caller}")
        return Response(content=TWIML_REJECT, media_type="text/xml")

    call_sid = form.get("CallSid", "unknown")
    logger.info(f"Inbound call — From={caller} CallSid={call_sid}")

    host = request.headers.get("host", request.base_url.hostname)
    twiml = TWIML_CONNECT.format(host=host)
    return Response(content=twiml, media_type="text/xml")


# ── WebSocket for Pipecat pipeline ────────────────────────────────────────────

@app.websocket("/ws/call")
async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    call_sid = "unknown"
    stream_sid = "unknown"
    try:
        # Twilio sends "connected" then "start" before any audio frames
        for _ in range(2):
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get("event") == "start":
                start = data.get("start", {})
                call_sid = start.get("callSid", "unknown")
                stream_sid = data.get("streamSid", "unknown")
                break
        await run_call_pipeline(websocket, call_sid, stream_sid)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected — CallSid={call_sid}")
    except Exception as e:
        logger.error(f"Pipeline error — CallSid={call_sid}: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Tool HTTP endpoints (called by n8n workflows) ─────────────────────────────

def _check_task_token(request: Request) -> None:
    if not settings.n8n_task_token:
        return  # token not configured → open (for local dev)
    token = request.headers.get("X-Task-Token", "")
    if token != settings.n8n_task_token:
        raise HTTPException(status_code=403, detail="Invalid task token")


@app.post("/tools/{tool_name}", dependencies=[Depends(_check_task_token)])
async def tool_endpoint(tool_name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    result = await dispatch(tool_name, body)
    return {"result": result}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "online", "assistant": settings.assistant_name}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("voice.main:app", host="0.0.0.0", port=settings.port, reload=False)
