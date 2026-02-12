"""FastAPI token server for LiveKit.

Endpoints:
  GET  /api/token?identity=<name>  -- returns { token, url } JWT for room access
  GET  /api/config                 -- returns app config (prompt, models, voices, etc.)
  POST /api/config/model           -- updates the active LLM model
  POST /api/config/voice           -- updates the active TTS voice
  GET  /                           -- serves frontend static files
"""

from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from livekit.api import AccessToken, VideoGrants, RoomAgentDispatch, RoomConfiguration
from pydantic import BaseModel
import os
import yaml

# Load environment variables from project root .env.local
load_dotenv(Path(__file__).parent.parent / ".env.local")

# Load non-sensitive config
_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

with open(_CONFIG_PATH) as f:
    config = yaml.safe_load(f)

app = FastAPI(title="LiveKit Voice App Token Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/token")
async def get_token(identity: str = Query(..., description="Participant identity")):
    """Generate a LiveKit JWT access token for the given identity."""
    token = AccessToken(
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )
    token.identity = identity
    token.with_kind("standard")
    token.with_grants(VideoGrants(
        room_join=True,
        room=config["app"]["room_name"],
        can_publish=True,
        can_subscribe=True,
    ))
    # Explicitly dispatch the agent when this participant connects.
    # This ensures the agent is dispatched even if auto-dispatch doesn't fire.
    token.with_room_config(
        RoomConfiguration(
            agents=[
                RoomAgentDispatch(agent_name=""),
            ],
        ),
    )
    return {"token": token.to_jwt(), "url": os.getenv("LIVEKIT_URL")}


@app.get("/api/config")
async def get_config():
    """Return non-sensitive app configuration to the frontend."""
    return {
        "default_system_prompt": config["app"]["default_system_prompt"],
        "room_name": config["app"]["room_name"],
        "active_model": config["llm"]["model"],
        "models": config["llm"].get("models", []),
        "active_voice": config["tts"].get("voice", "kokoro_af_heart"),
        "voices": config["tts"].get("voices", []),
    }


class ModelUpdate(BaseModel):
    model: str


@app.post("/api/config/model")
async def set_model(body: ModelUpdate):
    """Update the active LLM model.

    Validates against the models list in config, updates the in-memory config,
    and persists the change to config.yaml so the agent picks it up on the
    next session.
    """
    allowed_ids = {m["id"] for m in config["llm"].get("models", [])}
    if body.model not in allowed_ids:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{body.model}'. Allowed: {sorted(allowed_ids)}",
        )

    config["llm"]["model"] = body.model

    # Persist to disk so the agent reads the new model on next session
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    return {"active_model": body.model}


class VoiceUpdate(BaseModel):
    voice: str


@app.post("/api/config/voice")
async def set_voice(body: VoiceUpdate):
    """Update the active TTS voice.

    Validates against the voices list in config, updates the in-memory config,
    and persists the change to config.yaml so the agent picks it up on the
    next session.
    """
    allowed_ids = {v["id"] for v in config["tts"].get("voices", [])}
    if body.voice not in allowed_ids:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice '{body.voice}'. Allowed: {sorted(allowed_ids)}",
        )

    config["tts"]["voice"] = body.voice

    # Persist to disk so the agent reads the new voice on next session
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    return {"active_voice": body.voice}


# Serve frontend static files (must be last -- catches all unmatched routes)
app.mount(
    "/",
    StaticFiles(
        directory=Path(__file__).parent.parent / "frontend",
        html=True,
    ),
    name="frontend",
)
