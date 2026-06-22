"""
voice/pipeline.py
-----------------
Pipecat pipeline: Twilio WebSocket ↔ OpenAI Realtime API

Flow:
  Twilio (μ-law audio) → TwilioInputTransport
    → OpenAIRealtimeBetaLLMService (STT + LLM + TTS + tool calls)
    → TwilioOutputTransport → caller's ear
"""

import asyncio
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.openai_realtime_beta import (
    OpenAIRealtimeBetaLLMService,
    InputAudioTranscription,
    SessionProperties,
    TurnDetection,
)
from pipecat.transports.services.twilio import (
    TwilioParams,
    TwilioTransport,
)

from config.settings import settings
from config.prompts import SYSTEM_PROMPT
from core.dispatcher import dispatch
from memory.retrieval import build_memory_context
from tools import TOOL_SCHEMAS


async def run_call_pipeline(websocket, call_sid: str):
    """
    Entry point called per-call. Runs until the call ends.
    websocket — the raw WebSocket connection from Twilio
    """
    logger.info(f"Starting pipeline for call {call_sid}")

    # ── Twilio transport ──────────────────────────────────────────────────────
    transport = TwilioTransport(
        websocket,
        TwilioParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
        ),
    )

    # ── Build system prompt with memory injected ──────────────────────────────
    # We do a generic seed search; memory will be refined per-turn via context
    memory_ctx = await build_memory_context("greeting calendar reminders")
    full_system = SYSTEM_PROMPT
    if memory_ctx:
        full_system += f"\n\n{memory_ctx}"

    # ── OpenAI Realtime LLM ───────────────────────────────────────────────────
    llm = OpenAIRealtimeBetaLLMService(
        api_key=settings.openai_api_key,
        session_properties=SessionProperties(
            instructions=full_system,
            turn_detection=TurnDetection(type="server_vad", silence_duration_ms=600),
            input_audio_transcription=InputAudioTranscription(model="whisper-1"),
        ),
        tools=TOOL_SCHEMAS,
    )

    # ── Context ───────────────────────────────────────────────────────────────
    context = OpenAILLMContext(
        messages=[],
        tools=TOOL_SCHEMAS,
    )
    context_aggregator = llm.create_context_aggregator(context)

    # ── Register tool call handler ────────────────────────────────────────────
    @llm.event_handler("on_tool_call")
    async def on_tool_call(service, tool_call):
        result = await dispatch(tool_call.function.name, tool_call.function.arguments)
        await service.push_tool_result(tool_call, result)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    pipeline = Pipeline([
        transport.input(),
        context_aggregator.user(),
        llm,
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        PipelineParams(allow_interruptions=True),
    )

    # Greet the caller
    @transport.event_handler("on_client_connected")
    async def on_connected(t, client):
        await task.queue_frames([
            context_aggregator.user().get_context_frame(),
        ])
        await llm.say(
            f"Hello {settings.your_name}, how can I help you?",
        )

    runner = PipelineRunner()
    await runner.run(task)
    logger.info(f"Call pipeline ended for {call_sid}")
