# Development Guide

This guide covers how to set up a development environment, run tests, and contribute to the project.

## Prerequisites

- Python 3.11 or later
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip
- Git
- Docker (optional, for local Home Assistant testing)

## Setting Up Your Development Environment

### 1. Clone the Repository

```bash
git clone https://github.com/cognitivegears/ha-escpos-thermal-printer.git
cd ha-escpos-thermal-printer
```

### 2. Install Dependencies

Using uv (recommended):

```bash
uv sync --all-extras --group dev
```

Or using pip:

```bash
pip install -e ".[dev]"
```

### 3. Install Pre-commit Hooks

```bash
pre-commit install
```

This sets up automatic linting and formatting checks before each commit.

## Running Tests

### Run All Tests

```bash
uv run pytest -q
```

Or without uv:

```bash
pytest -q
```

### Run a Specific Test File

```bash
uv run pytest tests/test_services_text.py -v
```

### Run Integration Tests

Integration tests are excluded by default. To run them:

```bash
uv run pytest -m integration
```

### Run with Coverage

```bash
uv run pytest --cov=custom_components/escpos_printer --cov-report=html
```

## Linting and Type Checking

### Run Ruff (Linter)

```bash
uv run ruff check .
```

Auto-fix issues:

```bash
uv run ruff check . --fix
```

### Run Mypy (Type Checker)

```bash
uv run mypy custom_components/escpos_printer
```

### Run All Pre-commit Checks

```bash
pre-commit run --all-files
```

## Local Testing with Home Assistant

### Using Docker Compose

The easiest way to test the integration locally is with Docker:

```bash
# Start Home Assistant (runs at http://localhost:8123)
docker compose up -d

# View logs
docker compose logs -f

# Stop and remove container
docker compose down
```

The Docker setup mounts `custom_components/` into the container. Changes to your code are reflected after restarting Home Assistant.

Once running:
1. Open http://localhost:8123
2. Complete the onboarding wizard
3. Go to **Settings** > **Devices & services** > **Add Integration**
4. Search for "ESC/POS Thermal Printer"

### Framework Smoke Test

Test basic framework functionality without a full Home Assistant instance:

```bash
uv run python scripts/framework_smoke_test.py
```

## Project Structure

```
ha-escpos-thermal-printer/
├── custom_components/
│   └── escpos_printer/
│       ├── __init__.py          # Integration setup, entry points
│       ├── binary_sensor.py     # Printer status sensor
│       ├── capabilities.py      # Printer profile detection
│       ├── const.py             # Constants and defaults
│       ├── diagnostics.py       # Debug info collection
│       ├── manifest.json        # Integration metadata
│       ├── notify.py            # Notification platform
│       ├── security.py          # Input validation
│       ├── services.py          # Service handlers
│       ├── services.yaml        # Service definitions
│       ├── strings.json         # UI strings
│       ├── text_utils.py        # UTF-8 transcoding
│       ├── _config_flow/        # Configuration flow subpackage
│       │   ├── flow.py          # Main ConfigFlow class
│       │   ├── usb_helpers.py   # USB discovery and validation
│       │   └── network_helpers.py # Network validation
│       └── printer/             # Printer adapter subpackage
│           ├── base.py          # Abstract adapter base class
│           ├── network_adapter.py # Network (TCP/IP) adapter
│           ├── usb_adapter.py   # USB adapter
│           ├── config.py        # Config dataclasses
│           └── factory.py       # Adapter factory
├── tests/
│   ├── integration_tests/       # Full integration tests
│   └── test_*.py                # Unit tests
├── scripts/                     # Utility scripts
├── docs/                        # Documentation
└── pyproject.toml               # Project configuration
```

## Key Patterns

### Async I/O

All printer operations run on executor threads to avoid blocking the Home Assistant event loop:

```python
await hass.async_add_executor_job(blocking_function, arg1, arg2)
```

### Service Registration

Services are registered globally once (not per config entry) and resolve device targets at runtime. See `services.py` for the implementation.

### Security Validation

All user input is validated before reaching the printer. See `security.py` for validation functions.

### Printer Adapters

The integration uses a factory pattern for printer adapters:

- `EscposPrinterAdapterBase` - Abstract base class defining the interface
- `NetworkPrinterAdapter` - TCP/IP network connections
- `UsbPrinterAdapter` - Direct USB connections
- `create_printer_adapter()` - Factory function that instantiates the correct adapter

Both adapters implement identical operations, allowing services to work transparently with either connection type.

## Dependency Management

- **pyproject.toml** is the source of truth for all dependencies
- **manifest.json** must mirror runtime dependencies
- Use exact version pins (e.g., `==1.2.3`) for reproducible builds
- Renovate automatically updates dependencies

### Syncing manifest.json

If you add or update dependencies in pyproject.toml:

```bash
python scripts/sync_manifest_requirements.py
```

### Checking for Drift

```bash
python scripts/check_requirements_sync.py
```

## Making Changes

### Before Submitting a PR

1. Run the full test suite: `uv run pytest -q`
2. Run linting: `uv run ruff check .`
3. Run type checking: `uv run mypy custom_components/escpos_printer`
4. Run pre-commit: `pre-commit run --all-files`
5. Update documentation if needed

### Commit Messages

Use clear, descriptive commit messages:

- `Add support for printer model X`
- `Fix connection timeout handling`
- `Update dependencies`

### Code Style

- Follow existing patterns in the codebase
- Use type hints for function signatures
- Keep functions focused and reasonably sized
- Add docstrings for public functions

## Testing Without a Physical Printer

The test suite uses mocks for all printer operations. You don't need a physical printer to run tests or develop features.

For manual testing, you can:

1. Use a virtual printer emulator (see `tests/integration_tests/`)
2. Connect a real printer to your network or via USB
3. Use the binary sensor to verify connectivity without printing

**Note:** USB discovery functions are mocked in tests. To test USB functionality manually, connect a real USB printer.

## Troubleshooting Development Issues

### Import Errors

If you see import errors, make sure you've installed in development mode:

```bash
uv sync --all-extras --group dev
```

### Test Failures

Set the environment variable to skip platform forwarding in tests:

```bash
ESC_POS_DISABLE_PLATFORMS=1 uv run pytest -q
```

### Pre-commit Failures

If pre-commit fails, try updating the hooks:

```bash
pre-commit autoupdate
pre-commit run --all-files
```

## Resources

- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [python-escpos Documentation](https://python-escpos.readthedocs.io/)
- [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
