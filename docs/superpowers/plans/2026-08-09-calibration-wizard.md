# Printer Calibration Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An options-flow wizard that prints test patterns and dials in `impl`, `width_pixels`, `line_width`, and (optionally) `codepage`, ending with a merge-save and a prefilled GitHub share link carrying the full measured support matrix + a draft escpos-printer-db profile snippet.

**Architecture:** A new pure-function module `_config_flow/calibration.py` (patterns, sample lines, share URL) + a new `CalibrationFlowMixin` in `_config_flow/calibration_steps.py` mixed into the existing `EscposOptionsFlowHandler`. `async_step_init` becomes a two-item menu (settings / calibrate). All prints go through the adapter's existing `print_image` (base64 data-URI source) and `print_text` (per-line `encoding`) — zero new runtime print paths. Only the summary step writes options, and it merges over `entry.options`.

**Tech Stack:** Python 3.14, HA options flow (`async_show_menu`, `cv.multi_select`), PIL, existing adapter pipeline.

**Spec:** `docs/superpowers/specs/2026-08-09-calibration-wizard-design.md`

## Global Constraints

- Work in the existing worktree on branch `feature/profiles-autodetect` (already checked out) — commit on top of current HEAD.
- NEVER `git stash` / `git reset`. `git status` before committing; stage only files your task touched.
- Run tests with `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest ...`; ruff + mypy must stay clean (`uv run ruff check .`, `uv run mypy custom_components/`).
- `except A, B:` (PEP 758, no parens) is valid here — don't "fix" it.
- strings.json edits must be mirrored manually in `custom_components/escpos_printer/translations/en.json`.
- Dependency pins untouched. Changelog folds under the existing `## [1.1.0]` section (Task 6 only).
- Wizard never blocks printing: empty/none answers leave settings unchanged; nothing is stored before the summary step.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: `calibration.py` — patterns, samples, share URL (pure functions)

**Files:**
- Create: `custom_components/escpos_printer/_config_flow/calibration.py`
- Test: `tests/test_calibration_helpers.py` (new)

**Interfaces:**
- Consumes: PIL (`PIL.Image`, `PIL.ImageDraw`), stdlib `base64`, `io`, `urllib.parse`.
- Produces (Tasks 3-5 import all of these by exact name):
  - `WIDTH_CANDIDATES: tuple[int, ...] = (384, 512, 576, 640)`
  - `IMPL_CANDIDATES: tuple[str, ...] = ("bitImageRaster", "bitImageColumn", "graphics")`
  - `CODEPAGE_CANDIDATES: tuple[str, ...] = ("CP858", "CP1252", "CP850", "ISO_8859_1", "CP437")` (capability order, broadest first)
  - `CODEPAGE_SAMPLE = "café ñ ü é ß ° €"`
  - `checkerboard_data_uri() -> str` — 192×48 px, 8-px squares, PNG base64 data URI
  - `width_bar_data_uri(width_px: int) -> str` — solid black bar `width_px`×28 with the white label `f"{width_px}"` drawn at x=4 (left edge, survives right-edge clipping)
  - `build_ruler(cols: int = 64) -> str` — `....+...1|....+...2|...` pattern: position i (1-based) is the tens digit at multiples of 10 (`1`,`2`,…,`6` at 10,20,…,60), `|` at multiples of 5 that aren't tens, `+` at… (see code below — keep exactly this layout)
  - `codepage_sample_line(encoding: str) -> str` — `CODEPAGE_SAMPLE` round-tripped through `encoding` with unencodable chars replaced by `?`
  - `build_share_url(model: str, results: dict[str, object]) -> str` — GitHub new-issue URL, fully URL-encoded

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calibration_helpers.py`:

```python
"""Tests for calibration wizard pattern/sample/share-link helpers."""

import base64
import io
from urllib.parse import parse_qs, urlparse

from PIL import Image

from custom_components.escpos_printer._config_flow.calibration import (
    CODEPAGE_CANDIDATES,
    CODEPAGE_SAMPLE,
    IMPL_CANDIDATES,
    WIDTH_CANDIDATES,
    build_ruler,
    build_share_url,
    checkerboard_data_uri,
    codepage_sample_line,
    width_bar_data_uri,
)


def _decode_data_uri(uri: str) -> Image.Image:
    assert uri.startswith("data:image/png;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    return Image.open(io.BytesIO(raw))


def test_checkerboard_dimensions() -> None:
    img = _decode_data_uri(checkerboard_data_uri())
    assert img.size == (192, 48)


def test_width_bar_exact_width_and_label_at_left() -> None:
    for width in WIDTH_CANDIDATES:
        img = _decode_data_uri(width_bar_data_uri(width)).convert("L")
        assert img.size == (width, 28)
        # Bar is black at the far right edge (clipping there is what we detect)
        assert img.getpixel((width - 1, 14)) < 64
        # Label pixels (white on black) exist in the left 80 px
        left = img.crop((0, 0, 80, 28))
        assert left.getextrema()[1] > 192


def test_ruler_layout() -> None:
    ruler = build_ruler(64)
    assert len(ruler) == 64
    # Tens digits sit at the multiple-of-10 positions (1-based)
    for tens in range(1, 7):
        assert ruler[tens * 10 - 1] == str(tens)


def test_codepage_sample_replaces_unencodable() -> None:
    # CP437 has no €; the sample must show ? instead, never drop the char
    line = codepage_sample_line("CP437")
    assert len(line) == len(CODEPAGE_SAMPLE)
    assert "?" in line
    # CP858 encodes the whole sample
    assert codepage_sample_line("CP858") == CODEPAGE_SAMPLE


def test_candidate_orders() -> None:
    assert IMPL_CANDIDATES[0] == "bitImageRaster"
    assert CODEPAGE_CANDIDATES[0] == "CP858"  # broadest first


def test_share_url_contains_everything() -> None:
    url = build_share_url(
        "Rongta RP850P",
        {
            "impl": "bitImageRaster",
            "impls_clean": ["bitImageRaster", "bitImageColumn"],
            "width_pixels": 576,
            "line_width": 48,
            "codepage": "CP858",
            "codepages_match": ["CP858", "CP850"],
            "profile": "",
            "integration_version": "1.1.0",
            "escpos_version": "3.1",
        },
    )
    parsed = urlparse(url)
    assert parsed.netloc == "github.com"
    assert parsed.path == "/cognitivegears/ha-escpos-thermal-printer/issues/new"
    qs = parse_qs(parsed.query)
    assert qs["title"] == ["Printer calibration: Rongta RP850P"]
    body = qs["body"][0]
    for expected in (
        "Rongta RP850P",
        "576",
        "48",
        "CP858",
        "bitImageColumn",
        "bitImageRaster: true",  # draft profile YAML snippet
        "media:",
    ):
        assert expected in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_calibration_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: ..._config_flow.calibration`

- [ ] **Step 3: Implement**

Create `custom_components/escpos_printer/_config_flow/calibration.py`:

```python
"""Pure helpers for the printer calibration wizard.

Pattern generators, codepage sample lines, and the GitHub share-link
builder. No printer I/O here — the flow steps in calibration_steps.py
do the printing via the adapter's existing pipeline.
"""

from __future__ import annotations

import base64
import io
from urllib.parse import quote

from PIL import Image, ImageDraw

WIDTH_CANDIDATES: tuple[int, ...] = (384, 512, 576, 640)
IMPL_CANDIDATES: tuple[str, ...] = ("bitImageRaster", "bitImageColumn", "graphics")
# Capability order, broadest encoding first: the wizard stores the first
# checked candidate in this order, so ties resolve to the most capable.
CODEPAGE_CANDIDATES: tuple[str, ...] = ("CP858", "CP1252", "CP850", "ISO_8859_1", "CP437")
CODEPAGE_SAMPLE = "café ñ ü é ß ° €"

_ISSUES_URL = "https://github.com/cognitivegears/ha-escpos-thermal-printer/issues/new"


def _png_data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def checkerboard_data_uri() -> str:
    """192x48 checkerboard of 8px squares — garbles visibly on a wrong impl."""
    img = Image.new("1", (192, 48), 1)
    draw = ImageDraw.Draw(img)
    for y in range(0, 48, 8):
        for x in range(0, 192, 8):
            if (x // 8 + y // 8) % 2 == 0:
                draw.rectangle((x, y, x + 7, y + 7), fill=0)
    return _png_data_uri(img)


def width_bar_data_uri(width_px: int) -> str:
    """Solid bar exactly width_px wide, labeled at the LEFT edge.

    Bars at or beyond the true printable width clip to identical length;
    the left-edge label survives the right-edge clipping.
    """
    img = Image.new("1", (width_px, 28), 0)
    draw = ImageDraw.Draw(img)
    draw.text((4, 7), str(width_px), fill=1)
    return _png_data_uri(img)


def build_ruler(cols: int = 64) -> str:
    """ASCII column ruler: tens digits at 10/20/..., '|' at other 5s, '.' fill."""
    chars = []
    for i in range(1, cols + 1):
        if i % 10 == 0:
            chars.append(str(i // 10))
        elif i % 5 == 0:
            chars.append("|")
        else:
            chars.append(".")
    return "".join(chars)


def codepage_sample_line(encoding: str) -> str:
    """The sample round-tripped through ``encoding``; unencodable chars -> '?'."""
    return CODEPAGE_SAMPLE.encode(encoding, errors="replace").decode(encoding)


def build_share_url(model: str, results: dict[str, object]) -> str:
    """Prefilled GitHub new-issue URL with the full measured dataset."""
    impls = results.get("impls_clean") or []
    codepages = results.get("codepages_match") or []
    feature_lines = "\n".join(
        f"    {impl}: {'true' if impl in impls else 'false'}" for impl in IMPL_CANDIDATES
    )
    body = (
        f"Printer model: {model}\n"
        f"Configured profile: {results.get('profile') or '(generic)'}\n\n"
        f"Calibration results:\n"
        f"- Image implementation stored: {results.get('impl') or '(unchanged)'}\n"
        f"- Implementations that printed cleanly: {', '.join(map(str, impls)) or 'none'}\n"
        f"- Printable width: {results.get('width_pixels') or '(unchanged)'} px\n"
        f"- Columns (font A): {results.get('line_width') or '(unchanged)'}\n"
        f"- Codepage stored: {results.get('codepage') or '(unchanged)'}\n"
        f"- Codepages that matched: {', '.join(map(str, codepages)) or '(step skipped)'}\n\n"
        f"Versions: integration {results.get('integration_version', '?')}, "
        f"python-escpos {results.get('escpos_version', '?')}\n\n"
        f"Draft escpos-printer-db profile:\n\n"
        f"```yaml\n"
        f"{model}:\n"
        f"  name: {model}\n"
        f"  notes: Hardware-verified via HA calibration wizard\n"
        f"  media:\n"
        f"    width:\n"
        f"      pixels: {results.get('width_pixels') or 'null'}\n"
        f"  features:\n"
        f"{feature_lines}\n"
        f"```\n"
    )
    title = f"Printer calibration: {model}"
    return f"{_ISSUES_URL}?title={quote(title)}&body={quote(body)}"
```

(If PIL's default bitmap font makes `draw.text` unavailable on mode "1" images, draw the label on an "L" image and `convert("1")` — adjust while keeping the test contract: exact bar width, black right edge, bright label pixels on the left.)

- [ ] **Step 4: Run tests**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_calibration_helpers.py -v`
Expected: PASS (7)

- [ ] **Step 5: Lint, then commit**

Run `uv run ruff check .` and `uv run mypy custom_components/`; fix trivia.

```bash
git add custom_components/escpos_printer/_config_flow/calibration.py tests/test_calibration_helpers.py
git commit -m "feat: calibration wizard pattern/sample/share-link helpers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Options-flow menu (settings / calibrate)

**Files:**
- Modify: `custom_components/escpos_printer/_config_flow/options_flow.py`
- Modify: `custom_components/escpos_printer/strings.json`, `translations/en.json`
- Modify (mechanical): `tests/test_options_flow_custom.py`, `tests/test_config_flow_options_and_duplicate.py`, `tests/test_width_override.py` (14 `options.async_init` call sites total)

**Interfaces:**
- Produces: `async_step_init` shows a menu with `menu_options=["settings", "calibrate"]`; the old init logic lives unchanged in `async_step_settings` (its form `step_id` becomes `"settings"`); `async_step_calibrate` exists as a stub that Task 3 replaces (for this task it may simply `return await self.async_step_settings()` with a `# ponytail: Task 3 replaces this` comment — NO, see below: implement it as the mixin entry hook named `async_step_calibrate` raising `NotImplementedError` is forbidden in flows; instead have it abort with reason `"calibration_unavailable"` so the menu is honest until Task 3 lands).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_flow_options_and_duplicate.py` (adapt imports to the file's style):

```python
async def test_options_flow_shows_menu_first(hass, ...existing fixture...):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert set(result["menu_options"]) == {"settings", "calibrate"}
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "settings"
```

(Reuse whatever mock-entry fixture the file's existing options tests use.)

- [ ] **Step 2: Run to verify it fails**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_config_flow_options_and_duplicate.py -v -k menu`
Expected: FAIL — result type is "form"

- [ ] **Step 3: Implement**

In `options_flow.py`:

```python
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Entry menu: regular settings or the calibration wizard."""
        return self.async_show_menu(step_id="init", menu_options=["settings", "calibrate"])
```

Rename the current `async_step_init` body to `async_step_settings` (keep its `# noqa` markers) and change its `async_show_form(step_id="init", ...)` call(s) to `step_id="settings"`. Add a temporary:

```python
    async def async_step_calibrate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Calibration wizard entry — implemented in CalibrationFlowMixin (Task 3)."""
        return self.async_abort(reason="calibration_unavailable")
```

`strings.json` (mirror in `translations/en.json`):
- `options.step.init` becomes `{"menu_options": {"settings": "Printer settings", "calibrate": "Calibrate printer (prints test pages)"}}`.
- The old `options.step.init` `data`/`data_description` content moves verbatim to `options.step.settings`.
- Add `options.abort.calibration_unavailable: "Calibration is not available."` (Task 3 removes it.)

Update the 14 `options.async_init` test call sites: insert the menu hop
(`async_configure(result["flow_id"], {"next_step_id": "settings"})`) and update any
`step_id == "init"` assertions to `"settings"`. Write one tiny test helper if the same
file repeats the hop more than 3 times.

- [ ] **Step 4: Run the affected suites**

Run: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest tests/test_options_flow_custom.py tests/test_config_flow_options_and_duplicate.py tests/test_width_override.py -q`
Expected: PASS. Then full suite: `ESC_POS_DISABLE_PLATFORMS=1 uv run pytest -q` — PASS.

- [ ] **Step 5: Lint + commit**

```bash
git add -A && git commit -m "feat: options flow menu — settings vs calibration wizard

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Wizard steps — impl + width

**Files:**
- Create: `custom_components/escpos_printer/_config_flow/calibration_steps.py`
- Modify: `custom_components/escpos_printer/_config_flow/options_flow.py` (mix in; replace the Task-2 `async_step_calibrate` stub)
- Test: `tests/test_calibration_flow.py` (new)

**Interfaces:**
- Consumes: Task 1 helpers; `self.config_entry.runtime_data.adapter` (the live adapter; `print_image(hass, image=<data URI>, impl=..., cut="none", feed=1, dither="threshold", auto_resize=False)` and `print_text(hass, text=..., cut="none", feed=1)`).
- Produces: `CalibrationFlowMixin` with `async_step_calibrate` (guard + route to impl step), `async_step_calibrate_impl`, `async_step_calibrate_width`; wizard state dicts `self._calib: dict[str, Any]` (pending option values) and `self._calib_extra: dict[str, Any]` (full multi-select sets, for the share link). Task 4 adds the next steps to the same mixin; Task 5 reads both dicts.

**Design (binding):**
- `async_step_calibrate`: if the entry is not loaded (`self.config_entry.state is not ConfigEntryState.LOADED`) → `async_abort(reason="printer_not_ready")`. Else init `self._calib = {}`, `self._calib_extra = {}` and `return await self.async_step_calibrate_impl()`.
- Print-on-entry pattern for every wizard step: when `user_input is None` **or** the submitted action is `"reprint"`, run the step's prints inside `try/except Exception` — on failure set `errors["base"] = "calibration_print_failed"` (and log with `sanitize_log_message`); always fall through to `async_show_form`. Only a non-reprint submission advances.
- impl step prints, per candidate in `IMPL_CANDIDATES` order: `print_text(hass, text=f"TEST {n}", cut="none", feed=0)` then `print_image(hass, image=checkerboard_data_uri(), impl=candidate, cut="none", feed=1, dither="threshold", auto_resize=False)`. A per-candidate print failure prints the text label `f"TEST {n}: FAILED TO SEND"` instead where possible and is treated as "not clean" — do NOT fail the whole step if at least one candidate printed (a printer rejecting `graphics` at the transport level must not brick the wizard).
- impl form: `vol.Optional("impls_clean", default=[]): cv.multi_select({"bitImageRaster": "Pattern 1 (Raster)", "bitImageColumn": "Pattern 2 (Column)", "graphics": "Pattern 3 (Graphics)"})` + `vol.Required("action", default="continue"): vol.In({"continue": "Continue", "reprint": "Reprint the test page"})`.
- On continue: `self._calib_extra["impls_clean"] = selection`; if selection non-empty, `self._calib["impl"] = next(c for c in IMPL_CANDIDATES if c in selection)`; route to width step. Empty selection still continues (spec: warn-but-continue using raster for later prints; the *stored* impl stays unchanged).
- width step prints the four bars (`width_bar_data_uri(w)` for `WIDTH_CANDIDATES`, `impl=self._calib.get("impl", "bitImageRaster")`, `cut="none"`, `feed=1`, `auto_resize=False`). Form: `vol.Required("first_equal", default="none"): vol.In({"384": "Bar 1 (384)", "512": "Bar 2 (512)", "576": "Bar 3 (576)", "640": "Bar 4 (640)", "none": "Not sure / bars unclear"})` + the same action dropdown. On continue: if not "none", `self._calib["width_pixels"] = int(choice)`; route to `async_step_calibrate_ruler` (Task 4 — for THIS task, route to a placeholder `async_step_calibrate_summary` that Task 5 implements; for Task 3 alone, make the width step's continue path `return self.async_abort(reason="calibration_unavailable")` with a `# Task 4 wires the next step` comment, and the flow test asserts up to that abort).

- [ ] **Step 1: Write failing tests** — `tests/test_calibration_flow.py` with a `MockConfigEntry` whose `runtime_data` carries a `MagicMock` adapter with `print_image`/`print_text` as `AsyncMock`s, entry state LOADED (follow the repo's existing options-flow test fixtures; set `entry.runtime_data` directly). Tests:
  - menu → calibrate with unloaded entry aborts `printer_not_ready`.
  - calibrate prints 3 labels + 3 checkerboards (assert `print_text` awaited 3×, `print_image` 3× with `impl` kwargs in candidate order) and shows form `calibrate_impl`.
  - submitting `{"impls_clean": ["bitImageColumn"], "action": "continue"}` stores pending impl "bitImageColumn" and advances to `calibrate_width` (4 more `print_image` calls, one per bar width, each with `impl="bitImageColumn"`).
  - `action: "reprint"` on the impl form re-prints and re-shows the same step.
  - adapter `print_image` raising on ALL candidates → form re-shown with `errors["base"] == "calibration_print_failed"`.
- [ ] **Step 2: Run to verify failure** (`ModuleNotFoundError` / abort mismatch).
- [ ] **Step 3: Implement** per the binding design. Mix `CalibrationFlowMixin` into the options-flow handler class and delete the Task-2 stub + its abort string (keep `printer_not_ready` abort string; add it to strings.json + en.json now: `options.abort.printer_not_ready: "The printer is not connected — load the integration before calibrating."` and `options.error.calibration_print_failed: "Printing the test page failed. Check the printer and try again."`).
- [ ] **Step 4: Run** the new file + full suite; ruff + mypy clean.
- [ ] **Step 5: Commit** (`feat: calibration wizard — impl and width steps`, with trailer).

---

### Task 4: Wizard steps — ruler + codepage

**Files:**
- Modify: `custom_components/escpos_printer/_config_flow/calibration_steps.py`
- Modify: `tests/test_calibration_flow.py`

**Interfaces:**
- Consumes: `build_ruler`, `CODEPAGE_CANDIDATES`, `codepage_sample_line`, adapter `print_text(hass, text=..., encoding=..., cut="none", feed=...)`.
- Produces: `async_step_calibrate_ruler`, `async_step_calibrate_codepage`; width step's continue path now routes to the ruler step (replace the Task-3 abort).

**Design (binding):**
- ruler step prints `print_text(hass, text=build_ruler(64), cut="none", feed=1)` (no encoding — plain ASCII). Form: `vol.Required("last_marker", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=96))` + action dropdown (`continue`/`reprint`). `0` = "don't know / skip" (described in strings): leaves `line_width` unchanged; any 16–96 value → `self._calib["line_width"] = value`; values 1–15 are rejected by a form error `invalid_line_width` (add to strings). Route → codepage step.
- codepage candidates: profile-aware — `get_profile_codepages(profile)` intersected with `CODEPAGE_CANDIDATES` order when a profile is configured and the intersection is non-empty, else `CODEPAGE_CANDIDATES` (compute via executor job; the capabilities load is blocking).
- codepage step prints, per candidate n: `print_text(hass, text=f"{n}: {codepage_sample_line(cp)}", encoding=cp, cut="none", feed=0)` then a final `feed=2` blank print or feed on the last line. A per-candidate encoding/print failure prints nothing for that line and excludes it from the choices shown (log at debug).
- codepage form: `vol.Optional("codepages_match", default=[]): cv.multi_select({cp: f"Line {n}: {cp}" ...})` + `vol.Required("action", default="continue"): vol.In({"continue": ..., "reprint": ..., "skip": "Skip this step"})`. On skip: store nothing, route to summary. On continue: `self._calib_extra["codepages_match"] = selection`; non-empty → `self._calib["codepage"] = first checked in candidate order`; route to summary (Task 5 — for THIS task alone, `async_abort(reason="calibration_unavailable")` again with a comment; tests assert up to it).
- The reference string for the step description is provided via `description_placeholders={"sample": CODEPAGE_SAMPLE}`.

- [ ] **Step 1: Failing tests** — ruler prints once + stores 48; ruler `0` skips storing; codepage prints one line per candidate with the right `encoding` kwarg; multi-select `["CP850", "CP858"]` stores `codepage == "CP858"` (capability order, not selection order); skip stores nothing; reprint re-prints.
- [ ] **Step 2: RED**, **Step 3: implement** (strings additions: ruler + codepage step text with the on-screen sample and the "0 = skip" explanation; mirror en.json), **Step 4: suites + lint**, **Step 5: commit** (`feat: calibration wizard — ruler and codepage steps`, trailer).

---

### Task 5: Summary step — merge-save + share link

**Files:**
- Modify: `custom_components/escpos_printer/_config_flow/calibration_steps.py`
- Modify: `tests/test_calibration_flow.py`

**Interfaces:**
- Consumes: `build_share_url` (Task 1); `CONF_IMPL`, `CONF_WIDTH_PIXELS`, `CONF_LINE_WIDTH`, `CONF_CODEPAGE` from `..const`; `importlib.metadata.version` (executor not required — metadata read is cheap, but do it in the executor anyway alongside the profile lookup to stay obviously safe).
- Produces: `async_step_calibrate_summary`; codepage/width steps route here (replace Task-4 abort).

**Design (binding):**
- Form: `vol.Optional("model", default="")`: str + `vol.Required("action", default="save"): vol.In({"save": "Save calibration", "discard": "Discard (save nothing)"})`.
- `description_placeholders`: measured values (or "unchanged") AND `share_url` built from `build_share_url(model or "Unknown printer", results)` — note the URL must reflect the CURRENT form's model field only after submit; for the initial render use the placeholder model "your printer model". Simplest compliant approach: render the share link on the summary description using the results with model "—", and ALSO re-show the summary once after a save-with-model? No — keep it simple and honest: the summary form shows measured values; the share link is rendered in the step description from current results with the model appearing as entered-so-far (initial render: generic). After **save**, show a final `async_show_form(step_id="calibrate_done")`-style… **Decision (binding): two-screen finish.** `calibrate_summary` collects `model` + action; on save it computes merged options, creates the entry via `async_create_entry(title="", data=merged)` — but since options flows END on create_entry, the share link must be ON the summary screen. Therefore: build the share URL at summary render time from `self._calib`/`self._calib_extra` with the model slot filled by the literal text `YOUR-PRINTER-MODEL` (users edit the prefilled issue title/body on GitHub anyway — the link is complete except the model). The `model` form field feeds ONLY the URL regeneration on `action == "refresh_link"` (third action choice, "Update share link with my model") which re-shows the summary with the model-substituted URL. This keeps everything in one flow with no post-save screen.
- Save: `merged = {**dict(self.config_entry.options)}` then apply `self._calib` mappings (`impl`→CONF_IMPL, `width_pixels`→CONF_WIDTH_PIXELS, `line_width`→CONF_LINE_WIDTH, `codepage`→CONF_CODEPAGE — only keys present in `self._calib`); `return self.async_create_entry(title="", data=merged)`. Discard: `return self.async_abort(reason="calibration_discarded")` (add abort string).
- `results` for the URL: `impl`/`width_pixels`/`line_width`/`codepage` from `self._calib`, `impls_clean`/`codepages_match` from `self._calib_extra`, `profile` = currently configured profile (options-over-data), `integration_version` = `importlib.metadata.version("ha-escpos-thermal-printer")` — if that dist name isn't installed (dev checkout), fall back to reading `manifest.json`'s version via `json.load` in the executor; `escpos_version` = `importlib.metadata.version("python-escpos")`.

- [ ] **Step 1: Failing tests** — full wizard run ends in `create_entry` whose data preserves a pre-existing unrelated option (e.g. `timeout: 7.0`) AND contains the four measured keys; skip-codepage run omits `CONF_CODEPAGE`; discard aborts without touching options; summary description placeholders include a `share_url` containing the measured width; `refresh_link` with model "Rongta RP850P" produces a URL containing the encoded model.
- [ ] **Step 2: RED**, **Step 3: implement** (+ strings: summary step description with the markdown share link `[Open a prefilled GitHub issue]({share_url})`, done/discard abort strings; mirror en.json), **Step 4: suites + lint**, **Step 5: commit** (`feat: calibration wizard — summary, merge-save, share link`, trailer).

---

### Task 6: Copy polish, changelog, full validation

**Files:**
- Modify: `custom_components/escpos_printer/strings.json`, `translations/en.json` (read every wizard step's copy end-to-end for coherence; ensure each step description says what the printer should have just printed)
- Modify: `CHANGELOG.md`

- [ ] **Step 1:** Proofread all wizard strings as a set; verify strings.json and en.json are identical for the new keys (`python3 -c` diff of the two JSON subtrees is acceptable evidence).
- [ ] **Step 2:** CHANGELOG under `## [1.1.0]` → Added:

```markdown
- Printer calibration wizard (Settings → Configure → "Calibrate printer"):
  prints guided test pages to dial in image implementation, paper width,
  columns, and (optionally) codepage, then saves them for the entry — and
  offers a prefilled GitHub issue link with the full measured support matrix
  and a draft printer profile for contributing back.
```

- [ ] **Step 3:** Full battery, all must pass:

```bash
ESC_POS_DISABLE_PLATFORMS=1 uv run pytest -q
uv run ruff check .
uv run mypy custom_components/
uv run python scripts/check_requirements_sync.py
uv run python scripts/sync_service_translations.py --check
uv run python scripts/check_version_sync.py
pre-commit run --all-files
```

- [ ] **Step 4: Commit** (`feat: calibration wizard copy + changelog`, trailer).

---

## Self-review notes

- Spec coverage: menu → Task 2; impl/width steps → Task 3; ruler/codepage (skippable, on-screen reference, multi-select, capability order) → Task 4; summary merge-save + model field + share link with full matrix + draft YAML → Tasks 1+5; failure handling (`calibration_print_failed`, per-candidate tolerance, no partial saves) → Tasks 3-5; `GS ( A` stretch → deliberately omitted (needs a raw-bytes adapter method; defer per spec).
- Type consistency: `self._calib` keys are exactly `impl`/`width_pixels`/`line_width`/`codepage` in Tasks 3-5; `self._calib_extra` keys `impls_clean`/`codepages_match` defined in Task 3/4 and consumed in Task 5; helper names match Task 1's test imports.
- Known executor judgment calls for implementers: capabilities lookups (profile codepages) must go through `hass.async_add_executor_job`; adapter print calls are already async.
