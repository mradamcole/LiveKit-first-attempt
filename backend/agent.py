"""LiveKit Speech-to-Speech Agent.

Receives user text via lk.chat topic, processes with LLM, responds with
text (lk.transcription) and TTS audio. System prompt can be updated at
runtime via RPC from the frontend.
"""

from pathlib import Path
from dotenv import load_dotenv
from livekit.agents import AgentServer, AgentSession, Agent, room_io, JobContext
from livekit.plugins import openai as openai_plugin
from livekit import rtc
import yaml
import logging

logger = logging.getLogger("voice-agent")
logging.basicConfig(level=logging.INFO)

# Models that require the Google plugin instead of OpenAI
_GOOGLE_MODEL_PREFIXES = ("gemini-",)

# Load environment variables from project root .env.local
load_dotenv(Path(__file__).parent.parent / ".env.local")

# Config path (re-read per session so UI model changes take effect)
_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config() -> dict:
    """Read config.yaml from disk. Called per session so changes are picked up."""
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _build_llm(config: dict):
    """Return an LLM plugin instance based on the model name in config.

    If the model starts with 'gemini-', the Google plugin is used (requires
    GOOGLE_API_KEY in .env.local). Otherwise, the OpenAI plugin is used
    (requires OPENAI_API_KEY).
    """
    model = config["llm"]["model"]

    if model.startswith(_GOOGLE_MODEL_PREFIXES):
        from livekit.plugins import google as google_plugin
        logger.info("Using Google LLM plugin for model: %s", model)
        return google_plugin.LLM(model=model)

    logger.info("Using OpenAI LLM plugin for model: %s", model)
    return openai_plugin.LLM(model=model)


def _build_tts(config: dict):
    """Return a TTS plugin instance based on config['tts']['engine'].

    Imports are lazy so you only need the pip package for the engine you use.
    Returns None if the TTS engine is unavailable (allows text-only mode).

    Supported engines:
      - cartesia  : Cloud TTS (requires CARTESIA_API_KEY)
      - kokoro    : Local TTS via Kokoro-FastAPI server (OpenAI-compatible)
      - piper     : Local TTS via self-hosted Piper server
    """
    engine = config["tts"]["engine"]
    engine_cfg = config["tts"].get(engine, {})

    if engine == "cartesia":
        from livekit.plugins import cartesia
        return cartesia.TTS(
            model=engine_cfg.get("model", "sonic-3"),
            voice=engine_cfg.get("voice"),
        )
    elif engine == "kokoro":
        base_url = engine_cfg.get("base_url", "http://localhost:8880/v1")
        # Verify the Kokoro server is reachable before creating the TTS instance
        import urllib.request
        import urllib.error
        try:
            health_url = base_url.rstrip("/").rsplit("/v1", 1)[0] + "/v1/models"
            urllib.request.urlopen(health_url, timeout=3)
        except (urllib.error.URLError, OSError) as exc:
            logger.warning(
                "Kokoro TTS server not reachable at %s (%s) — running in text-only mode",
                base_url, exc,
            )
            return None
        # Kokoro-FastAPI exposes an OpenAI-compatible /v1/audio/speech endpoint,
        # so we reuse the OpenAI TTS plugin with a custom base_url.
        return openai_plugin.TTS(
            model=engine_cfg.get("model", "kokoro"),
            voice=engine_cfg.get("voice", "af_heart"),
            speed=engine_cfg.get("speed", 1.0),
            base_url=base_url,
            api_key=engine_cfg.get("api_key", "not-needed"),
        )
    elif engine == "piper":
        from livekit.plugins import piper_tts
        return piper_tts.TTS(
            base_url=engine_cfg.get("base_url", "http://localhost:5000"),
        )
    else:
        raise ValueError(
            f"Unknown TTS engine '{engine}'. "
            f"Supported engines: cartesia, kokoro, piper"
        )

server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    """Entry point for each agent session."""

    # Re-read config from disk so model changes from the UI take effect
    config = _load_config()

    tts = _build_tts(config)

    agent = Agent(instructions=config["app"]["default_system_prompt"])

    session = AgentSession(
        llm=_build_llm(config),
        tts=tts,
        # No stt= or vad= needed -- browser handles STT via Web Speech API
    )

    # session.start() automatically connects the room. We must connect
    # explicitly first only because the RPC registrations below need
    # ctx.room.local_participant to exist already.
    await ctx.connect()

    # RPC: frontend can update the system prompt at runtime
    @ctx.room.local_participant.register_rpc_method("update_system_prompt")
    async def on_update_prompt(data: rtc.RpcInvocationData) -> str:
        await agent.update_instructions(data.payload)
        logger.info("System prompt updated via RPC")
        return "ok"

    # RPC: frontend can interrupt current agent speech/generation
    @ctx.room.local_participant.register_rpc_method("interrupt")
    async def on_interrupt(data: rtc.RpcInvocationData) -> str:
        try:
            await session.interrupt()
            logger.info("Agent interrupted via RPC")
        except RuntimeError:
            logger.debug("Interrupt called but no active generation to stop")
        return "ok"

    # If TTS is unavailable, disable audio output so the
    # TranscriptSynchronizer doesn't block text waiting for audio frames.
    audio_output = True if tts is not None else False

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=False,      # browser handles STT, no audio sent to server
            audio_output=audio_output,
            # text_input=True       (default -- receives text on lk.chat)
            # text_output=True      (default -- sends text on lk.transcription)
            delete_room_on_close=True,  # clean up room so reconnects get a fresh session
        ),
    )

    if tts is None:
        logger.info("Agent session started in TEXT-ONLY mode (no TTS)")
    else:
        logger.info("Agent session started with TTS — waiting for user text on lk.chat")


if __name__ == "__main__":
    from livekit.agents.cli import run_app
    run_app(server)
