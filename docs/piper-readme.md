# Piper TTS Setup

Piper is a fast, lightweight, local text-to-speech engine. It runs on your machine via a self-hosted [Piper TTS web server](https://github.com/OHF-Voice/piper1-gpl) and connects to the agent through the `livekit-plugins-piper-tts` community plugin. No cloud API key is needed.

## Prerequisites

- **Python 3.9+** (for the Piper server, if running from source)
- Or **Docker** (for the containerized option)

## Quick Start

### 1. Start the Piper TTS server

**Option A -- Docker (recommended):**

```bash
docker run -p 5000:5000 rhasspy/piper:latest --server
```

**Option B -- From source:**

```bash
# Clone the Piper server
git clone https://github.com/OHF-Voice/piper1-gpl.git
cd piper1-gpl

# Install and run (see repo README for full details)
pip install -e .
piper --server --port 5000
```

On first run Piper downloads the voice model you select. Wait for the server to finish loading before proceeding.

### 2. Verify the server is running

```bash
curl "http://localhost:5000/api/tts?text=Hello+world" --output test.wav
```

If you get a valid WAV file back, the server is working.

### 3. Set the engine in config.yaml

```yaml
tts:
  engine: "piper"
```

### 4. Start the app

```bash
./start.sh start
```

The agent connects to the Piper server at the `base_url` configured under `tts.piper` in `config.yaml` (default: `http://localhost:5000`).

## Configuration

All Piper settings live under `tts.piper` in `config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `base_url` | `http://localhost:5000` | Piper TTS server URL |

Voice selection is handled server-side by the Piper server configuration. See the Piper documentation for how to download and switch voice models.

## Available Voices

Piper has a large collection of voices across many languages. Voices are downloaded as ONNX model files. Some popular English voices:

| Voice | Quality | Description |
|-------|---------|-------------|
| `en_US-lessac-medium` | Medium | Clear American male (default for many setups) |
| `en_US-lessac-high` | High | Higher quality version of lessac |
| `en_US-amy-medium` | Medium | American female |
| `en_US-ryan-medium` | Medium | American male |
| `en_GB-alba-medium` | Medium | British female |
| `en_GB-alan-medium` | Medium | British male |

For the full voice catalog, see [Piper voice samples](https://rhasspy.github.io/piper-samples/).

## Architecture

```
Agent (agent.py)
  └─ piper_tts.TTS(base_url="http://localhost:5000")
       └─ HTTP request  ──→  Piper TTS Server (port 5000)
                                └─ ONNX voice model (local inference)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Connection refused` on port 5000 | Make sure the Piper server is running |
| No audio / empty response | Ensure a voice model is installed on the server |
| Slow first response | The voice model loads on first request; subsequent requests are fast |
| Poor voice quality | Try a `-high` quality voice model instead of `-medium` or `-low` |
| Docker not found | Install Docker Desktop from https://www.docker.com/products/docker-desktop |

## Links

- [Piper TTS GitHub (OHF-Voice)](https://github.com/OHF-Voice/piper1-gpl)
- [Piper voice samples](https://rhasspy.github.io/piper-samples/)
- [livekit-plugins-piper-tts on PyPI](https://pypi.org/project/livekit-plugins-piper-tts/)
