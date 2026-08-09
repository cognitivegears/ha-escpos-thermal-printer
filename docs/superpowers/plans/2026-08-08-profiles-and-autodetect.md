# Printer Profiles & Autodetect Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make unlisted/clone printers work out of the box: per-entry width override, USB profile suggestion, clone alias table, profile-driven image-implementation defaults, and `impl` as a first-class config option.

**Architecture:** All capability logic stays in `custom_components/escpos_printer/capabilities/` (two new modules: `aliases.py`, `suggestions.py`). Config plumbing follows the existing options-over-data pattern (`_shared_print_config`). Image `impl` resolution is computed once per entry at adapter setup (executor job — the capabilities YAML load is blocking) and consulted by `prepare_image()`.

**Tech Stack:** Python 3.14, Home Assistant custom integration, python-escpos 3.1 (pinned), voluptuous, pytest + pytest-homeassistant-custom-component.

**Spec:** `docs/superpowers/specs/2026-08-08-profiles-and-autodetect-design.md`

## Global Constraints

- Work on a feature branch off `main` (e.g. `feature/profiles-autodetect`) — never commit to `main`.
- Do NOT touch dependency pins (`python-escpos==3.1` stays).
- Every user-visible change gets a CHANGELOG.md entry under `## [Unreleased]` (done once in Task 8).
- Version bump to **1.1.0** in `manifest.json` AND `pyproject.toml` (Task 8 only).
- `strings.json` edits must be mirrored in `custom_components/escpos_printer/translations/en.json` (the sync script only covers the `services` key).
- services.yaml: `preview_image` deliberately omits `impl` — update only the FIVE printing image services, never add `impl` to `preview_image`.
- Do not re-add any `center`/`image_center` field to services.yaml (deliberately removed).
- Run commands with `uv run` (e.g. `uv run pytest -q`). Unit tests may need `ESC_POS_DISABLE_PLATFORMS=1`.
- `except A, B:` (PEP 758, no parens) is valid in this codebase — don't "fix" it.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Per-entry width override + "Generic (no profile)" rename

**Files:**

- Modify: `custom_components/escpos_printer/const.py` (near line 17, next to `CONF_LINE_WIDTH`)
- Modify: `custom_components/escpos_printer/printer/config.py:39-46` (`BasePrinterConfig`)
- Modify: `custom_components/escpos_printer/__init__.py:91-110` (`_shared_print_config`)
- Modify: `custom_components/escpos_printer/printer/base_adapter.py:489-539` (`get_profile_pixel_width`)
- Modify: `custom_components/escpos_printer/capabilities/profiles.py:22`
- Modify: `custom_components/escpos_printer/_config_flow/settings_steps.py:172-228` (codepage step)
- Modify: `custom_components/escpos_printer/_config_flow/options_flow.py:279-308` (`_build_options_schema`)
- Modify: `custom_components/escpos_printer/strings.json`, `custom_components/escpos_printer/translations/en.json`
- Test: `tests/test_width_override.py` (new)

**Interfaces:**

- Consumes: existing `BasePrinterConfig`, `create_printer_adapter` (from `custom_components.escpos_printer.printer`).
- Produces: `CONF_WIDTH_PIXELS = "width_pixels"` in const.py; `BasePrinterConfig.width_pixels: int | None = None`; `get_profile_pixel_width()` returns the override when set. Later tasks rely on `CONF_WIDTH_PIXELS` existing.

- [ ] **Step 1: Create the feature branch**

```bash
git checkout -b feature/profiles-autodetect
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_width_override.py` (follow import style of `tests/test_capabilities.py`):

```python
"""Tests for the per-entry paper width override."""

from custom_components.escpos_printer.printer import create_printer_adapter
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig


def test_width_override_beats_profile() -> None:
    config = NetworkPrinterConfig(host="127.0.0.1", profile="TM-T20II", width_pixels=576)
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 576


def test_width_override_without_profile() -> None:
    config = NetworkPrinterConfig(host="127.0.0.1", profile=None, width_pixels=384)
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 384


def test_no_override_uses_profile() -> None:
    config = NetworkPrinterConfig(host="127.0.0.1", profile="TM-T20II")
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 512  # TM-T20II declares 512px
```

(If `create_printer_adapter` isn't importable from `custom_components.escpos_printer.printer`, check `custom_components/escpos_printer/printer/__init__.py` for the actual export and adjust. If TM-T20II's width isn't 512, print `escpos.capabilities.CAPABILITIES['profiles']['TM-T20II']['media']` and use the real value.)

- [ ] **Step 3: Run test to verify it fails**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_width_override.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'width_pixels'`

- [ ] **Step 4: Implement**

`const.py`, directly under `CONF_LINE_WIDTH = "line_width"`:

```python
CONF_WIDTH_PIXELS = "width_pixels"  # per-entry image width override (overrides profile)
```

`printer/config.py`, add to `BasePrinterConfig` after `line_width`:

```python
    # Per-entry override for the printable width in pixels. Beats the
    # profile's media.width.pixels; None means "use the profile".
    width_pixels: int | None = None
```

`__init__.py` `_shared_print_config`, add to the returned dict (and add `CONF_WIDTH_PIXELS` to the existing `from .const import` block):

```python
        "width_pixels": (
            int(raw_width) if (raw_width := opt.get(CONF_WIDTH_PIXELS, data.get(CONF_WIDTH_PIXELS))) else None
        ),
```

`base_adapter.py` `get_profile_pixel_width`, insert at the top of the method (before the `_profile_width_lookup_done` check):

```python
        override = getattr(self._config, "width_pixels", None)
        if override:
            # User-set width beats the profile and retires any open
            # profile_width_fallback repairs issue for this entry.
            if hass is not None:
                self._clear_profile_width_repair_issue(hass)
            return int(override)
```

`capabilities/profiles.py:22` — change:

```python
    choices: list[tuple[str, str]] = [(PROFILE_AUTO, "Generic (no profile)")]
```

Also update the docstring on line 12 ("Auto-detect (Default)" → "Generic (no profile)").

`settings_steps.py` codepage step: add to the `data_schema` dict (import `CONF_WIDTH_PIXELS` from `..const`):

```python
                vol.Optional(CONF_WIDTH_PIXELS): vol.All(vol.Coerce(int), vol.Range(min=16, max=2048)),
```

and in the entry-creation branch, after `data = {...}` is built:

```python
            if user_input.get(CONF_WIDTH_PIXELS):
                data[CONF_WIDTH_PIXELS] = int(user_input[CONF_WIDTH_PIXELS])
```

`options_flow.py` `_build_options_schema`, add after the `CONF_LINE_WIDTH` field:

```python
            vol.Optional(
                CONF_WIDTH_PIXELS,
                description={
                    "suggested_value": opts.get(CONF_WIDTH_PIXELS, data.get(CONF_WIDTH_PIXELS))
                },
            ): vol.All(vol.Coerce(int), vol.Range(min=16, max=2048)),
```

`strings.json`:

- `config.step.codepage.data`: add `"width_pixels": "Paper width in pixels (optional)"`.
- If the step has a `data_description` block, add: `"width_pixels": "Overrides the profile's printable width for images. Leave empty to use the profile. Common values: 384 (58 mm), 576 (80 mm)."`
- `options.step.init.data`: add the same `"width_pixels"` label (+ description if the block exists).
- `issues.profile_width_fallback.description`: replace the `**To fix:**` sentence with:

```text
**To fix:** open the integration's options and set “Paper width in pixels” (384 for 58 mm, 576 for 80 mm printers), pick a closer matching printer profile, or set `image_width` explicitly in your service calls.
```

Mirror all `strings.json` edits into `translations/en.json` (same JSON paths).

- [ ] **Step 5: Run tests**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_width_override.py -v`
Expected: PASS (all 3)

- [ ] **Step 6: Fix label assertions and run the affected suites**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/ -q -k "capabilit or config_flow or options"`
Any test asserting the old `"Auto-detect (Default)"` label: update it to `"Generic (no profile)"`.
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: per-entry paper width override; rename Auto-detect to Generic

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Clone alias table + alias-aware custom profile entry

**Files:**

- Create: `custom_components/escpos_printer/capabilities/aliases.py`
- Modify: `custom_components/escpos_printer/capabilities/profiles.py` (add `resolve_profile_name`)
- Modify: `custom_components/escpos_printer/capabilities/__init__.py` (exports)
- Modify: `custom_components/escpos_printer/_config_flow/settings_steps.py:100-111` (custom profile step)
- Modify: `custom_components/escpos_printer/_config_flow/options_flow.py:343-365` (options custom profile step)
- Test: `tests/test_profile_aliases.py` (new)

**Interfaces:**

- Consumes: `_get_capabilities()` from `capabilities/loader.py`.
- Produces: `normalize_model(name: str) -> str`; `PROFILE_ALIASES: dict[str, str]` (normalized alias → bundled profile key); `resolve_alias(name: str) -> str | None`; `resolve_profile_name(raw: str | None) -> str | None` (exact key, case-insensitive key, or alias → bundled key; else None). Task 3 imports `PROFILE_ALIASES` and `normalize_model`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_profile_aliases.py`:

```python
"""Tests for clone alias table and profile name resolution."""

from custom_components.escpos_printer.capabilities.aliases import (
    PROFILE_ALIASES,
    normalize_model,
    resolve_alias,
)
from custom_components.escpos_printer.capabilities.loader import _get_capabilities
from custom_components.escpos_printer.capabilities.profiles import resolve_profile_name


def test_normalize_model() -> None:
    assert normalize_model("CT-S601 II") == "cts601ii"
    assert normalize_model("ZJ_5890-K") == "zj5890k"


def test_every_alias_target_exists_in_bundled_db() -> None:
    profiles = _get_capabilities()["profiles"]
    for alias, target in PROFILE_ALIASES.items():
        assert alias == normalize_model(alias), f"alias key {alias!r} must be pre-normalized"
        assert target in profiles, f"alias {alias!r} -> {target!r} not in bundled DB"


def test_resolve_alias() -> None:
    assert resolve_alias("CT-S601II") == "CT-S651"
    assert resolve_alias("nonsense-model") is None


def test_resolve_profile_name() -> None:
    assert resolve_profile_name("TM-T20II") == "TM-T20II"  # exact
    assert resolve_profile_name("tm-t20ii") == "TM-T20II"  # case-insensitive
    assert resolve_profile_name("CT-S601II") == "CT-S651"  # alias
    assert resolve_profile_name("no-such-printer") is None
    assert resolve_profile_name("") is None
    assert resolve_profile_name(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_profile_aliases.py -v`
Expected: FAIL — `ModuleNotFoundError: ...capabilities.aliases`

- [ ] **Step 3: Implement**

Create `capabilities/aliases.py`:

```python
"""Clone/equivalent-model aliases onto bundled escpos-printer-db profiles.

Aliases route rebadged or near-equivalent hardware to an existing
bundled profile. They only ever improve defaults (width, codepages) —
they never gate behavior. Genuinely new hardware belongs upstream in
escpos-printer-db, not here.

Keys MUST be pre-normalized with :func:`normalize_model` (guard test:
``test_every_alias_target_exists_in_bundled_db``). Each entry cites its
basis.
"""

from __future__ import annotations

import re

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_model(name: str) -> str:
    """Lowercase and strip everything but letters/digits ("CT-S601 II" -> "cts601ii")."""
    return _NORMALIZE_RE.sub("", name.casefold())


PROFILE_ALIASES: dict[str, str] = {
    # Citizen CT-S601/651 family: shared command reference
    # (escpos-printer-db issue #49), same 80mm/640px/203dpi class per
    # Citizen spec pages. S801/S851 excluded until dpi verified.
    "cts601": "CT-S651",
    "cts601ii": "CT-S651",
    "cts651ii": "CT-S651",
    # Zijiang 5890 family: POS-5890 profile explicitly covers rebadges
    # ("also marketed under various other names").
    "zj5890": "POS-5890",
    "zj5890k": "POS-5890",
    "pos5890k": "POS-5890",
}


def resolve_alias(name: str) -> str | None:
    """Resolve a model name to a bundled profile key via the alias table."""
    return PROFILE_ALIASES.get(normalize_model(name))
```

Add to `capabilities/profiles.py`:

```python
def resolve_profile_name(raw: str | None) -> str | None:
    """Resolve user input to a bundled profile key.

    Accepts an exact key, a case-insensitive key, or a clone alias
    (see ``aliases.PROFILE_ALIASES``). Returns None when nothing matches.
    """
    if not raw:
        return None
    from .aliases import resolve_alias  # noqa: PLC0415

    raw = raw.strip()
    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})
    if raw in profiles:
        return raw
    lowered = {key.casefold(): key for key in profiles}
    if raw.casefold() in lowered:
        return lowered[raw.casefold()]
    target = resolve_alias(raw)
    if target and target in profiles:
        return target
    return None
```

`capabilities/__init__.py`: import and re-export `resolve_profile_name` (from `.profiles`), `normalize_model`, `PROFILE_ALIASES`, `resolve_alias` (from `.aliases`); add all four to `__all__` (keep it sorted).

`settings_steps.py` custom profile step (lines 100-111) — replace the validation block:

```python
            resolved = await self.hass.async_add_executor_job(resolve_profile_name, custom_profile)
            if not resolved:
                _LOGGER.warning("Invalid profile name: %s", custom_profile)
                errors["base"] = "invalid_profile"
            else:
                self._user_data[CONF_PROFILE] = resolved
                return await self.async_step_codepage()
```

(import `resolve_profile_name` where `is_valid_profile` is imported; drop the `is_valid_profile` import if now unused in this module).

`options_flow.py` options custom profile step (lines 343-354) — same replacement, storing `data[CONF_PROFILE] = resolved`.

- [ ] **Step 4: Run tests**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_profile_aliases.py tests/ -q -k "alias or custom_profile or config_flow"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: clone alias table; custom profile entry resolves aliases

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: USB profile suggestion module

**Files:**

- Create: `custom_components/escpos_printer/capabilities/suggestions.py`
- Modify: `custom_components/escpos_printer/capabilities/__init__.py` (exports)
- Test: `tests/test_profile_suggestions.py` (new)

**Interfaces:**

- Consumes: `PROFILE_ALIASES`, `normalize_model` (Task 2); `_get_capabilities()`.
- Produces: `suggest_profile(product: str | None, vid: int | None, pid: int | None) -> str | None`. Task 4 calls it from the USB config flow.

- [ ] **Step 1: Write the failing test**

Create `tests/test_profile_suggestions.py`:

```python
"""Tests for USB descriptor / VID:PID profile suggestion."""

from custom_components.escpos_printer.capabilities.suggestions import suggest_profile


def test_descriptor_exact_model() -> None:
    assert suggest_profile("TM-T20II", 0x04B8, 0x0E15) == "TM-T20II"


def test_descriptor_longest_match_wins() -> None:
    # "tmt88iii" contains "tmt88ii" too; the longer key must win.
    assert suggest_profile("EPSON TM-T88III Receipt", None, None) == "TM-T88III"


def test_short_profile_keys_never_substring_match() -> None:
    # "T-1" normalizes to "t1" — must not match arbitrary descriptors.
    assert suggest_profile("Printer t1000 deluxe", None, None) is None


def test_alias_in_descriptor() -> None:
    assert suggest_profile("CITIZEN CT-S601II", None, None) == "CT-S651"


def test_vid_pid_fallback() -> None:
    assert suggest_profile("USB Printer", 0x0416, 0x5011) == "POS-5890"


def test_no_match() -> None:
    assert suggest_profile("Mystery Device", 0x1234, 0x5678) is None
    assert suggest_profile(None, None, None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_profile_suggestions.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `capabilities/suggestions.py`:

```python
"""Suggest a printer profile from USB identity.

Order: USB product descriptor name match (descriptors like "TM-T20II"
carry the model name and beat any PID table), then clone aliases, then
a small curated VID:PID map. A suggestion only preselects a dropdown —
it never gates behavior.
"""

from __future__ import annotations

from .aliases import PROFILE_ALIASES, normalize_model
from .loader import _get_capabilities

# Curated VID:PID -> profile map. Verified hardware families only.
# Epson (0x04b8) deliberately absent: name matching handles specific
# models, and a wrong blanket guess is worse than no suggestion.
VID_PID_PROFILES: dict[tuple[int, int], str] = {
    (0x0416, 0x5011): "POS-5890",  # Winbond-VID Zijiang POS-5890 family
}

# "T-1" normalizes to "t1"; require 4+ chars so tiny keys can't
# substring-match unrelated descriptors.
_MIN_KEY_LEN = 4


def suggest_profile(product: str | None, vid: int | None, pid: int | None) -> str | None:
    """Return a bundled profile key for a USB device, or None."""
    if product:
        norm = normalize_model(product)
        if norm:
            profiles = _get_capabilities().get("profiles", {})
            candidates = [
                key
                for key in profiles
                if len(normalize_model(key)) >= _MIN_KEY_LEN and normalize_model(key) in norm
            ]
            if candidates:
                # Longest normalized key wins: "tmt88iii" over "tmt88ii".
                return max(candidates, key=lambda key: len(normalize_model(key)))
            for alias_norm, target in PROFILE_ALIASES.items():
                if alias_norm in norm and target in profiles:
                    return target
    if vid is not None and pid is not None:
        return VID_PID_PROFILES.get((vid, pid))
    return None
```

Export `suggest_profile` from `capabilities/__init__.py` (add to imports and `__all__`).

- [ ] **Step 4: Run tests**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_profile_suggestions.py -v`
Expected: PASS (all 6)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: profile suggestion from USB descriptor and VID:PID

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Preselect suggested profile in the USB config flow

**Files:**

- Modify: `custom_components/escpos_printer/_config_flow/usb_steps.py` (`async_step_usb_select` ~line 155-183; `async_step_usb_all_devices` — same pattern where its schema builds `CONF_PROFILE`)
- Test: extend the existing USB config-flow test file (locate with `grep -rl "usb_select" tests/`)

**Interfaces:**

- Consumes: `suggest_profile` (Task 3), `self._discovered_printers` dicts with `product`/`vendor_id`/`product_id` keys (built in `usb_helpers.py:267-277`).
- Produces: no new symbols — the profile dropdown's `default` becomes the suggestion when one exists.

- [ ] **Step 1: Write the failing test**

In the USB config-flow test file, add (adapt fixture/patch style from neighboring tests in that file — they already patch `_discover_usb_printers`):

```python
async def test_usb_select_preselects_suggested_profile(hass) -> None:
    fake_printers = [
        {
            "vendor_id": 0x04B8,
            "product_id": 0x0E15,
            "manufacturer": "EPSON",
            "product": "TM-T20II",
            "serial_number": None,
            "is_known_printer": True,
            "label": "EPSON TM-T20II (04B8:0E15)",
        }
    ]
    with patch(
        "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
        return_value=fake_printers,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"connection_type": "usb"}
        )
    schema = result["data_schema"].schema
    profile_key = next(k for k in schema if k.schema == CONF_PROFILE)
    assert profile_key.default() == "TM-T20II"
```

(Match the actual step-navigation calls used by existing tests in that file — the first step may differ; copy their path to reach `usb_select`. The patch target module path must be where `_discover_usb_printers` is *used*, i.e. `usb_steps`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest <that file> -v -k preselects`
Expected: FAIL — default is `""` (PROFILE_AUTO)

- [ ] **Step 3: Implement**

In `usb_steps.py` `async_step_usb_select`, after `profile_choices` is fetched and before `data_schema`:

```python
        # Preselect a suggested profile for the default (first) device.
        # ponytail: suggestion follows the first discovered printer only;
        # re-computing per selected device would need a two-step flow.
        default_profile = PROFILE_AUTO
        if self._discovered_printers:
            first = self._discovered_printers[0]
            suggestion = await self.hass.async_add_executor_job(
                suggest_profile,
                first.get("product"),
                first.get("vendor_id"),
                first.get("product_id"),
            )
            if suggestion and suggestion in profile_choices:
                default_profile = suggestion
```

and change the schema line to:

```python
                vol.Optional(CONF_PROFILE, default=default_profile): vol.In(profile_choices),
```

Import `suggest_profile` from `..capabilities`. Apply the identical pattern in `async_step_usb_all_devices` (it also lists devices and offers `CONF_PROFILE` — if its device list variable differs, adapt; if that step has no discovered-device dicts with descriptors, leave it unchanged and note that in the commit message).

- [ ] **Step 4: Run tests**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/ -q -k "usb"`
Expected: PASS (new test + no regressions)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: preselect suggested profile in USB config flow

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `pick_impl` helpers; reliability presets become pacing-only

**Files:**

- Modify: `custom_components/escpos_printer/capabilities/features.py` (add two functions)
- Modify: `custom_components/escpos_printer/capabilities/__init__.py` (exports)
- Modify: `custom_components/escpos_printer/const.py:291-313` (`RELIABILITY_PROFILE_PRESETS`)
- Test: `tests/test_pick_impl.py` (new); adjust any preset-shape assertions in existing tests

**Interfaces:**

- Consumes: `get_profile_features` (existing, same module).
- Produces: `pick_impl(profile_key: str | None) -> str | None` (`"bitImageRaster"` | `"bitImageColumn"` | None); `profile_declares_no_images(profile_key: str | None) -> bool`. Task 6 calls both from `__init__.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pick_impl.py`:

```python
"""Tests for profile-driven image implementation selection."""

from custom_components.escpos_printer.capabilities.features import (
    pick_impl,
    profile_declares_no_images,
)
from custom_components.escpos_printer.const import RELIABILITY_PROFILE_PRESETS


def test_raster_preferred() -> None:
    assert pick_impl("TM-T20II") == "bitImageRaster"


def test_column_only_impact_printer() -> None:
    assert pick_impl("TM-U220") == "bitImageColumn"


def test_no_image_profile() -> None:
    assert pick_impl("AF-240") is None
    assert profile_declares_no_images("AF-240") is True


def test_unknown_and_auto_profiles() -> None:
    assert pick_impl("") is None
    assert pick_impl(None) is None
    assert pick_impl("no-such-profile") is None
    assert profile_declares_no_images("") is False
    assert profile_declares_no_images("no-such-profile") is False


def test_graphics_never_auto_picked() -> None:
    # Every bundled profile with graphics also has raster; the picker
    # must never return "graphics".
    assert pick_impl("TM-T88V") == "bitImageRaster"


def test_presets_are_pacing_only() -> None:
    for name, preset in RELIABILITY_PROFILE_PRESETS.items():
        assert "impl" not in preset, f"preset {name} must not set impl"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_pick_impl.py -v`
Expected: FAIL — `ImportError: cannot import name 'pick_impl'`

- [ ] **Step 3: Implement**

Append to `capabilities/features.py`:

```python
# Preference order for automatic image implementation selection.
# graphics is deliberately absent: every bundled profile with graphics
# also declares bitImageRaster, so raster strictly dominates it for
# compatibility; graphics stays a manual choice.
_IMPL_PREFERENCE = ("bitImageRaster", "bitImageColumn")

_IMAGE_FEATURES = ("bitImageRaster", "bitImageColumn", "graphics")


def pick_impl(profile_key: str | None) -> str | None:
    """Pick the image implementation a profile declares support for.

    Returns None for auto/custom/unknown profiles (caller falls back to
    DEFAULT_IMPL) and for profiles that declare no image support at all
    (caller warns but still prints — feature flags are hints, not gates).
    """
    features = get_profile_features(profile_key)
    for impl in _IMPL_PREFERENCE:
        if features.get(impl):
            return impl
    return None


def profile_declares_no_images(profile_key: str | None) -> bool:
    """True when a known profile explicitly declares no image support."""
    features = get_profile_features(profile_key)
    if not features:
        return False  # auto/custom/unknown: assume capable, stay silent
    return not any(features.get(feature) for feature in _IMAGE_FEATURES)
```

Export both from `capabilities/__init__.py` (imports + `__all__`, sorted).

`const.py`: delete the `"impl": "bitImageRaster",` line from all four presets (`fast_lan`, `balanced`, `conservative`, `bluetooth_safe`) and update the comment above the dict:

```python
# Reliability profile presets used by the options flow.
# A preset picks transport pacing (fragment_height + chunk_delay_ms) only;
# image implementation is a printer property resolved from the printer
# profile / CONF_IMPL. The user can still override per service call.
```

- [ ] **Step 4: Run tests**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_pick_impl.py -v && ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/ -q -k "reliability or preset or diagnostics"`
Expected: new tests PASS. Any existing test asserting presets contain `impl` must be updated to expect pacing-only presets.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: pick_impl from profile features; presets are pacing-only

BREAKING-ish: reliability presets no longer force bitImageRaster.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `CONF_IMPL` option + resolution chain wiring

**Files:**

- Modify: `custom_components/escpos_printer/const.py` (near `IMPL_MODES`, line ~279)
- Modify: `custom_components/escpos_printer/printer/base_adapter.py` (`__init__`, ~line 86-95)
- Modify: `custom_components/escpos_printer/__init__.py` (`async_setup_entry`, after the reliability wiring at line ~261-264)
- Modify: `custom_components/escpos_printer/printer/image_operations.py:106-108`
- Modify: `custom_components/escpos_printer/_config_flow/options_flow.py` (schema + current value)
- Modify: `custom_components/escpos_printer/_config_flow/settings_steps.py` (codepage step schema)
- Modify: `custom_components/escpos_printer/strings.json`, `translations/en.json`
- Test: `tests/test_impl_resolution.py` (new)

**Interfaces:**

- Consumes: `pick_impl`, `profile_declares_no_images` (Task 5).
- Produces: `CONF_IMPL = "impl"`, `IMPL_AUTO = "auto"`, `IMPL_CHOICE_LABELS` in const.py; adapter attributes `default_impl: str | None`, `profile_no_image_support: bool`, `_no_image_warned: bool`. Resolution chain (first hit wins): per-call `impl` → legacy `reliability_profile_defaults["impl"]` → `adapter.default_impl` → `DEFAULT_IMPL`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_impl_resolution.py`:

```python
"""Tests for the image implementation resolution chain."""

from custom_components.escpos_printer.const import (
    CONF_IMPL,
    IMPL_AUTO,
    IMPL_CHOICE_LABELS,
    IMPL_MODES,
)
from custom_components.escpos_printer.printer import create_printer_adapter
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig


def test_impl_labels_cover_all_modes() -> None:
    assert set(IMPL_CHOICE_LABELS) == {IMPL_AUTO, *IMPL_MODES}


def test_adapter_default_impl_attrs() -> None:
    adapter = create_printer_adapter(NetworkPrinterConfig(host="127.0.0.1"))
    assert adapter.default_impl is None
    assert adapter.profile_no_image_support is False
```

Plus a chain test in the same file (async; follow the fixture style of whichever existing test exercises `prepare_image` — `grep -rl "prepare_image" tests/`):

```python
async def test_prepare_image_uses_adapter_default_impl(hass, ...) -> None:
    # Arrange an adapter with default_impl="bitImageColumn", no per-call
    # impl, empty reliability_profile_defaults; run the existing
    # prepare_image path on a tiny in-memory PNG and assert
    # prepared.impl == "bitImageColumn". Then pass impl="graphics"
    # per-call and assert it wins.
```

(Write this as a real test by copying the minimal setup from the existing `prepare_image`/print-image test — the repo already has image-service tests that build a 1x1 PNG. Assert on the `PreparedImage.impl` field.)

- [ ] **Step 2: Run test to verify it fails**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_impl_resolution.py -v`
Expected: FAIL — `ImportError: cannot import name 'CONF_IMPL'`

- [ ] **Step 3: Implement**

`const.py`, next to `IMPL_MODES` (line ~279):

```python
CONF_IMPL = "impl"  # per-entry default image implementation
IMPL_AUTO = "auto"  # follow the printer profile (pick_impl)
IMPL_CHOICE_LABELS: dict[str, str] = {
    IMPL_AUTO: "Auto (recommended) — follow the printer profile",
    "bitImageRaster": "Raster — works on most printers",
    "bitImageColumn": "Column — older/impact printers; try this if images print as garbled text",
    "graphics": "Graphics — modern Epson printers",
}
```

`base_adapter.py` `__init__`, alongside the existing attribute setup:

```python
        # Per-entry default image implementation, resolved at setup from
        # CONF_IMPL / pick_impl(profile). None -> DEFAULT_IMPL at use time.
        self.default_impl: str | None = None
        # True when the profile explicitly declares no image support;
        # prepare_image warns once but still prints (hints, not gates).
        self.profile_no_image_support: bool = False
        self._no_image_warned: bool = False
```

`__init__.py` `async_setup_entry`, right after the `reliability_profile_defaults` assignment (imports: `CONF_IMPL`, `IMPL_AUTO`, `IMPL_MODES` from `.const`; `pick_impl`, `profile_declares_no_images` from `.capabilities`):

```python
    entry_impl = entry.options.get(CONF_IMPL, entry.data.get(CONF_IMPL, IMPL_AUTO))
    if entry_impl in IMPL_MODES:
        adapter.default_impl = entry_impl
    else:
        adapter.default_impl = await hass.async_add_executor_job(pick_impl, shared["profile"])
    adapter.profile_no_image_support = await hass.async_add_executor_job(
        profile_declares_no_images, shared["profile"]
    )
```

(`shared` is the `_shared_print_config(entry)` dict already used to build `config` — if the local name differs, use that name.)

`image_operations.py`, replace lines 107-108:

```python
    if impl is None:
        # Legacy: presets no longer carry impl, but honor it if present.
        impl = profile_defaults.get("impl")
    if impl is None:
        impl = getattr(host, "default_impl", None)
    if impl is None:
        impl = DEFAULT_IMPL
    if getattr(host, "profile_no_image_support", False) and not getattr(
        host, "_no_image_warned", True
    ):
        _LOGGER.warning(
            "Printer profile reports no image support; attempting impl=%s anyway",
            impl,
        )
        host._no_image_warned = True
```

`options_flow.py`: compute the current value next to `current_reliability`:

```python
        current_impl = self.config_entry.options.get(CONF_IMPL, IMPL_AUTO)
```

pass it into `_build_options_schema` (add parameter `current_impl: str`) and add the field after `CONF_RELIABILITY_PROFILE`:

```python
            vol.Optional(CONF_IMPL, default=current_impl): vol.In(IMPL_CHOICE_LABELS),
```

`settings_steps.py` codepage step schema, after the `CONF_WIDTH_PIXELS` field:

```python
                vol.Optional(CONF_IMPL, default=IMPL_AUTO): vol.In(IMPL_CHOICE_LABELS),
```

and persist it in the entry-creation branch: `data[CONF_IMPL] = user_input.get(CONF_IMPL, IMPL_AUTO)`.

`strings.json` (+ mirror in `translations/en.json`):

- `config.step.codepage.data`: `"impl": "Image printing implementation"`
- `options.step.init.data`: `"impl": "Image printing implementation"`

- [ ] **Step 4: Run tests**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_impl_resolution.py tests/ -q -k "impl or image or options"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: per-entry impl option with profile-driven auto default

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: services.yaml impl descriptions + translation sync

**Files:**

- Modify: `custom_components/escpos_printer/services.yaml` (the `impl` field in exactly five services: `print_image`, `print_image_url`, `print_image_path`, `print_camera_snapshot`, `print_image_entity` — NOT `preview_image`, which deliberately omits it)
- Modify (generated): `custom_components/escpos_printer/strings.json`, `translations/en.json` via script

**Interfaces:**

- Consumes: nothing new.
- Produces: no code symbols — user-facing copy only.

- [ ] **Step 1: Update the five impl descriptions**

In each of the five image services, set the `impl` field's `description` to (identical in all five — the parity test enforces byte-equality; keep the existing `name`/`selector` unchanged):

```yaml
        description: >
          Image implementation. Leave unset to follow the printer profile.
          Raster (bitImageRaster) works on most printers; Column
          (bitImageColumn) suits older/impact printers — try it if images
          print as garbled text; Graphics is for modern Epson printers.
```

(Use a `>` folded scalar exactly as shown — no `#` characters, so no quoting concerns.)

- [ ] **Step 2: Regenerate translations**

Run: `uv run python scripts/sync_service_translations.py`
Expected: strings.json / translations/en.json `services` keys updated; no errors.

- [ ] **Step 3: Run the guard tests**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_services_yaml_schema.py -v`
Expected: PASS — including `test_image_services_share_common_field_metadata` and `test_image_services_no_truncated_descriptions`.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "docs: impl service descriptions mention profile-driven default

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Changelog, version bump, full validation

**Files:**

- Modify: `CHANGELOG.md` (`## [Unreleased]`)
- Modify: `custom_components/escpos_printer/manifest.json` (`"version": "1.1.0"`)
- Modify: `pyproject.toml` (`version = "1.1.0"`)

**Interfaces:** none.

- [ ] **Step 1: Changelog entries**

Under `## [Unreleased]` (create `### Added` / `### Changed` subsections matching the file's existing style):

```markdown
### Added
- Per-entry "Paper width in pixels" override — fixes image sizing for printers whose profile lacks a width (previously a Repairs issue with no user-side fix).
- USB config flow now preselects a suggested profile from the device's USB descriptor or a curated VID:PID list.
- Clone/equivalent model aliases (e.g. Citizen CT-S601II → CT-S651, ZJ-5890 → POS-5890) accepted in the custom profile field.
- Per-entry "Image printing implementation" option (Auto/Raster/Column/Graphics) with plain-language guidance.

### Changed
- **Behavioral:** image implementation now defaults from the printer profile (raster, or column for column-only printers) instead of always raster; reliability presets no longer force `bitImageRaster`. Explicit `impl` in service calls is unaffected.
- Profile dropdown's "Auto-detect (Default)" renamed to "Generic (no profile)" — it never detected anything.
- Printing an image on a profile that declares no image support now logs a warning (the print is still attempted).
```

- [ ] **Step 2: Bump versions**

`manifest.json`: `"version": "1.1.0"`. `pyproject.toml`: `version = "1.1.0"`.

- [ ] **Step 3: Full validation**

Run each; all must pass:

```bash
ESC_POS_DISABLE_PLATFORMS=1 uv run pytest -q
uv run ruff check .
uv run mypy custom_components/
python scripts/check_requirements_sync.py
python scripts/sync_service_translations.py --check
pre-commit run --all-files
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: changelog + version 1.1.0

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec coverage: Piece 1 → Task 1; Piece 2 → Tasks 3-4; Piece 3 → Task 2; Piece 4 → Tasks 5-6; Piece 5 → Tasks 6-7; version/changelog → Task 8. Repairs-issue text update → Task 1 Step 4. Warn-but-try → Task 6 (`profile_no_image_support` warning path).
- Type consistency: `pick_impl`/`profile_declares_no_images` signatures identical in Tasks 5 (definition) and 6 (consumption); `CONF_WIDTH_PIXELS` defined in Task 1, reused nowhere else by name collision; `IMPL_CHOICE_LABELS` defined Task 6, consumed Task 6 only.
- Known judgment calls for the executor: exact TM-T20II pixel width (verify 512 vs actual), USB flow test navigation path, and whether `usb_all_devices` carries descriptor dicts — each has an inline fallback instruction.
