# Cartesia TTS Setup

Cartesia is a cloud-based text-to-speech service that produces high-quality, low-latency speech. It connects to the agent through the official `livekit-plugins-cartesia` plugin. A Cartesia API key is required.

## Prerequisites

- A **Cartesia account** at https://cartesia.ai
- A **Cartesia API key**

## Quick Start

### 1. Get a Cartesia API key

1. Sign up or log in at https://play.cartesia.ai
2. Navigate to your account settings or API section
3. Generate an API key

### 2. Add the key to .env.local

```
CARTESIA_API_KEY=sk_car_your-key-here
```

### 3. Set the engine in config.yaml

```yaml
tts:
  engine: "cartesia"
```

### 4. Start the app

```bash
./start.sh start
```

No local server is needed -- the agent calls the Cartesia cloud API directly.

## Configuration

All Cartesia settings live under `tts.cartesia` in `config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `model` | `sonic-3` | Cartesia model name |
| `voice` | *(required)* | Cartesia voice ID (UUID format) |

The API key is read from the `CARTESIA_API_KEY` environment variable in `.env.local`.

## Available Voices

Cartesia provides a library of pre-built voices. Each voice is identified by a UUID. You can browse and audition voices at https://play.cartesia.ai.

Some suggested voices from the LiveKit documentation:

| Name | Description | Voice ID |
|------|-------------|----------|
| Blake | Energetic American adult male | *(find on Cartesia site)* |
| Daniela | Calm, trusting Mexican female | *(find on Cartesia site)* |
| Jacqueline | Confident young American female | *(find on Cartesia site)* |
| Robyn | Neutral, mature Australian female | *(find on Cartesia site)* |

To use a voice, copy its UUID from the Cartesia voice library and paste it as the `voice` value in `config.yaml`:

```yaml
tts:
  cartesia:
    model: "sonic-3"
    voice: "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
```

Cartesia also supports voice cloning -- see their documentation for details.

## Architecture

```
Agent (agent.py)
  └─ cartesia.TTS(model="sonic-3", voice="...")
       └─ HTTPS request  ──→  Cartesia Cloud API
                                 └─ Cloud inference (requires internet)
```

## Cost

Cartesia is a paid cloud service. Costs are based on the number of characters synthesized. Check https://cartesia.ai/pricing for current rates. For local alternatives with no cloud costs, see `docs/kokoro-readme.md` or `docs/piper-readme.md`.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `401 Unauthorized` | Check that `CARTESIA_API_KEY` is set correctly in `.env.local` |
| `Invalid voice` error | Verify the voice UUID is correct (copy from Cartesia voice library) |
| No audio output | Ensure the agent is running and connected to the LiveKit room |
| High latency | Cartesia depends on internet connectivity; check your network |
| Unexpected charges | Monitor usage at https://play.cartesia.ai; consider switching to a local engine |

## Links

- [Cartesia website](https://cartesia.ai)
- [Cartesia voice library](https://play.cartesia.ai)
- [LiveKit Cartesia plugin docs](https://docs.livekit.io/agents/models/tts/plugins/cartesia/)
- [livekit-plugins-cartesia on PyPI](https://pypi.org/project/livekit-plugins-cartesia/)
