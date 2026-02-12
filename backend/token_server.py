"""FastAPI token server for LiveKit.

Endpoints:
  GET  /api/token?identity=<name>  -- returns { token, url } JWT for room access
  GET  /api/config                 -- returns app config (prompt, models, voices, etc.)
  POST /api/config/model           -- updates the active LLM model
  POST /api/config/voice           -- updates the active TTS voice
  GET  /api/tts/status             -- returns TTS engine type and health status
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
import urllib.request
import urllib.error

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


# Engines that run locally and need a health check
_LOCAL_ENGINES = {"kokoro", "piper"}


@app.get("/api/tts/status")
async def tts_status():
    """Return the active TTS engine type and its health status.

    For local engines (kokoro, piper) this performs a quick HTTP health check
    against the configured server URL. Cloud engines and text_only always
    return status 'ok'.
    """
    voice_id = config["tts"].get("voice", "kokoro_af_heart")

    # Text-only mode
    if voice_id == "text_only":
        return {"engine": "text_only", "status": "ok", "label": "Text Only"}

    # Resolve voice entry
    voices = config["tts"].get("voices", [])
    entry = next((v for v in voices if v["id"] == voice_id), None)
    if entry is None:
        return {"engine": "unknown", "status": "error", "label": "Unknown voice"}

    engine = entry.get("engine", "unknown")
    engine_cfg = config["tts"].get(engine, {})

    # Cloud engine -- no health check needed
    if engine not in _LOCAL_ENGINES:
        label = engine.capitalize()
        return {"engine": engine, "status": "ok", "label": f"Cloud ({label})"}

    # Local engine -- perform health check
    label = engine.capitalize()
    if engine == "kokoro":
        base_url = engine_cfg.get("base_url", "http://localhost:8880/v1")
        health_url = base_url.rstrip("/").rsplit("/v1", 1)[0] + "/v1/models"
    elif engine == "piper":
        base_url = engine_cfg.get("base_url", "http://localhost:8881")
        health_url = base_url.rstrip("/") + "/voices"
    else:
        health_url = None

    if health_url:
        try:
            urllib.request.urlopen(health_url, timeout=3)
            return {"engine": engine, "status": "online", "label": label}
        except (urllib.error.URLError, OSError):
            return {"engine": engine, "status": "offline", "label": label}

    return {"engine": engine, "status": "unknown", "label": label}


# Serve frontend static files (must be last -- catches all unmatched routes)
app.mount(
    "/",
    StaticFiles(
        directory=Path(__file__).parent.parent / "frontend",
        html=True,
    ),
    name="frontend",
)
