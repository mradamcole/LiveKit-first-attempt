# Kokoro TTS Setup

Kokoro is a local text-to-speech engine that runs on your machine via the [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) server. It exposes an OpenAI-compatible API, so the agent reuses the existing OpenAI TTS plugin with a custom `base_url`. No cloud API key is needed.

## Prerequisites

- **Docker** installed and running

## Quick Start

### 1. Start the Kokoro-FastAPI server

**CPU only:**

```bash
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

**With NVIDIA GPU acceleration:**

```bash
docker run --gpus all -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest
```

**Apple Silicon (M1/M2/M3):** Use the CPU image. CUDA is not supported on Apple Silicon. MPS support is planned but not yet available.

On first run the server downloads the Kokoro model weights (~300 MB). Wait for log output indicating the server is ready before proceeding.

### 2. Verify the server is running

```bash
curl http://localhost:8880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model": "kokoro", "input": "Hello world", "voice": "af_heart"}' \
  --output test.wav
```

If you get a valid WAV file back, the server is working.

### 3. Set the engine in config.yaml

```yaml
tts:
  engine: "kokoro"
```

### 4. Start the app

```bash
./start.sh start
```

The agent connects to the Kokoro server at the `base_url` configured under `tts.kokoro` in `config.yaml` (default: `http://localhost:8880/v1`).

## Configuration

All Kokoro settings live under `tts.kokoro` in `config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `base_url` | `http://localhost:8880/v1` | Kokoro-FastAPI server URL |
| `model` | `kokoro` | Model name passed to the API |
| `voice` | `af_heart` | Voice ID (see available voices below) |
| `speed` | `1.0` | Speech speed multiplier |

## Available Voices

Kokoro ships with several built-in voices. Change the voice in `config.yaml` at `tts.kokoro.voice`.

### American English

| Voice ID | Description |
|----------|-------------|
| `af_heart` | Female (default) |
| `af_bella` | Female |
| `af_sarah` | Female |
| `af_nicole` | Female |
| `am_adam` | Male |
| `am_michael` | Male |

### British English

| Voice ID | Description |
|----------|-------------|
| `bf_emma` | Female |
| `bf_isabella` | Female |
| `bm_george` | Male |
| `bm_lewis` | Male |

For the full and most up-to-date voice list, see the [Kokoro-FastAPI documentation](https://github.com/remsky/Kokoro-FastAPI).

## Architecture

```
Agent (agent.py)
  └─ openai_plugin.TTS(base_url="http://localhost:8880/v1")
       └─ POST /v1/audio/speech  ──→  Kokoro-FastAPI (Docker, port 8880)
                                         └─ Kokoro model (local inference)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Connection refused` on port 8880 | Make sure the Kokoro-FastAPI Docker container is running |
| Slow first response | The model loads into memory on the first request; subsequent requests are fast |
| Out of memory (GPU) | Use CPU mode (omit `--gpus all`) or try a machine with more VRAM |
| Docker not found | Install Docker Desktop from https://www.docker.com/products/docker-desktop |
