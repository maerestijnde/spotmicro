# CLAUDE.md - Project Instructions for Claude Code

## Project Overview

MicroSpot is a Raspberry Pi-based SpotMicro quadruped robot control system. It provides walking control via trot gait, inverse kinematics, IMU-based balance correction, PS4/PS5/Xbox controller support, a FastAPI REST backend, and Streamlit/Dash web UIs.

## Quick Reference

- **Language**: Python 3.9+
- **Package name**: `microspot`
- **Main source**: `src/`
- **Backend**: FastAPI on port 8000 (`src/microspot_app.py`)
- **Web UI**: Streamlit on port 8501 (`src/app.py`) or Dash on port 8050 (`src/dash_app.py`)
- **Deploy target**: Raspberry Pi at `ssh spot@microspot`, code at `/home/spot/microspot/`

## Commands

### Formatting & Linting

```bash
# Format code
black src/

# Sort imports
isort src/

# Lint
flake8 src/
```

### Testing

```bash
# Run all tests
python -m pytest src/tests/

# Run a specific test
python -m pytest src/tests/test_walk.py
```

### Install dev dependencies

```bash
pip install -e ".[dev]"
```

### Start the application (on Raspberry Pi)

```bash
./start.sh
```

## Code Style

- **Line length**: 127 characters (configured for black, isort, and flake8)
- **Formatter**: black with `--target-version py39`
- **Import sorting**: isort with `profile = "black"`
- **Flake8 ignores**: E203, W503

## Architecture

```
Controller (PS4/Xbox) ──► FastAPI Backend (port 8000)
                              ├── gait.py           (trot gait controller, 50Hz loop)
                              ├── balance.py         (IMU balance, MPU6050)
                              ├── ik_interface.py    (foot XYZ → servo angles)
                              ├── trajectory.py      (foot trajectory generation)
                              └── stability_monitor.py (stability state machine)
                          ▼
                     Web UI (Streamlit/Dash)
                          └── src/components/   (UI pages)
```

## Key Files

| File | Purpose |
|------|---------|
| `src/microspot_app.py` | FastAPI backend, main entry point, servo control |
| `src/gait.py` | Trot gait controller (angle-based + IK-based modes) |
| `src/balance.py` | IMU balance controller (MPU6050, proportional correction) |
| `src/ik_interface.py` | IK bridge: foot XYZ positions to servo angles |
| `src/trajectory.py` | Foot trajectory generator (swing/stance phases) |
| `src/ps4_controller.py` | PS4/PS5 controller input handler |
| `src/xbox_controller.py` | Xbox 360 controller input handler |
| `src/calibration.json` | Per-servo calibration data (offsets, directions, neutrals) |
| `src/tuning.json` | Persistent gait/balance tuning parameters |

## Hardware Mapping

12 servos (MG996R) via PCA9685 PWM driver over I2C:

```
FL (left):  hip=ch0,  knee=ch1,  ankle=ch2   (direction=-1)
FR (right): hip=ch3,  knee=ch4,  ankle=ch5   (direction=+1)
RL (left):  hip=ch6,  knee=ch7,  ankle=ch8   (direction=-1)
RR (right): hip=ch9,  knee=ch10, ankle=ch11  (direction=+1)
```

## Critical Rules

- **Do NOT modify `src/kinematics/`** - it's an external working library
- **Do NOT modify `src/calibration.json`** - it's already calibrated for the physical robot
- **Do NOT use `set_servo(ch, angle, True)` after IK** - IK already applies calibration
- All hardware imports are wrapped in `try/except ImportError` for simulation mode - maintain this pattern
- Servo angles are "logical" where 90 degrees = calibrated neutral

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LOG_LEVEL` | INFO | General log level |
| `LOG_LEVEL_GAIT` | WARNING | Gait controller log level |
| `LOG_LEVEL_SERVO` | WARNING | Servo control log level |
| `LOG_LEVEL_IMU` | WARNING | IMU log level |
| `LOG_LEVEL_API` | INFO | API log level |
| `MICROSPOT_BACKEND` | `http://localhost:8000` | Backend URL override for UI |

## Test Notes

The tests in `src/tests/` are **hardware tests** designed to run on the physical robot. They control real servos and require the PCA9685 hardware. They are not unit tests that can run in CI.
