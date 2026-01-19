# MicroSpot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)

A Raspberry Pi-based SpotMicro quadruped robot with inverse kinematics, real-time balance control, and PS4/PS5 controller support.

<!-- Drop your GIF/image in the docs/ folder and update the filename below -->
<p align="center">
  <img src="docs/spotmicro_small.gif" alt="MicroSpot Robot" width="500">
</p>

## Features

- **Trot Gait Walking** - Smooth diagonal gait with configurable speed and step height
- **PS4/PS5 Controller** - Full Bluetooth control for walking, poses, and body orientation
- **Real-time Balance** - MPU6050 IMU integration for active pitch/roll stabilization
- **Servo Calibration** - Web-based wizard with per-servo offset and direction tuning
- **Dual Web UI** - Streamlit dashboard + FastAPI backend with 3D visualization
- **Inverse Kinematics** - SpotMicro kinematics library for precise foot placement

## Hardware

| Component | Specification |
|-----------|--------------|
| Controller | Raspberry Pi 4/5 |
| Servos | 12x MG996R (180°) |
| PWM Driver | PCA9685 @ I2C 0x40 |
| IMU | MPU6050 @ I2C 0x68 |
| Frame | 3D printed SpotMicro |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/maerestijnde/spotmicro.git
cd spotmicro

# Install dependencies
pip install -r requirements.txt

# Start the robot
./start.sh
```

Access the interfaces:
- **http://microspot:8000** - FastAPI backend + HTML UI
- **http://microspot:8501** - Streamlit dashboard

## PS4 Controller

| Input | Function |
|-------|----------|
| Left Stick | Walk forward/backward, strafe |
| Right Stick | Body pitch/roll |
| L2/R2 | Turn left/right |
| L1/R1 | Body height up/down |
| D-pad | Preset poses (stand/sit/rest) |
| Triangle | Toggle IMU balance |
| Options | Emergency stop |

Pair controller:
```bash
./pair_ps4.sh
```

## Project Structure

```
spotmicro/
├── src/
│   ├── microspot_app.py    # FastAPI backend
│   ├── app.py              # Streamlit UI
│   ├── gait.py             # Trot gait controller
│   ├── balance.py          # IMU balance control
│   ├── ps4_controller.py   # Controller input
│   ├── components/         # UI components
│   ├── kinematics/         # IK library
│   └── tests/              # Test scripts
├── start.sh                # Quick start script
├── requirements.txt
└── README.md
```

## API

Full REST API available at `/docs` (FastAPI auto-generated).

Key endpoints:
- `POST /api/pose/{pose_name}` - Apply pose (neutral, stand, sit, rest)
- `POST /api/gait/start` - Start walking
- `POST /api/gait/stop` - Stop walking
- `POST /api/balance/enable` - Toggle balance control
- `GET /api/status` - System status

## Configuration

Servo calibration is stored in `src/calibration.json`. Use the Streamlit UI calibration wizard or edit directly:

```json
{
  "servos": {
    "0": {
      "channel": 0,
      "leg": "FL",
      "joint": "hip",
      "offset": 0,
      "direction": -1,
      "neutral_angle": 90
    }
  }
}
```

## Development

```bash
# Run in simulation mode (no hardware)
cd src
python microspot_app.py

# Run tests
python -m pytest src/tests/

# Format code
black src/
```

## Credits

Built on the shoulders of giants:
- [mike4192/spotMicro](https://github.com/mike4192/spotMicro) - Kinematics library
- [SpotMicroAI](https://gitlab.com/public-open-source/spotmicroai) - Community project
- [KDY0523](https://www.thingiverse.com/thing:3445283) - Original 3D design

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.
