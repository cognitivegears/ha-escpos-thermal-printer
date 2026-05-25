<!--
Thanks for contributing! A few quick checks before submitting will save
review time. Delete sections that don't apply.
-->

## Summary

<!-- One or two sentences. What changes, why. -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (a service / config / API surface changed in a way users will notice)
- [ ] Documentation / CI / chore only

## Checklist

- [ ] Tests added or updated for the change (or the change is doc-only).
- [ ] `uv run pytest -q` passes locally (or the CI run is expected to).
- [ ] `uv run ruff check .` and `uv run mypy custom_components/` are clean.
- [ ] **`CHANGELOG.md`** has an entry under `[Unreleased]` describing the
  change. Security-relevant fixes go under `### Security`; user-visible
  behaviour changes go under `### Changed` or `### Breaking changes`.
- [ ] If a service surface changed, `services.yaml` + `docs/services.md`
  + the relevant `docs/*.md` were updated in lockstep.
- [ ] If a dependency changed, `manifest.json` and `pyproject.toml`
  are in sync (`python scripts/check_requirements_sync.py`).
- [ ] If any inline docstring became inaccurate, it was updated.

## Test plan

<!-- How did you verify the change? Include relevant command output or
     screenshots if the change is user-visible. -->
