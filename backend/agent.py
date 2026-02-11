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

# Load environment variables from project root .env.local
load_dotenv(Path(__file__).parent.parent / ".env.local")

# Load non-sensitive config
with open(Path(__file__).parent.parent / "config.yaml") as f:
    config = yaml.safe_load(f)


def _build_tts(config: dict):
    """Return a TTS plugin instance based on config['tts']['engine'].

    Imports are lazy so you only need the pip package for the engine you use.

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
        # Kokoro-FastAPI exposes an OpenAI-compatible /v1/audio/speech endpoint,
        # so we reuse the OpenAI TTS plugin with a custom base_url.
        return openai_plugin.TTS(
            model=engine_cfg.get("model", "kokoro"),
            voice=engine_cfg.get("voice", "af_heart"),
            speed=engine_cfg.get("speed", 1.0),
            base_url=engine_cfg.get("base_url", "http://localhost:8880/v1"),
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

    # Connect to the room FIRST so local_participant is available
    await ctx.connect()

    agent = Agent(instructions=config["app"]["default_system_prompt"])

    session = AgentSession(
        llm=openai_plugin.LLM(model=config["llm"]["model"]),
        tts=_build_tts(config),
        # No stt= or vad= needed -- browser handles STT via Web Speech API
    )

    # RPC: frontend can update the system prompt at runtime
    # (must be after ctx.connect() so local_participant exists)
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

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=False,      # browser handles STT, no audio sent to server
            # audio_output=True     (default -- TTS audio published to room)
            # text_input=True       (default -- receives text on lk.chat)
            # text_output=True      (default -- sends text on lk.transcription)
        ),
    )

    logger.info("Agent session started -- waiting for user text on lk.chat")


if __name__ == "__main__":
    from livekit.agents.cli import run_app
    run_app(server)
