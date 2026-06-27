# D&D Dice Detector

Real-time physical dice detection for D&D with Foundry VTT integration.

## Features

- **Live Camera Detection**: Detect dice from your webcam in real-time
- **Multiple Dice Support**: D4, D6, D8, D10, D12, D20, D100
- **Multi-Stage Rolling**: Roll formulas requiring more dice than you own across multiple throws
- **Modifier Presets**: Configure attack rolls, damage, saving throws with bonuses
- **Confidence System**: Manual correction for uncertain detections
- **Foundry VTT Integration**: Send roll results via browser extension
- **Local API**: FastAPI-based REST and WebSocket API

## Installation

This project uses **uv** for dependency management.

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and enter the project
cd dice_detector

# Sync dependencies
uv sync
```

## Usage

### Start the API Server

```bash
uv run uvicorn dice_detector.api:app --reload
```

The API will be available at:
- HTTP: `http://localhost:8765`
- WebSocket: `ws://localhost:8765/ws`
- API Docs: `http://localhost:8765/docs`

### Run Tests

```bash
uv run pytest --cov
```

### Development Tools

```bash
# Linting
uv run ruff check src tests

# Type checking
uv run mypy src

# Format code
uv run ruff format src tests
```

## Architecture

```
dice_detector/
├── src/dice_detector/
│   ├── api/           # FastAPI REST and WebSocket API
│   ├── models/        # Pydantic data models
│   ├── camera/        # Webcam capture
│   ├── vision/        # Dice detection and recognition
│   ├── roll_engine/   # Roll calculation and presets
│   ├── foundry/       # Foundry VTT integration
│   ├── ui/            # GUI application (future)
│   ├── training/      # Dataset and model training
│   └── config/        # Settings management
├── extension/         # Browser extension for Foundry
├── tests/             # Test suite
└── data/              # Presets and samples
```

## Multi-Stage Rolling

The app supports rolling formulas that require more dice than you physically own:

```
Formula: 2d20 + 2d4
Physical dice: 1x D20, 1x D4

Stage 1: Roll D20 (13) and D4 (2)
Stage 2: Roll D20 (18) and D4 (4)

Result: 13 + 18 + 2 + 4 = 37
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Current app status |
| `/config` | GET/POST | Configuration |
| `/presets` | GET/POST | Modifier presets |
| `/roll/start` | POST | Start a roll session |
| `/roll/current` | GET | Get current session |
| `/roll/accept` | POST | Accept detected dice |
| `/roll/confirm` | POST | Confirm and complete roll |
| `/roll/cancel` | POST | Cancel current session |
| `/roll/manual` | POST | Submit manual roll |
| `/foundry/payload/latest` | GET | Get latest Foundry payload |
| `/ws` | WebSocket | Real-time updates |

## Browser Extension

The browser extension connects the local app to Foundry VTT:

1. Load the extension from `extension/` in Chrome/Firefox developer mode
2. Start the dice detector API server
3. Open Foundry VTT in your browser
4. Use the extension popup to send rolls to Foundry

## Configuration

Edit `config/settings.yaml` to configure:
- Camera source
- Detection area/zone
- Confidence thresholds
- Auto-post settings
- Foundry connection details

## Foundry VTT Setup

1. Install the companion Foundry module (see `foundry_module/`)
2. Enable WebSocket connection in Foundry settings
3. Configure connection in dice detector settings

## Acknowledgments

Huge shoutout to [dianaavlis2002](https://www.artstation.com/dianasilva8) on Sketchfab/Artstation for the amazing RPG dice set used in this project's Blender scenes for synthetic data generation!

## License

MIT License
