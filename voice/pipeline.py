"""
voice/pipeline.py
-----------------
Pipecat realtime voice pipeline:
  Twilio (μ-law audio) → Deepgram STT → Claude LLM → ElevenLabs TTS → Twilio

Each inbound call gets its own pipeline instance running until the call ends.
Tool calls from Claude are dispatched to voice/tools/ handlers in-process.
"""
import json

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.anthropic import AnthropicLLMService
from pipecat.services.deepgram import DeepgramSTTService, LiveOptions
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.transports.services.twilio import TwilioParams, TwilioTransport

from voice.config import settings
from voice.prompts import SYSTEM_PROMPT
from voice.tools import TOOL_SCHEMAS, dispatch
from voice.tools.memory_tool import search_memories


async def _build_memory_context(seed: str = "greeting preferences schedule") -> str:
    memories = search_memories(seed, n_results=settings.memory_top_k)
    if not memories:
        return ""
    lines = [m["text"] for m in memories]
    return "Relevant context from memory:\n" + "\n".join(f"- {l}" for l in lines)


async def run_call_pipeline(websocket, call_sid: str) -> None:
    """Entry point per call. Runs until the call ends or an error occurs."""
    logger.info(f"Pipeline starting — CallSid={call_sid}")

    # ── Transport ─────────────────────────────────────────────────────────────
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

    # ── STT ───────────────────────────────────────────────────────────────────
    stt = DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        live_options=LiveOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            endpointing=300,
        ),
    )

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm = AnthropicLLMService(
        api_key=settings.anthropic_api_key,
        model="claude-sonnet-4-6",
    )

    # ── TTS ───────────────────────────────────────────────────────────────────
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        voice_id=settings.elevenlabs_voice_id,
        model=settings.elevenlabs_model_id,
    )

    # ── Context ───────────────────────────────────────────────────────────────
    memory_ctx = await _build_memory_context()
    system = SYSTEM_PROMPT
    if memory_ctx:
        system = f"{system}\n\n{memory_ctx}"

    context = OpenAILLMContext(
        messages=[{"role": "user", "content": "Hello"}],
        tools=TOOL_SCHEMAS,
        system=system,
    )
    context_aggregator = llm.create_context_aggregator(context)

    # ── Tool call handler ──────────────────────────────────────────────────────
    # Registered with None to catch all function calls from Claude.
    async def handle_tool_call(function_name, tool_call_id, arguments, llm_service, context, result_callback):
        logger.info(f"Tool call: {function_name}({arguments})")
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        result = await dispatch(function_name, args)
        logger.info(f"Tool result: {result[:120]}")
        await result_callback(result)

    llm.register_function(None, handle_tool_call)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    pipeline = Pipeline([
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        PipelineParams(allow_interruptions=True),
    )

    # Greet the caller on connect
    @transport.event_handler("on_client_connected")
    async def on_connected(t, client):
        await task.queue_frames([context_aggregator.user().get_context_frame()])
        await llm.say(f"Hello {settings.your_name}, this is {settings.assistant_name}. How can I help?")

    runner = PipelineRunner()
    await runner.run(task)
    logger.info(f"Pipeline ended — CallSid={call_sid}")
