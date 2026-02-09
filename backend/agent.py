"""LiveKit Speech-to-Speech Agent.

Receives user text via lk.chat topic, processes with LLM, responds with
text (lk.transcription) and TTS audio. System prompt can be updated at
runtime via RPC from the frontend.
"""

from pathlib import Path
from dotenv import load_dotenv
from livekit.agents import AgentServer, AgentSession, Agent, room_io, JobContext
from livekit.plugins import openai as openai_plugin
from livekit.plugins import cartesia
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

server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    """Entry point for each agent session."""

    # Connect to the room FIRST so local_participant is available
    await ctx.connect()

    agent = Agent(instructions=config["app"]["default_system_prompt"])

    session = AgentSession(
        llm=openai_plugin.LLM(model=config["llm"]["model"]),
        tts=cartesia.TTS(
            model=config["tts"]["model"],
            voice=config["tts"]["voice"],
        ),
        # No stt= or vad= needed -- browser handles STT via Web Speech API
    )

    # RPC: frontend can update the system prompt at runtime
    # (must be after ctx.connect() so local_participant exists)
    @ctx.room.local_participant.register_rpc_method("update_system_prompt")
    async def on_update_prompt(data: rtc.RpcInvocationData) -> str:
        await agent.update_instructions(data.payload)
        logger.info("System prompt updated via RPC")
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
