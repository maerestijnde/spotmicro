# Contributing to MicroSpot

Thanks for your interest in contributing to MicroSpot!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/maerestijnde/spotmicro.git`
3. Create a feature branch: `git checkout -b feature/my-feature`
4. Make your changes
5. Push to your fork: `git push origin feature/my-feature`
6. Open a Pull Request

## Development Setup

### On Raspberry Pi (with hardware)

```bash
cd /home/spot/microspot
pip install -r requirements.txt
./start.sh
```

### On your development machine (simulation)

```bash
pip install -r requirements.txt
cd src
python microspot_app.py  # Runs in simulation mode without hardware
```

## Code Style

- Follow PEP 8 guidelines
- Use meaningful variable names
- Add docstrings to functions and classes
- Keep functions focused and small

## Hardware Considerations

- All hardware-dependent code should gracefully handle simulation mode
- Check `SIMULATION_MODE` flag before accessing hardware
- Test both with and without hardware when possible

## Pull Request Guidelines

- Keep PRs focused on a single feature or fix
- Update documentation if needed
- Test on actual hardware if your changes affect servo control
- Follow the PR template

## Reporting Issues

- Use the issue templates
- Include relevant logs and hardware info
- Describe steps to reproduce

## Community

- Be respectful and constructive
- Help others when you can
- Share your builds and modifications!

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
