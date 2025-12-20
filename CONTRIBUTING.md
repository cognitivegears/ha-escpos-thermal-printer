Contributing

Thanks for your interest in improving the ESC/POS Thermal Printer integration for Home Assistant!

Getting Started
- Use Python 3.13.2+
- Install uv (https://github.com/astral-sh/uv) and pre-commit
- Create a virtualenv and install dev tools:
  - uv sync --all-extras --group dev
  - pre-commit install

Code Style & Quality
- Linting: ruff (configured via pyproject)
- Formatting: black (line length 100)
- Typing: mypy (strict-ish, see pyproject)
- Tests: pytest (asyncio mode auto)

Running Checks Locally
- Lint & tests: uv run pytest -q
- Static checks: uv run ruff check . && uv run mypy
- Pre-commit (runs on commit automatically): pre-commit run --all-files

Developer Utilities
- Framework smoke test (no Home Assistant required):
  - Run: uv run python scripts/framework_smoke_test.py
  - Purpose: quick validation of the emulator, utilities, and scenario modules

Dependency Policy (pyproject.toml and manifest.json)
- Exact pins only (no version ranges) for core runtime deps:
  - python-escpos, Pillow, qrcode, python-barcode
- pyproject.toml is the source of truth. Renovate updates this file.
- manifest.json must mirror the exact pins (Home Assistant installs from manifest).

Workflow with uv + Renovate
1) Update or add pins in pyproject.toml
   - Example: uv add "Pillow==11.3.0"
   - Lock: uv lock
2) Sync manifest.json requirements
   - Auto-check: python scripts/check_requirements_sync.py
   - Auto-fix (writes manifest): python scripts/sync_manifest_requirements.py
3) Commit changes. Pre-commit will block if files drift.

Renovate Integration
- Renovate bumps exact pins in pyproject.toml (rangeStrategy: pin)
- A regex manager keeps custom_components/escpos_printer/manifest.json in sync
- A postUpgradeTasks step runs python scripts/sync_manifest_requirements.py to ensure manifest matches pyproject/uv.lock

Hassfest & HACS Validation
- The repo includes CI workflows for Hassfest and HACS validation
- On push/PR, GitHub Actions runs hassfest to verify Home Assistant integration metadata

Submitting Changes
- Fork and create a feature branch
- Include tests for new functionality when possible
- Ensure pre-commit hooks and CI checks pass
- Open a pull request with a concise description and rationale
