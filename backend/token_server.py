"""FastAPI token server for LiveKit.

Endpoints:
  GET /api/token?identity=<name>  -- returns { token, url } JWT for room access
  GET /api/config                 -- returns { default_system_prompt, room_name }
  GET /                           -- serves frontend static files
"""

from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from livekit.api import AccessToken, VideoGrants
import os
import yaml

# Load environment variables from project root .env.local
load_dotenv(Path(__file__).parent.parent / ".env.local")

# Load non-sensitive config
with open(Path(__file__).parent.parent / "config.yaml") as f:
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
    token.with_grants(VideoGrants(
        room_join=True,
        room=config["app"]["room_name"],
        can_publish=True,
        can_subscribe=True,
    ))
    return {"token": token.to_jwt(), "url": os.getenv("LIVEKIT_URL")}


@app.get("/api/config")
async def get_config():
    """Return non-sensitive app configuration to the frontend."""
    return {
        "default_system_prompt": config["app"]["default_system_prompt"],
        "room_name": config["app"]["room_name"],
    }


# Serve frontend static files (must be last -- catches all unmatched routes)
app.mount(
    "/",
    StaticFiles(
        directory=Path(__file__).parent.parent / "frontend",
        html=True,
    ),
    name="frontend",
)
