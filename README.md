# LiveKit Speech-to-Speech Voice Assistant

A browser-based voice assistant that uses the **Web Speech API** for speech-to-text in the browser and a **LiveKit Agent** (Python) for LLM reasoning and TTS audio playback. Communication happens through a LiveKit Room using native text streams and RPC.

## Architecture

```
Browser (HTML/JS)                LiveKit Room              Python Agent
─────────────────               ──────────────             ─────────────
Mic → Web Speech API                                       
  → interim/final text          ──sendText('lk.chat')──→   receives text
  → display in transcript                                  → LLM (OpenAI / Gemini)
                                ←─lk.transcription─────    → streams response text
  → display agent response                                 → TTS (configurable)
  → play agent audio            ←─TTS audio track──────    → publishes audio

System prompt textarea          ──performRpc───────────→   updates agent.instructions
```

## Prerequisites

- **Python 3.9+**
- **Chrome or Edge** browser (Web Speech API requirement)
- **API keys** for OpenAI or Google (depending on chosen LLM) and Cartesia (only if using `cartesia` TTS engine)

## Quick Start

### 0. Install & start the LiveKit server

You need a self-hosted LiveKit server running locally. Download the latest release and start it in dev mode:

**Windows (Git Bash):**

```bash
# Download the binary
curl -L -o livekit-server.zip https://github.com/livekit/livekit/releases/download/v1.9.11/livekit_1.9.11_windows_amd64.zip

# Extract it
unzip livekit-server.zip -d livekit-server

# Start in dev mode (keep this terminal open)
./livekit-server/livekit-server --dev
```

**Linux:**

```bash
curl -L -o livekit-server.tar.gz https://github.com/livekit/livekit/releases/download/v1.9.11/livekit_1.9.11_linux_amd64.tar.gz
mkdir -p livekit-server && tar -xzf livekit-server.tar.gz -C livekit-server
./livekit-server/livekit-server --dev
```

**macOS (via Homebrew):**

```bash
brew install livekit
livekit-server --dev
```

The `--dev` flag starts the server on `ws://localhost:7880` with built-in test credentials:

| Setting | Dev-mode value |
|---------|---------------|
| URL | `ws://localhost:7880` |
| API Key | `devkey` |
| API Secret | `secret` |

> For the latest releases, see [github.com/livekit/livekit/releases](https://github.com/livekit/livekit/releases).
> For production deployments, see the [LiveKit self-hosting docs](https://docs.livekit.io/home/self-hosting/local/).

### 1. Configure credentials

Edit `.env.local` in the project root with your actual credentials. If you started the LiveKit server with `--dev` (step 0), use the dev-mode values for the first three:

```
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
OPENAI_API_KEY=sk-your-openai-key      # needed when llm.model is an OpenAI model
GOOGLE_API_KEY=your-google-api-key     # needed when llm.model is a Gemini model
CARTESIA_API_KEY=your-cartesia-key     # only needed when tts.engine is "cartesia"
```

Optionally edit `config.yaml` to change the TTS engine, LLM model, voice, default system prompt, or room name. See the [TTS Engine](#tts-engine) section below for details.

### 2. Install Python dependencies

```bash
cd backend
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
# source venv/bin/activate     # Linux / macOS / WSL
pip install -r requirements.txt
```

### 3. Start the app

The easiest way is with the startup script (from the project root):

```bash
./start.sh start      # Start token server + agent in background
./start.sh status     # Check if services are running
./start.sh restart    # Restart everything
./start.sh stop       # Shut down all services
```

The script will:
- Activate the virtual environment automatically
- Detect port conflicts and tell you if the port is already held by a previous instance of the app
- Store logs in `.logs/` (token_server.log, agent.log)

<details>
<summary>Manual start (two terminals)</summary>

**Terminal 1 – Token server** (also serves the frontend):

```bash
cd backend
source venv/Scripts/activate   # Windows Git Bash
# source venv/bin/activate     # Linux / macOS / WSL
uvicorn token_server:app --port 3000
# or...
Windows: cd backend && source venv/Scripts/activate && uvicorn token_server:app --port 3000
Mac: cd backend && source venv/bin/activate && uvicorn token_server:app --port 3000
```

**Terminal 2 – Agent:**

```bash
cd backend
source venv/Scripts/activate   # Windows Git Bash
# source venv/bin/activate     # Linux / macOS / WSL
python agent.py dev
# or...
Windows: cd backend && source venv/Scripts/activate && python agent.py dev
Mac: cd backend && source venv/bin/activate && python agent.py dev
```
</details>

### 4. Open the app

Navigate to **http://localhost:3000** in Chrome or Edge.

1. Click **Connect** to join the LiveKit room
2. Click **Start Mic** to begin speaking
3. Your speech is transcribed locally and sent to the agent
4. The agent responds with text (displayed) and audio (played)
5. Edit the system prompt textarea to change the agent's behavior

## Project Structure

```
├── start.sh                 # Service manager (start / stop / restart / status)
├── config.yaml              # Model names, voice ID, default prompt, room name
├── .env.local               # API keys and LiveKit credentials (git-ignored)
├── backend/
│   ├── requirements.txt     # Python dependencies
│   ├── agent.py             # LiveKit Agent (LLM + TTS pipeline)
│   └── token_server.py      # FastAPI (token generation + static serving)
├── frontend/
│   ├── index.html           # Main page layout
│   ├── style.css            # Styling
│   └── app.js               # Web Speech API + LiveKit client
└── README.md
```

## Configuration

### `config.yaml`

| Key | Description |
|-----|-------------|
| `llm.model` | LLM model name — OpenAI (e.g., `gpt-4o-mini`) or Google (e.g., `gemini-1.5-flash`) |
| `tts.engine` | TTS engine to use: `cartesia`, `kokoro`, or `piper` |
| `tts.cartesia.*` | Cartesia-specific settings (`model`, `voice`) |
| `tts.kokoro.*` | Kokoro-specific settings (`base_url`, `model`, `voice`, `speed`) |
| `tts.piper.*` | Piper-specific settings (`base_url`) |
| `app.default_system_prompt` | Default system prompt for the agent |
| `app.room_name` | LiveKit room name |

### TTS Engine

The TTS engine is selected by setting `tts.engine` in `config.yaml`. Each engine has its own sub-config block. To switch engines, change the `tts.engine` value -- no code changes required.

| Engine | Type | API Key Required | Local Server Required | Notes |
|--------|------|------------------|-----------------------|-------|
| `cartesia` | Cloud | Yes (`CARTESIA_API_KEY`) | No | High quality, requires internet and a paid API key |
| `kokoro` | Local | No | Yes | Good quality, runs on CPU or GPU, no cloud costs |
| `piper` | Local | No | Yes | Fast and lightweight, best for CPU-only machines |

**Kokoro** uses a local [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) server that exposes an OpenAI-compatible endpoint. Start it before running the agent:

```bash
# See https://github.com/remsky/Kokoro-FastAPI for full setup
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

**Piper** uses a self-hosted [Piper TTS](https://github.com/OHF-Voice/piper1-gpl) web server:

```bash
# See https://github.com/OHF-Voice/piper1-gpl for full setup
# Server should be reachable at http://localhost:5000
```

Example -- switch to local Kokoro TTS:

```yaml
tts:
  engine: "kokoro"
```

### `.env.local`

| Variable | Description |
|----------|-------------|
| `LIVEKIT_URL` | LiveKit server WebSocket URL |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `OPENAI_API_KEY` | OpenAI API key (needed when `llm.model` is an OpenAI model) |
| `GOOGLE_API_KEY` | Google API key (needed when `llm.model` is a Gemini model) |
| `CARTESIA_API_KEY` | Cartesia API key (only needed when `tts.engine` is `cartesia`) |

## How It Works

1. The browser fetches a JWT token from the FastAPI server and connects to the LiveKit room
2. The Python agent auto-joins the room when a participant connects
3. User speech is captured by the Web Speech API (runs entirely in the browser)
4. Final transcriptions are sent to the agent via `sendText()` on the `lk.chat` topic
5. The agent processes the text with the LLM and streams the response back via `lk.transcription`
6. TTS audio is synthesized and published to the room, auto-played in the browser
7. The system prompt can be updated at any time via RPC -- changes take effect on the next LLM call

## Tech Stack

| Component | Technology |
|-----------|-----------|
| STT | Browser Web Speech API |
| Text transport | LiveKit text streams (`lk.chat`, `lk.transcription`) |
| Prompt updates | LiveKit RPC |
| LLM | OpenAI or Google Gemini (configurable via `config.yaml`) |
| TTS | Cartesia, Kokoro, or Piper (configurable via `config.yaml`) |
| Agent framework | LiveKit Agents SDK (Python) |
| Token server | FastAPI |
| Frontend | Vanilla HTML/JS/CSS |
