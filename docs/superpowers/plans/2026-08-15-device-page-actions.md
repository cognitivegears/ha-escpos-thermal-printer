# Device Page Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the printer device page a Controls card (Feed / Cut / Beep / Sample test print buttons) and make the calibration wizard discoverable via a fixable Repairs issue.

**Architecture:** A new `button` platform presses through the existing adapter methods (already lock-serialized). A sample-print composer uses the existing `batch_connection()` single-connection API (extended with styled text + QR). A `repairs.py` platform reuses `CalibrationFlowMixin` — already flow-agnostic — so the real wizard runs from Settings → Repairs; `async_setup_entry` raises/clears one issue per never-calibrated entry.

**Tech Stack:** Home Assistant custom integration (Python 3.14, HA floor 2026.5.0), pytest-homeassistant-custom-component, voluptuous, python-escpos.

**Spec:** `docs/superpowers/specs/2026-08-15-device-page-actions-design.md`

## Global Constraints

- Run everything with `uv run …` from the repo root; if tools look stale run `uv sync --all-extras` first.
- Copy rules (approved wording, use verbatim): issue title **"Printer not yet calibrated"**; issue description **"The optional calibration tool prints test pages to tune print width and character set for this printer and paper. Run it now, or ignore this — printing works without it."**
- Feed button feeds a fixed **3** lines. Cut button uses the entry's `CONF_DEFAULT_CUT`, falling back to `"full"` when unset or `"none"`.
- `strings.json` and `translations/en.json` are maintained as identical copies for non-`services` keys — every manual edit to one must be mirrored in the other, then verified with `uv run python scripts/sync_service_translations.py --check`.
- Every user-visible change gets a CHANGELOG entry under `## [Unreleased]`.
- Never run `git stash` / `git reset` / anything that discards working-tree state.
- Unit tests: conftest monkeypatches `PLATFORMS` to `["notify"]`; tests needing the button platform must re-patch (shown in Task 3).
- Commit after each task with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` in the message.

---

### Task 0: Branch setup

**Files:** none (git only)

- [ ] **Step 1: Create the feature branch**

Check whether PR #151 is merged: `gh pr view 151 --json state -q .state`.
- If `MERGED`: `git checkout main && git pull && git checkout -b feat/device-page-actions`
- Otherwise: `git checkout feat/service-action-targets && git pull && git checkout -b feat/device-page-actions`

---

### Task 1: `_BatchPage` styled text passthrough + QR

**Files:**
- Modify: `custom_components/escpos_printer/printer/base_adapter.py` (class `_BatchPage`, ~line 752)
- Modify: `custom_components/escpos_printer/printer/print_operations.py` (extract `_qr_under_lock`)
- Test: `tests/test_batch_page_extensions.py` (create)

**Interfaces:**
- Consumes: `_print_text_under_lock(adapter, hass, printer, *, text, align, bold, underline, width, height, encoding, wrap)` and `map_align` (already imported/importable in these modules).
- Produces: `_BatchPage.print_text(*, text, align=None, bold=None, underline=None, width=None, height=None, encoding=None, wrap=True, feed=0)` and `_BatchPage.print_qr(*, data, size=None, ec=None, align="center")` — Task 2 calls both.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for _BatchPage styled-text passthrough and QR printing."""

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass, host="1.2.3.4"):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: 9100},
        title=f"ESC/POS {host}",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network", return_value=MagicMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_batch_page_styled_text_and_qr(hass):  # type: ignore[no-untyped-def]
    """Styled kwargs reach printer.set(); qr() is issued on the held connection."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        async with adapter.batch_connection(hass) as page:
            await page.print_text(text="Loud\n", bold=True, align="center")
            await page.print_qr(data="https://example.com")

    assert fake.qr.called
    qr_args, qr_kwargs = fake.qr.call_args
    assert qr_args[0] == "https://example.com"
    # bold=True must have been forwarded to printer.set() by the text half
    set_kwargs = [kw for _, kw in [c for c in fake.set.call_args_list]]
    assert any(kw.get("bold") for kw in set_kwargs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_batch_page_extensions.py -v`
Expected: FAIL — `TypeError: print_text() got an unexpected keyword argument 'bold'` (or `AttributeError: print_qr`).

- [ ] **Step 3: Extract `_qr_under_lock` in print_operations.py**

Move the body of `print_qr`'s validation + `_do_print` (currently inline at `print_operations.py:78-125`) into a module-level helper next to `_print_text_under_lock`, and call it from `print_qr`:

```python
async def _qr_under_lock(
    hass: HomeAssistant,
    printer: Any,
    *,
    data: str,
    size: int | None = None,
    ec: str | None = None,
    align: str | None = None,
) -> None:
    """Validate + print a QR on an already-acquired connection (lock held by caller)."""
    data = validate_qr_data(data)
    align_m = map_align(align)
    qsize = int(size) if size is not None else 3
    qsize = max(1, min(16, qsize))
    qec = (ec or "M").upper()
    if qec not in ("L", "M", "Q", "H"):
        qec = "M"

    def _map_qr_ec(level: str) -> Any:
        try:
            from escpos import escpos as _esc  # noqa: PLC0415

            return {
                "L": getattr(_esc, "QR_ECLEVEL_L", "L"),
                "M": getattr(_esc, "QR_ECLEVEL_M", "M"),
                "Q": getattr(_esc, "QR_ECLEVEL_Q", "Q"),
                "H": getattr(_esc, "QR_ECLEVEL_H", "H"),
            }[level]
        except Exception:
            return level

    def _do_print(printer_obj: Any) -> None:
        if hasattr(printer_obj, "set"):
            printer_obj.set(align=align_m, normal_textsize=True)
        printer_obj.qr(data, size=qsize, ec=_map_qr_ec(qec))

    await hass.async_add_executor_job(_do_print, printer)
```

`print_qr` becomes: acquire lock/printer as today, then `await _qr_under_lock(hass, printer, data=data, size=size, ec=ec, align=align)`, then `_apply_cut_and_feed` — behavior identical.

- [ ] **Step 4: Extend `_BatchPage` in base_adapter.py**

Replace `_BatchPage.print_text`'s hardcoded `None` style args with passthrough parameters, and add `print_qr` (import `_qr_under_lock` alongside the existing `_print_text_under_lock` import):

```python
    async def print_text(
        self,
        *,
        text: str,
        align: str | None = None,
        bold: bool | None = None,
        underline: str | None = None,
        width: str | int | None = None,
        height: str | int | None = None,
        encoding: str | None = None,
        wrap: bool = True,
        feed: int | None = 0,
    ) -> None:
        """Print text on the held connection (mirrors ``adapter.print_text``)."""
        await _print_text_under_lock(
            self._adapter,
            self._hass,
            self._printer,
            text=text,
            align=align,
            bold=bold,
            underline=underline,
            width=width,
            height=height,
            encoding=encoding,
            wrap=wrap,
        )
        await self._adapter._apply_cut_and_feed(self._hass, self._printer, "none", feed)

    async def print_qr(
        self,
        *,
        data: str,
        size: int | None = None,
        ec: str | None = None,
        align: str | None = "center",
    ) -> None:
        """Print a QR code on the held connection (mirrors ``adapter.print_qr``)."""
        await _qr_under_lock(
            self._hass, self._printer, data=data, size=size, ec=ec, align=align
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_batch_page_extensions.py -v` → PASS.
Run: `uv run pytest -q` → no regressions (the existing QR service tests cover the extraction).

- [ ] **Step 6: Commit**

```bash
git add custom_components/escpos_printer/printer/base_adapter.py \
        custom_components/escpos_printer/printer/print_operations.py \
        tests/test_batch_page_extensions.py
git commit -m "Add styled text and QR to _BatchPage held-connection API"
```

---

### Task 2: Sample print composer

**Files:**
- Create: `custom_components/escpos_printer/sample_print.py`
- Test: `tests/test_sample_print.py` (create)

**Interfaces:**
- Consumes: `_BatchPage.print_text` / `print_qr` (Task 1), `adapter.batch_connection(hass)`, `adapter.cut(hass, *, mode)`, `_shared_print_config(entry)` from the package `__init__`, `render_box` (`text_effects/box.py:77`), `render_table` (`text_effects/table.py:157`).
- Produces: `async_print_sample(hass: HomeAssistant, entry: EscposConfigEntry) -> None` — Task 3's button calls it.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the sample test print composer."""

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.sample_print import async_print_sample


async def _setup_entry(hass, host="1.2.3.4"):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: 9100},
        title=f"ESC/POS {host}",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network", return_value=MagicMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_sample_print_composes_one_receipt(hass):  # type: ignore[no-untyped-def]
    """Logo image, text sections, and QR go out; a cut follows."""
    entry = await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await async_print_sample(hass, entry)

    assert fake.image.called, "logo did not print"
    assert fake.qr.called, "QR did not print"
    assert fake.cut.called, "receipt was not cut"
    # image (logo) must come before qr on the wire
    names = [c[0] for c in fake.method_calls]
    assert names.index("image") < names.index("qr")


async def test_sample_print_cut_mode_none_falls_back_to_full(hass):  # type: ignore[no-untyped-def]
    """An entry whose default cut is 'none' still cuts (full)."""
    from custom_components.escpos_printer.const import CONF_DEFAULT_CUT

    entry = await _setup_entry(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_DEFAULT_CUT: "none"}
    )
    await hass.async_block_till_done()
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await async_print_sample(hass, entry)
    assert fake.cut.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sample_print.py -v`
Expected: FAIL — `ModuleNotFoundError: custom_components.escpos_printer.sample_print`.

- [ ] **Step 3: Implement `sample_print.py`**

```python
"""Compose the 'Sample test print' receipt (device page button).

One uninterrupted receipt on a single held connection: logo, boxed
header, styled text, table, separator, QR. ASCII border style on
purpose — it renders identically on every codepage, so the sample
never needs transcoding.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

from .text_effects.box import render_box
from .text_effects.table import render_table

if TYPE_CHECKING:
    from . import EscposConfigEntry

_LOGO_PATH = Path(__file__).parent / "brand" / "logo.png"
_REPO_URL = "https://github.com/cognitivegears/ha-escpos-thermal-printer"


def _logo_data_uri() -> str:
    """base64 data URI for the bundled logo (blocking; run via executor)."""
    return "data:image/png;base64," + base64.b64encode(_LOGO_PATH.read_bytes()).decode()


async def async_print_sample(hass: HomeAssistant, entry: EscposConfigEntry) -> None:
    """Print the sample receipt on the entry's printer."""
    from . import _shared_print_config  # noqa: PLC0415 (avoid import cycle at module load)

    adapter = entry.runtime_data.adapter
    line_width = _shared_print_config(entry)["line_width"]
    logo = await hass.async_add_executor_job(_logo_data_uri)

    header = render_box(
        f"ESC/POS Sample Print\n{entry.title}",
        inner_width=max(line_width - 2, 10),
        style="ascii",
        align="center",
    )
    table = render_table(
        [["Item", "Qty"], ["Receipt demo", "1"], ["Styled text", "3"]],
        total_width=line_width,
        style="ascii",
        header=True,
    )

    async with adapter.batch_connection(hass) as page:
        await page.print_image(image=logo, auto_resize=True)
        await page.print_text(text=header + "\n")
        await page.print_text(text="Bold text\n", bold=True)
        await page.print_text(text="Underlined text\n", underline="single")
        await page.print_text(text="Double size\n", width=2, height=2)
        await page.print_text(text=table + "\n")
        await page.print_text(text="=" * line_width + "\n")
        await page.print_qr(data=_REPO_URL)
        await page.print_text(text=f"Docs & source:\n{_REPO_URL}\n")
        await page.feed(2)

    # Batch pages never cut (documented _BatchPage contract) — follow-up
    # cut like the calibration wizard does. "none" would make the button
    # print an uncut dangling receipt, so fall back to full.
    cut_mode = entry.runtime_data.defaults.get("cut") or "full"
    if cut_mode == "none":
        cut_mode = "full"
    await adapter.cut(hass, mode=cut_mode)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sample_print.py -v` → PASS. If `page.print_image` rejects the data URI or width, check `prepare_image_for_print` error output — calibration already passes generated data URIs through this exact path, so mirror what `calibration.py` does if anything differs.

- [ ] **Step 5: Commit**

```bash
git add custom_components/escpos_printer/sample_print.py tests/test_sample_print.py
git commit -m "Add sample test print composer"
```

---

### Task 3: Button platform

**Files:**
- Create: `custom_components/escpos_printer/button.py`
- Modify: `custom_components/escpos_printer/__init__.py:83` (`PLATFORMS` list)
- Modify: `custom_components/escpos_printer/strings.json` + `custom_components/escpos_printer/translations/en.json` (`entity` section — mirror the edit in both files)
- Modify: `custom_components/escpos_printer/icons.json` (`entity` section)
- Test: `tests/test_buttons.py` (create)

**Interfaces:**
- Consumes: `async_print_sample(hass, entry)` (Task 2); `adapter.feed(hass, *, lines)`, `adapter.cut(hass, *, mode)`, `adapter.beep(hass)` (`printer/control_operations.py:54,92,128`); `build_device_info(entry)` (`device.py:61`).
- Produces: four button entities with translation keys `feed` / `cut` / `beep` / `sample_print`, unique_ids `{entry_id}_{key}`.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the printer device-page buttons."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_DEFAULT_CUT, DOMAIN


@pytest.fixture(autouse=True)
def _enable_button_platform(monkeypatch):  # type: ignore[no-untyped-def]
    """conftest limits unit-test platforms to ['notify']; buttons need theirs."""
    import custom_components.escpos_printer.__init__ as cc_init

    monkeypatch.setattr(cc_init, "PLATFORMS", ["notify", "button"], raising=False)


async def _setup_entry(hass, host="1.2.3.4", options=None):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: 9100},
        options=options or {},
        title=f"ESC/POS {host}",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network", return_value=MagicMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _button_entity_id(hass, entry, key):  # type: ignore[no-untyped-def]
    registry = er.async_get(hass)
    entity = registry.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity is not None, f"button {key} not registered"
    return entity


async def _press(hass, entity_id):  # type: ignore[no-untyped-def]
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


async def test_feed_button_feeds_three_lines(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    entry.runtime_data.adapter.feed = AsyncMock()
    await _press(hass, _button_entity_id(hass, entry, "feed"))
    entry.runtime_data.adapter.feed.assert_awaited_once_with(hass, lines=3)


async def test_cut_button_uses_entry_default(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass, options={CONF_DEFAULT_CUT: "partial"})
    entry.runtime_data.adapter.cut = AsyncMock()
    await _press(hass, _button_entity_id(hass, entry, "cut"))
    entry.runtime_data.adapter.cut.assert_awaited_once_with(hass, mode="partial")


async def test_cut_button_none_falls_back_to_full(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass, options={CONF_DEFAULT_CUT: "none"})
    entry.runtime_data.adapter.cut = AsyncMock()
    await _press(hass, _button_entity_id(hass, entry, "cut"))
    entry.runtime_data.adapter.cut.assert_awaited_once_with(hass, mode="full")


async def test_beep_button(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    entry.runtime_data.adapter.beep = AsyncMock()
    await _press(hass, _button_entity_id(hass, entry, "beep"))
    entry.runtime_data.adapter.beep.assert_awaited_once_with(hass)


async def test_sample_print_button_calls_composer(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    with patch(
        "custom_components.escpos_printer.button.async_print_sample",
        new=AsyncMock(),
    ) as sample:
        await _press(hass, _button_entity_id(hass, entry, "sample_print"))
    sample.assert_awaited_once_with(hass, entry)


async def test_buttons_attached_to_printer_device(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    registry = er.async_get(hass)
    entity_id = _button_entity_id(hass, entry, "feed")
    reg_entry = registry.async_get(entity_id)
    assert reg_entry is not None and reg_entry.device_id is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_buttons.py -v`
Expected: FAIL — button entities not registered (`assert entity is not None` trips).

- [ ] **Step 3: Implement `button.py` and register the platform**

```python
"""Button platform: Feed, Cut, Beep, Sample test print on the device page."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .device import build_device_info
from .sample_print import async_print_sample

if TYPE_CHECKING:
    from . import EscposConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# ponytail: fixed tear-off advance; make configurable only if someone asks
FEED_LINES = 3


async def async_setup_entry(  # type: ignore[no-untyped-def]
    hass: HomeAssistant, entry: EscposConfigEntry, async_add_entities
) -> None:
    async_add_entities(
        [
            EscposFeedButton(hass, entry),
            EscposCutButton(hass, entry),
            EscposBeepButton(hass, entry),
            EscposSamplePrintButton(hass, entry),
        ]
    )


class _EscposButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: EscposConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_translation_key}"

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._entry)

    async def async_press(self) -> None:
        try:
            await self._press()
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(
                f"Printer operation failed: {err.__class__.__name__}"
            ) from err

    async def _press(self) -> None:
        raise NotImplementedError


class EscposFeedButton(_EscposButton):
    _attr_translation_key = "feed"

    async def _press(self) -> None:
        await self._entry.runtime_data.adapter.feed(self._hass, lines=FEED_LINES)


class EscposCutButton(_EscposButton):
    _attr_translation_key = "cut"

    async def _press(self) -> None:
        # A Cut button that does nothing reads as broken — "none" → full.
        mode = self._entry.runtime_data.defaults.get("cut") or "full"
        if mode == "none":
            mode = "full"
        await self._entry.runtime_data.adapter.cut(self._hass, mode=mode)


class EscposBeepButton(_EscposButton):
    _attr_translation_key = "beep"

    async def _press(self) -> None:
        await self._entry.runtime_data.adapter.beep(self._hass)


class EscposSamplePrintButton(_EscposButton):
    _attr_translation_key = "sample_print"

    async def _press(self) -> None:
        await async_print_sample(self._hass, self._entry)
```

In `__init__.py:83` change `PLATFORMS: list[str] = ["notify", "binary_sensor", "sensor"]` to `PLATFORMS: list[str] = ["notify", "binary_sensor", "sensor", "button"]`.

- [ ] **Step 4: Add entity names and icons**

In **both** `strings.json` and `translations/en.json`, add to the existing `"entity"` object (alongside `"binary_sensor"` / `"sensor"`):

```json
"button": {
  "feed": {"name": "Feed paper"},
  "cut": {"name": "Cut paper"},
  "beep": {"name": "Beep"},
  "sample_print": {"name": "Sample test print"}
}
```

In `icons.json`, add to `"entity"`:

```json
"button": {
  "feed": {"default": "mdi:arrow-collapse-down"},
  "cut": {"default": "mdi:content-cut"},
  "beep": {"default": "mdi:volume-high"},
  "sample_print": {"default": "mdi:receipt-text-check-outline"}
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_buttons.py -v` → PASS.
Run: `uv run python scripts/sync_service_translations.py --check` → in sync (proves the mirrored strings/en.json edits stayed identical).

- [ ] **Step 6: Commit**

```bash
git add custom_components/escpos_printer/button.py custom_components/escpos_printer/__init__.py \
        custom_components/escpos_printer/strings.json custom_components/escpos_printer/translations/en.json \
        custom_components/escpos_printer/icons.json tests/test_buttons.py
git commit -m "Add Feed/Cut/Beep/Sample buttons to the device page"
```

---

### Task 4: Repairs-based calibration entry

**Files:**
- Create: `custom_components/escpos_printer/repairs.py`
- Modify: `custom_components/escpos_printer/__init__.py` (`async_setup_entry`, after `entry.runtime_data` is assigned and platforms forwarded; plus the existing entry-removal cleanup block near line 377-392 that deletes `profile_width_fallback` issues — extend it the same way)
- Modify: `custom_components/escpos_printer/strings.json` + `translations/en.json` (`issues` section — mirror both)
- Test: `tests/test_repairs.py` (create)

**Interfaces:**
- Consumes: `CalibrationFlowMixin` (`_config_flow/calibration_steps.py:113` — needs `hass`, `config_entry`, `_calib`, `_calib_extra`; entry step `async_step_calibrate` aborts with reason `printer_not_ready` unless the entry is LOADED, else shows step `calibrate_confirm`). `_CALIB_TO_CONF` maps to `CONF_IMPL`, `CONF_WIDTH_PIXELS`, `CONF_LINE_WIDTH`, `CONF_CODEPAGE` (import these four from `.const`).
- Produces: fixable issue id `printer_not_calibrated_{entry_id}` with `data={"entry_id": ...}`; `async_create_fix_flow(hass, issue_id, data)` returning `NotCalibratedRepairFlow`.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the printer-not-calibrated repairs issue and fix flow."""

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_LINE_WIDTH, DOMAIN


async def _setup_entry(hass, host="1.2.3.4", options=None):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: 9100},
        options=options or {},
        title=f"ESC/POS {host}",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network", return_value=MagicMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _issue(hass, entry):  # type: ignore[no-untyped-def]
    registry = ir.async_get(hass)
    return registry.async_get_issue(DOMAIN, f"printer_not_calibrated_{entry.entry_id}")


async def test_uncalibrated_entry_raises_issue(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.is_fixable
    assert issue.translation_key == "printer_not_calibrated"


async def test_calibrated_entry_has_no_issue(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass, options={CONF_LINE_WIDTH: 42})
    assert _issue(hass, entry) is None


async def test_issue_cleared_after_calibration_reload(hass):  # type: ignore[no-untyped-def]
    """Saving a calibration option and reloading (what the wizard does) clears the issue."""
    entry = await _setup_entry(hass)
    assert _issue(hass, entry) is not None
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_LINE_WIDTH: 42}
    )
    with patch("escpos.printer.Network", return_value=MagicMock()):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert _issue(hass, entry) is None


async def test_fix_flow_opens_wizard_confirm_step(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    from custom_components.escpos_printer.repairs import async_create_fix_flow

    flow = await async_create_fix_flow(
        hass,
        f"printer_not_calibrated_{entry.entry_id}",
        {"entry_id": entry.entry_id},
    )
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_confirm"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repairs.py -v`
Expected: FAIL — no issue created / `ModuleNotFoundError: ...repairs`.

- [ ] **Step 3: Implement `repairs.py`**

```python
"""Repairs platform: fix flow for the printer-not-calibrated suggestion.

The fix flow IS the calibration wizard — ``CalibrationFlowMixin`` was
written flow-agnostic (needs only ``hass`` + ``config_entry``), so it
runs identically here and in the options flow.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from ._config_flow.calibration_steps import CalibrationFlowMixin


class NotCalibratedRepairFlow(CalibrationFlowMixin, RepairsFlow):
    """Run the calibration wizard from Settings → Repairs."""

    def __init__(self, entry: Any) -> None:
        self.config_entry = entry
        self._calib: dict[str, Any] = {}
        self._calib_extra: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_calibrate()  # type: ignore[return-value]


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    entry = hass.config_entries.async_get_entry((data or {})["entry_id"])
    if entry is None:
        raise ValueError(f"Unknown config entry for repairs issue {issue_id}")
    return NotCalibratedRepairFlow(entry)
```

If mypy complains about the `FlowResult`/`ConfigFlowResult` return-type mismatch between the mixin and `RepairsFlow`, resolve with a targeted `# type: ignore[...]` on the class line — do not restructure the mixin.

- [ ] **Step 4: Raise/clear the issue in `async_setup_entry`**

In `__init__.py`, after platform forwarding succeeds, add (importing `CONF_IMPL`, `CONF_WIDTH_PIXELS`, `CONF_CODEPAGE` alongside the already-imported `CONF_LINE_WIDTH` from `.const`):

```python
    # Calibration nudge: one fixable Repairs issue per never-calibrated
    # entry. "Calibrated" = any wizard-saved key present in options; the
    # settings form writes the same keys, which is fine — a user who
    # found the options flow doesn't need the pointer.
    from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

    calibrated = any(
        key in entry.options
        for key in (CONF_IMPL, CONF_WIDTH_PIXELS, CONF_LINE_WIDTH, CONF_CODEPAGE)
    )
    issue_id = f"printer_not_calibrated_{entry.entry_id}"
    if calibrated:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    else:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="printer_not_calibrated",
            translation_placeholders={"name": entry.title},
            data={"entry_id": entry.entry_id},
        )
```

Extend the existing entry-removal cleanup (the block near `__init__.py:377-392` that deletes `profile_width_fallback` issues) to also call `ir.async_delete_issue(hass, DOMAIN, f"printer_not_calibrated_{entry.entry_id}")`, matching its style.

- [ ] **Step 5: Add issue strings (both strings.json and translations/en.json)**

Add to the existing `"issues"` object, alongside `"profile_width_fallback"`:

```json
"printer_not_calibrated": {
  "title": "Printer not yet calibrated",
  "description": "The optional calibration tool prints test pages to tune print width and character set for this printer and paper. Run it now, or ignore this — printing works without it.",
  "fix_flow": {
    "step": {},
    "abort": {}
  }
}
```

Then populate `fix_flow.step` / `fix_flow.abort` by copying the wizard's existing options-flow translations (repairs flows look up `issues.<translation_key>.fix_flow.*`, not `options.*`). Run this once and inspect the diff:

```python
# scratch script — run with: uv run python <path>
import json

for path in (
    "custom_components/escpos_printer/strings.json",
    "custom_components/escpos_printer/translations/en.json",
):
    with open(path) as f:
        data = json.load(f)
    steps = {
        k: v
        for k, v in data["options"]["step"].items()
        if k.startswith("calibrate")
    }
    aborts = {
        k: v
        for k, v in data["options"].get("abort", {}).items()
        if "calibrat" in k or k == "printer_not_ready"
    }
    fix = data["issues"]["printer_not_calibrated"]["fix_flow"]
    fix["step"] = steps
    fix["abort"] = aborts
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
```

Match the files' existing indent style (check `git diff` — if the repo uses a different JSON formatting, adjust the dump call to match; the sync-check in Step 6 plus `git diff` review is the guard).

- [ ] **Step 6: Run tests + validation**

Run: `uv run pytest tests/test_repairs.py -v` → PASS.
Run: `uv run python scripts/sync_service_translations.py --check` → in sync.
Run hassfest (validates the issues/strings schema):
`docker run --rm -v "$(pwd)":/github/workspace ghcr.io/home-assistant/hassfest:latest` → `Invalid integrations: 0`.

- [ ] **Step 7: Commit**

```bash
git add custom_components/escpos_printer/repairs.py custom_components/escpos_printer/__init__.py \
        custom_components/escpos_printer/strings.json custom_components/escpos_printer/translations/en.json \
        tests/test_repairs.py
git commit -m "Suggest the calibration wizard via a fixable Repairs issue"
```

---

### Task 5: Docs, changelog, roadmap, full gates

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`)
- Modify: `README.md`
- Modify: the calibration doc (find it: `grep -l -i calibration docs/*.md`)
- Modify: `ROADMAP.md` (item 1)

**Interfaces:** none (prose only).

- [ ] **Step 1: CHANGELOG**

Under `## [Unreleased]` add:

```markdown
### Added

- Device page buttons: Feed paper, Cut paper, Beep, and Sample test print
  (a one-tap demo receipt with the integration logo, styled text, a table,
  and a QR code).
- Uncalibrated printers now get a dismissible suggestion in Settings →
  Repairs that launches the calibration wizard directly — no more hunting
  for it under the integration's Configure menu.
```

- [ ] **Step 2: README + calibration doc + ROADMAP**

- README: in the features/entities area, one sentence: device page offers Feed / Cut / Beep / Sample test print buttons, and new printers get a Repairs suggestion linking to the calibration wizard.
- Calibration doc (`grep -l -i calibration docs/*.md`): add a "Starting the wizard" note listing both entry points — Settings → Devices & services → ESC/POS entry → Configure → Calibrate, and the Settings → Repairs suggestion shown while a printer is uncalibrated.
- ROADMAP item 1 ("Button entities"): rewrite to note Feed/Cut/Beep/Sample buttons shipped (this change); the calibration-sheet button was deliberately not added (Repairs entry covers calibration; `calibration_print` service remains).

- [ ] **Step 3: Full gates**

```
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy custom_components/
uv run python scripts/sync_service_translations.py --check
docker run --rm -v "$(pwd)":/github/workspace ghcr.io/home-assistant/hassfest:latest
```

All must pass.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md ROADMAP.md docs/
git commit -m "Document device page buttons and calibration repairs entry"
```

---

## Self-Review Notes

- Spec coverage: buttons (Task 3), sample print incl. `_BatchPage` prerequisites (Tasks 1-2), repairs entry + trigger + copy (Task 4), docs/changelog/roadmap (Task 5). Out-of-scope items from the spec have no tasks, correctly.
- The repairs fix-flow translation duplication (Task 4 Step 5) is required because repairs flows resolve translations under `issues.<key>.fix_flow.*`, not `options.*` — hassfest in Task 4 Step 6 validates the result.
- Type consistency: `async_print_sample(hass, entry)` (Task 2) matches the button's call (Task 3); `_BatchPage.print_text/print_qr` signatures (Task 1) match Task 2's calls; issue id `printer_not_calibrated_{entry_id}` used identically in Task 4 code and tests.
