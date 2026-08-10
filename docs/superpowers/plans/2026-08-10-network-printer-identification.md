# Network Printer Identification & DHCP Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify network printers via ESC/POS `GS I` transmit-printer-ID queries (device card, profile hint, calibrate prefill) and auto-discover them via DHCP hostname matchers (`tm-*`, `rongta_*`).

**Architecture:** A raw-socket `query_printer_id()` helper in `_config_flow/network_helpers.py` (same style as the existing `_can_connect`) runs during the network config-flow step; results persist as `detected_manufacturer`/`detected_model` in `entry.data` and are consumed by `device.py`, the profile-dropdown default (discovery flows only), and the calibration summary's model field. A new `DiscoveryFlowMixin` (`_config_flow/discovery_steps.py`) handles `async_step_dhcp`: probe port 9100, query the ID, hand off to the existing network form with host prefilled.

**Tech Stack:** Python 3.14, Home Assistant custom integration, voluptuous, pytest + pytest-homeassistant-custom-component. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-10-network-printer-identification-design.md`

## Global Constraints

- No new runtime dependencies; `manifest.json` `requirements` unchanged.
- All printer I/O runs on executor threads via `hass.async_add_executor_job()` — never block the event loop with sockets.
- `query_printer_id` must never raise and never change printer state (transmit-ID commands are read-only).
- DHCP matchers are evidence-only: exactly `{"hostname": "tm-*"}` and `{"hostname": "rongta_*"}`. Do not add more.
- Discovery false positives must abort **silently** (no user-visible card) when port 9100 is closed.
- Profile suggestion preselects a dropdown default only — never auto-commits a profile.
- PEP 758 (`except A, B:`) is valid in this repo (Python ≥ 3.14.2 floor); do not "fix" it.
- Every user-visible change gets a CHANGELOG entry under `## [Unreleased]`.
- `strings.json` and `translations/en.json` must stay mirrored for every key touched.
- Verification commands: `uv run pytest -q` (all unit tests), `uv run ruff check .`, `uv run mypy custom_components/`.
- Commit messages end with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: `query_printer_id` helper

**Files:**
- Modify: `custom_components/escpos_printer/_config_flow/network_helpers.py`
- Test: `tests/test_network_helpers_query.py` (new)

**Interfaces:**
- Consumes: nothing new (stdlib `socket`, existing module).
- Produces: `query_printer_id(host: str, port: int, timeout: float) -> dict[str, str] | None` — keys `"manufacturer"` and/or `"model"` (non-empty strings, either may be absent), or `None` if nothing was identified. Also module-private `_read_id_reply(sock) -> str | None` (unit-tested directly).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_network_helpers_query.py`:

```python
"""Tests for the GS I printer-ID query helper."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

from custom_components.escpos_printer._config_flow.network_helpers import (
    _read_id_reply,
    query_printer_id,
)


class FakeSocket:
    """recv() feeds back a canned byte stream one byte at a time."""

    def __init__(self, payload: bytes) -> None:
        self._buf = list(payload)
        self.sent: list[bytes] = []

    def recv(self, _n: int) -> bytes:
        if not self._buf:
            raise socket.timeout("timed out")
        return bytes([self._buf.pop(0)])

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def settimeout(self, _t: float) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_read_id_reply_happy_path():
    assert _read_id_reply(FakeSocket(b"\x5fTM-T20II\x00")) == "TM-T20II"


def test_read_id_reply_no_data_times_out():
    assert _read_id_reply(FakeSocket(b"")) is None


def test_read_id_reply_missing_header_is_garbage():
    assert _read_id_reply(FakeSocket(b"TM-T20II\x00")) is None


def test_read_id_reply_missing_nul_hits_length_cap():
    # 200 printable bytes, no terminator: reply is capped, then rejected
    # only if the header is absent; with header it returns the capped text.
    assert _read_id_reply(FakeSocket(b"\x5f" + b"A" * 200)) == "A" * 79


def test_read_id_reply_empty_string_reply():
    assert _read_id_reply(FakeSocket(b"\x5f\x00")) is None


def test_read_id_reply_strips_nonascii():
    assert _read_id_reply(FakeSocket(b"\x5fTM\xff-T20\x00")) == "TM-T20"


def test_query_printer_id_both_replies():
    payload = b"\x5fEPSON\x00\x5fTM-T20II\x00"
    fake = FakeSocket(payload)
    with patch(
        "custom_components.escpos_printer._config_flow.network_helpers.socket.create_connection",
        return_value=fake,
    ):
        result = query_printer_id("192.168.10.157", 9100, 4.0)
    assert result == {"manufacturer": "EPSON", "model": "TM-T20II"}
    assert fake.sent == [b"\x1d\x49\x42", b"\x1d\x49\x43"]


def test_query_printer_id_silent_clone_returns_none():
    # Clone never answers: first read times out -> None, no exception.
    with patch(
        "custom_components.escpos_printer._config_flow.network_helpers.socket.create_connection",
        return_value=FakeSocket(b""),
    ):
        assert query_printer_id("192.168.10.157", 9100, 4.0) is None


def test_query_printer_id_maker_only():
    # Maker answers, model read times out -> partial dict survives.
    with patch(
        "custom_components.escpos_printer._config_flow.network_helpers.socket.create_connection",
        return_value=FakeSocket(b"\x5fEPSON\x00"),
    ):
        assert query_printer_id("192.168.10.157", 9100, 4.0) == {"manufacturer": "EPSON"}


def test_query_printer_id_connection_refused_returns_none():
    with patch(
        "custom_components.escpos_printer._config_flow.network_helpers.socket.create_connection",
        side_effect=ConnectionRefusedError,
    ):
        assert query_printer_id("192.168.10.157", 9100, 4.0) is None


def test_query_printer_id_never_raises_on_weird_oserror():
    sock = MagicMock()
    sock.__enter__ = MagicMock(return_value=sock)
    sock.__exit__ = MagicMock(return_value=False)
    sock.sendall.side_effect = OSError("broken pipe")
    with patch(
        "custom_components.escpos_printer._config_flow.network_helpers.socket.create_connection",
        return_value=sock,
    ):
        assert query_printer_id("192.168.10.157", 9100, 4.0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_network_helpers_query.py -v`
Expected: FAIL — `ImportError: cannot import name '_read_id_reply'`

- [ ] **Step 3: Implement the helper**

Append to `custom_components/escpos_printer/_config_flow/network_helpers.py` (after `_can_connect`):

```python
# --- GS I (Transmit Printer ID) query -------------------------------------
#
# Epson network printers answer GS I 66/67 with the maker/model name framed
# as 0x5F <ascii> 0x00. Clones typically ignore the command entirely; the
# short read timeout turns that silence into a clean None. The commands are
# read-only: nothing is printed and no printer state changes.

_GS_I_MAKER = b"\x1d\x49\x42"  # GS I 66 -> maker name ("EPSON")
_GS_I_MODEL = b"\x1d\x49\x43"  # GS I 67 -> model name ("TM-T20II")
_ID_HEADER = 0x5F
_ID_MAX_LEN = 80
_ID_READ_TIMEOUT = 2.0


def _read_id_reply(sock: socket.socket) -> str | None:
    """Read one 0x5F...0x00 framed reply; None on timeout/garbage/empty."""
    data = bytearray()
    try:
        while len(data) < _ID_MAX_LEN:
            chunk = sock.recv(1)
            if not chunk or chunk == b"\x00":
                break
            data += chunk
    except OSError:
        pass  # timeout mid-reply: fall through and parse what we have
    if not data or data[0] != _ID_HEADER:
        return None
    text = data[1:].decode("ascii", errors="ignore").strip()
    return text or None


def query_printer_id(host: str, port: int, timeout: float) -> dict[str, str] | None:
    """Best-effort printer identification via GS I over raw TCP.

    Returns {"manufacturer": ..., "model": ...} (either key may be
    absent), or None when nothing was identified. Never raises.
    """
    result: dict[str, str] = {}
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(_ID_READ_TIMEOUT)
            for key, command in (("manufacturer", _GS_I_MAKER), ("model", _GS_I_MODEL)):
                sock.sendall(command)
                value = _read_id_reply(sock)
                if value is None:
                    break  # no answer: don't wait out a second timeout
                result[key] = value
    except OSError:
        _LOGGER.debug("GS I query failed for %s:%s", host, port)
    return result or None
```

Note `_read_id_reply` swallows the timeout itself, so `query_printer_id`'s
`break` fires on silence — a silent clone costs one ~2 s read timeout, not two.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_network_helpers_query.py -v`
Expected: all PASS

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy custom_components/`
Expected: clean.

```bash
git add custom_components/escpos_printer/_config_flow/network_helpers.py tests/test_network_helpers_query.py
git commit -m "feat: GS I printer-ID query helper for network printers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Persist detected fields through the network config flow

**Files:**
- Modify: `custom_components/escpos_printer/const.py` (add two CONF_ keys near the other configuration keys, ~line 22)
- Modify: `custom_components/escpos_printer/_config_flow/main_flow.py:46-53` (`__init__`)
- Modify: `custom_components/escpos_printer/_config_flow/network_steps.py`
- Modify: `tests/test_config_flow.py` (existing network-step tests must patch the new query)
- Test: `tests/test_config_flow.py` (new tests appended)

**Interfaces:**
- Consumes: `query_printer_id(host, port, timeout) -> dict[str, str] | None` from Task 1 (keys `"manufacturer"`/`"model"`).
- Produces:
  - `const.CONF_DETECTED_MANUFACTURER = "detected_manufacturer"` and `const.CONF_DETECTED_MODEL = "detected_model"` — `entry.data` keys later tasks read.
  - `EscposConfigFlow._detected: dict[str, str]` — raw query result (keys `"manufacturer"`/`"model"`), populated by discovery (Task 5) or by the network submit; consumed by the network step.

- [ ] **Step 1: Add the constants**

In `custom_components/escpos_printer/const.py`, after `CONF_ALLOW_LOCAL_IMAGE_URLS`:

```python
# Best-effort GS I identification captured during config flow (network
# printers only). Absent when the printer didn't answer.
CONF_DETECTED_MANUFACTURER = "detected_manufacturer"
CONF_DETECTED_MODEL = "detected_model"
```

- [ ] **Step 2: Update existing tests to patch the query (they would otherwise open real sockets)**

Every existing test that patches `network_steps._can_connect` drives the network submit path, which now also calls `query_printer_id`. Find them:

Run: `grep -rn "network_steps._can_connect" tests/`

In **each** listed `with patch(...)` context (files: `tests/test_config_flow.py`, `tests/test_config_flow_options_and_duplicate.py`, `tests/test_config_flow_reconfigure.py`, `tests/test_config_flow_negative.py` — confirm via the grep), add a second patch alongside:

```python
patch(
    "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
    return_value=None,
),
```

(Patch target is `network_steps.query_printer_id` because Step 3 imports it into that namespace.) Tests that only exercise `cannot_connect` never reach the query, but patching uniformly is harmless and future-proof.

- [ ] **Step 3: Write the failing new tests**

Append to `tests/test_config_flow.py`:

```python
async def test_network_flow_persists_detected_fields(hass):
    """GS I result lands in entry.data as detected_manufacturer/model."""
    from custom_components.escpos_printer.const import (
        CONF_DETECTED_MANUFACTURER,
        CONF_DETECTED_MODEL,
    )

    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value={"manufacturer": "EPSON", "model": "TM-T20II"},
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.10.157", CONF_PORT: 9100}
        )
        # Complete the codepage step with defaults to create the entry.
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DETECTED_MANUFACTURER] == "EPSON"
    assert result["data"][CONF_DETECTED_MODEL] == "TM-T20II"


async def test_network_flow_no_reply_omits_detected_fields(hass):
    """query_printer_id -> None leaves entry.data without detected keys."""
    from custom_components.escpos_printer.const import CONF_DETECTED_MODEL

    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value=None,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.10.157", CONF_PORT: 9100}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_DETECTED_MODEL not in result["data"]
```

Match the file's existing import style — it already imports `DOMAIN`, `CONF_HOST`, `CONF_PORT`, `config_entries`, `FlowResultType`, `patch`, and the codepage-step submit pattern (see the happy-path test at the top of the file); reuse those instead of re-importing. If the codepage step needs explicit fields in existing tests, copy the exact dict those tests pass.

- [ ] **Step 4: Run new tests to verify they fail**

Run: `uv run pytest tests/test_config_flow.py -v -k detected`
Expected: FAIL — `ImportError` (constants) or missing keys in `result["data"]`

- [ ] **Step 5: Implement flow persistence**

In `custom_components/escpos_printer/_config_flow/main_flow.py` `__init__` (line ~49), add:

```python
        self._detected: dict[str, str] = {}
```

In `custom_components/escpos_printer/_config_flow/network_steps.py`:

1. Extend the `.network_helpers` import (line 26):

```python
from .network_helpers import _can_connect, query_printer_id
```

2. Extend the `..const` import block (lines 18-25) with `CONF_DETECTED_MANUFACTURER, CONF_DETECTED_MODEL`.

3. In `async_step_network`, in the `if ok:` branch (after line 79's debug log, before `self._user_data = {...}`), run the query — reusing a discovery-time result when present:

```python
                detected = self._detected or (
                    await self.hass.async_add_executor_job(
                        query_printer_id, host, port, timeout
                    )
                    or {}
                )
```

and after the `self._user_data = {...}` assignment (line 89), merge it in:

```python
                if detected.get("manufacturer"):
                    self._user_data[CONF_DETECTED_MANUFACTURER] = detected["manufacturer"]
                if detected.get("model"):
                    self._user_data[CONF_DETECTED_MODEL] = detected["model"]
```

4. In `async_step_reconfigure_network`, in its `if ok:` branch (before the `title` logic at line 158), add:

```python
                detected = (
                    await self.hass.async_add_executor_job(
                        query_printer_id, host, port, timeout
                    )
                    or {}
                )
```

and extend `data_updates` (lines 167-171):

```python
                data_updates={
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_TIMEOUT: timeout,
                    **(
                        {CONF_DETECTED_MANUFACTURER: detected["manufacturer"]}
                        if detected.get("manufacturer")
                        else {}
                    ),
                    **(
                        {CONF_DETECTED_MODEL: detected["model"]}
                        if detected.get("model")
                        else {}
                    ),
                },
```

`type: ignore[attr-defined]` comments follow the file's existing pattern for mixin attributes if mypy complains about `self._detected`; prefer declaring it in the mixin's expected-attributes block (add `_detected: dict[str, str]` under `_user_data: dict[str, Any]` at line 47).

- [ ] **Step 6: Run the full flow test files**

Run: `uv run pytest tests/test_config_flow.py tests/test_config_flow_options_and_duplicate.py tests/test_config_flow_reconfigure.py tests/test_config_flow_negative.py -q`
Expected: all PASS (including the pre-existing tests updated in Step 2)

- [ ] **Step 7: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy custom_components/`

```bash
git add custom_components/escpos_printer/const.py custom_components/escpos_printer/_config_flow/main_flow.py custom_components/escpos_printer/_config_flow/network_steps.py tests/
git commit -m "feat: persist GS I detected manufacturer/model in network entries

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Device registry shows detected manufacturer/model

**Files:**
- Modify: `custom_components/escpos_printer/device.py:57-72`
- Test: `tests/test_device_info.py`

**Interfaces:**
- Consumes: `CONF_DETECTED_MANUFACTURER` / `CONF_DETECTED_MODEL` from Task 2.
- Produces: no new interface — `build_device_info(entry)` behavior change only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device_info.py` (mirror its existing entry-fixture style — it builds `MockConfigEntry` objects with `data={...}`; copy the exact constructor form used by the existing network test):

```python
def test_device_info_prefers_detected_fields():
    entry = _make_entry(  # use the file's existing helper/constructor pattern
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
            CONF_DETECTED_MANUFACTURER: "EPSON",
            CONF_DETECTED_MODEL: "TM-T20II",
        }
    )
    info = build_device_info(entry)
    assert info["manufacturer"] == "EPSON"
    assert info["model"] == "TM-T20II"


def test_device_info_falls_back_without_detected_fields():
    entry = _make_entry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK})
    info = build_device_info(entry)
    assert info["manufacturer"] == "ESC/POS"
    assert info["model"] == "Network Printer"
```

(Adapt `_make_entry` to whatever the file actually uses; the assertions are the contract.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_device_info.py -v`
Expected: new tests FAIL (manufacturer is `"ESC/POS"`)

- [ ] **Step 3: Implement**

In `custom_components/escpos_printer/device.py`, extend the `.const` import with `CONF_DETECTED_MANUFACTURER, CONF_DETECTED_MODEL`, then change `build_device_info`:

```python
def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Build the DeviceInfo shared by every entity on a config entry."""
    connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
    model = entry.data.get(CONF_DETECTED_MODEL) or _MODEL_BY_CONNECTION_TYPE.get(
        connection_type, "Network Printer"
    )
    manufacturer = entry.data.get(CONF_DETECTED_MANUFACTURER) or "ESC/POS"

    info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"ESC/POS Printer {entry.title}",
        manufacturer=manufacturer,
        model=model,
    )
    if connection_type == CONNECTION_TYPE_USB:
        serial = _usb_serial_number(entry)
        if serial:
            info["serial_number"] = serial
    return info
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_device_info.py -v`
Expected: all PASS

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy custom_components/`

```bash
git add custom_components/escpos_printer/device.py tests/test_device_info.py
git commit -m "feat: device registry shows GS I detected manufacturer/model

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Calibration share-link model prefill

**Files:**
- Modify: `custom_components/escpos_printer/_config_flow/calibration_steps.py` (`async_step_calibrate_summary`, the `vol.Optional("model", default="")` schema)
- Test: `tests/test_calibration_flow.py`

**Interfaces:**
- Consumes: `CONF_DETECTED_MODEL` from Task 2 (via `self.config_entry.data`).
- Produces: no new interface.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_calibration_flow.py`, following its existing options-flow setup pattern (it initializes the options flow and steps to `calibrate_summary`; copy the shortest existing summary-step test's scaffolding):

```python
async def test_calibrate_summary_prefills_detected_model(hass):
    """The share-link model field defaults to entry.data's detected model."""
    # Build the entry exactly like the file's existing summary tests, but
    # with CONF_DETECTED_MODEL: "TM-T20II" added to the entry data dict.
    ...  # scaffold copied from existing test
    # Reach the calibrate_summary form, then:
    schema = result["data_schema"].schema
    model_key = next(k for k in schema if k.schema == "model")
    assert model_key.default() == "TM-T20II"
```

(The scaffold is intentionally copied from the neighboring test in the same file — the new assertion block is the contract. Voluptuous stores defaults as callables, hence `model_key.default()`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_calibration_flow.py -v -k prefills`
Expected: FAIL — default is `""`

- [ ] **Step 3: Implement**

In `custom_components/escpos_printer/_config_flow/calibration_steps.py`:

1. Extend the `..const` import with `CONF_DETECTED_MODEL`.
2. In `async_step_calibrate_summary`, change the schema line:

```python
        schema = vol.Schema(
            {
                vol.Optional(
                    "model",
                    default=self.config_entry.data.get(CONF_DETECTED_MODEL, ""),
                ): str,
                vol.Required("action", default="save"): vol.In(_SUMMARY_ACTION_CHOICES),
            }
        )
```

- [ ] **Step 4: Run test file to verify it passes**

Run: `uv run pytest tests/test_calibration_flow.py -q`
Expected: all PASS

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy custom_components/`

```bash
git add custom_components/escpos_printer/_config_flow/calibration_steps.py tests/test_calibration_flow.py
git commit -m "feat: calibrate share-link model prefills from GS I detection

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

**Note:** `calibration_steps.py` has uncommitted user changes in the worktree. Do NOT `git stash`/`git reset`. Commit only the specific files listed (`git add` exactly those paths); if the user's uncommitted hunks are in the same file, commit the file as-is (their changes ride along is NOT acceptable — instead use `git add -p`-free approach: verify with `git diff --cached` before committing that only intended hunks are staged; if the user's unrelated hunks would be swept in, stop and report instead of committing).

---

### Task 5: DHCP discovery step

**Files:**
- Modify: `custom_components/escpos_printer/manifest.json` (add `dhcp` key)
- Create: `custom_components/escpos_printer/_config_flow/discovery_steps.py`
- Modify: `custom_components/escpos_printer/_config_flow/main_flow.py` (mixin wiring)
- Modify: `custom_components/escpos_printer/strings.json` + `custom_components/escpos_printer/translations/en.json` (`flow_title`, `abort.cannot_connect`)
- Test: `tests/test_config_flow_dhcp.py` (new)

**Interfaces:**
- Consumes: `query_printer_id` (Task 1), `self._detected` (Task 2), `_can_connect` (existing), `CONF_DETECTED_MODEL` (Task 2).
- Produces: `DiscoveryFlowMixin.async_step_dhcp(discovery_info: DhcpServiceInfo) -> ConfigFlowResult`; sets `self._detected` and `self._discovery_host` (a `str | None`, consumed by Task 6's network-form prefill).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_flow_dhcp.py`:

```python
"""DHCP discovery flow tests."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN

DISCOVERY = DhcpServiceInfo(
    ip="192.168.10.157",
    hostname="TM-T20II-628E52",
    macaddress="50579c628e52",
)


async def _start_dhcp_flow(hass, can_connect=True, query_result=None):
    with (
        patch(
            "custom_components.escpos_printer._config_flow.discovery_steps._can_connect",
            return_value=can_connect,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.discovery_steps.query_printer_id",
            return_value=query_result,
        ),
    ):
        return await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DISCOVERY
        )


async def test_dhcp_discovery_shows_network_form(hass):
    result = await _start_dhcp_flow(
        hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "network"
    # Host is prefilled from discovery.
    assert result["data_schema"]({})["host"] == "192.168.10.157"


async def test_dhcp_discovery_title_uses_detected_model(hass):
    await _start_dhcp_flow(hass, query_result={"model": "TM-T20II"})
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"] == {"name": "TM-T20II (192.168.10.157)"}


async def test_dhcp_discovery_title_falls_back_to_hostname(hass):
    await _start_dhcp_flow(hass, query_result=None)
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"] == {
        "name": "TM-T20II-628E52 (192.168.10.157)"
    }


async def test_dhcp_discovery_aborts_when_port_closed(hass):
    result = await _start_dhcp_flow(hass, can_connect=False)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_discovery_aborts_when_already_configured(hass):
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.10.157:9100",
        data={"connection_type": "network", "host": "192.168.10.157", "port": 9100},
    ).add_to_hass(hass)
    result = await _start_dhcp_flow(hass)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
```

If `result["data_schema"]({})` errors on other required-field defaults, assert the suggested value instead: `result["data_schema"].schema` iteration checking the `host` marker's `description["suggested_value"]` — pick whichever mechanism Task 6 Step 3 implements (suggested values; see that task).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_flow_dhcp.py -v`
Expected: FAIL — flow raises `UnknownStep` / `data_entry_flow.UnknownHandler` for source `dhcp`

- [ ] **Step 3: Add the manifest matchers**

In `custom_components/escpos_printer/manifest.json`, after the `"documentation"` key (alphabetical-ish placement with the existing keys, matching hassfest ordering: `dhcp` sorts after `documentation`... hassfest requires: domain, name, then alphabetical. Place `"dhcp"` between `"config_flow"` and `"documentation"`):

```json
  "dhcp": [
    { "hostname": "tm-*" },
    { "hostname": "rongta_*" }
  ],
```

Evidence (do not extend this list): Epson FAQ KA-01071 documents "product name + last 6 MAC digits" defaults (`TM-T88VI-C3FE21`, `TM-m30-FED95E`; user-verified `TM-T20II-628E52`); user-verified `Rongta_RP820`, generalized to the brand prefix because Rongta manufactures only printers.

- [ ] **Step 4: Create the discovery mixin**

Create `custom_components/escpos_printer/_config_flow/discovery_steps.py`:

```python
"""DHCP discovery step mixin.

Evidence-only hostname matchers live in manifest.json ("tm-*", "rongta_*").
A match is confirmed by a TCP probe of port 9100 before the user ever sees
a discovery card, so matcher false positives abort silently. The existing
network form is the confirmation UI — discovery just prefills it.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from ..const import DEFAULT_PORT, DEFAULT_TIMEOUT
from .network_helpers import _can_connect, query_printer_id

_LOGGER = logging.getLogger(__name__)


class DiscoveryFlowMixin:
    """Mixin providing the DHCP discovery entry point.

    Expects from the composed flow class:
    - hass, async_set_unique_id(), _abort_if_unique_id_configured(),
      async_abort(), async_step_network()
    - _detected: dict[str, str] (main_flow.__init__)
    - _discovery_host: str | None (main_flow.__init__)
    """

    hass: Any
    _detected: dict[str, str]
    _discovery_host: str | None

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Handle a DHCP-discovered printer candidate."""
        host = discovery_info.ip
        await self.async_set_unique_id(f"{host.lower()}:{DEFAULT_PORT}")  # type: ignore[attr-defined]
        self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

        if not await self.hass.async_add_executor_job(
            _can_connect, host, DEFAULT_PORT, DEFAULT_TIMEOUT
        ):
            _LOGGER.debug("DHCP match %s (%s) not listening on %s; ignoring",
                          discovery_info.hostname, host, DEFAULT_PORT)
            return self.async_abort(reason="cannot_connect")  # type: ignore[attr-defined,no-any-return]

        self._detected = (
            await self.hass.async_add_executor_job(
                query_printer_id, host, DEFAULT_PORT, DEFAULT_TIMEOUT
            )
            or {}
        )
        self._discovery_host = host
        name = self._detected.get("model") or discovery_info.hostname
        self.context["title_placeholders"] = {"name": f"{name} ({host})"}  # type: ignore[attr-defined]
        return await self.async_step_network()  # type: ignore[attr-defined,no-any-return]
```

- [ ] **Step 5: Wire the mixin and flow state**

In `custom_components/escpos_printer/_config_flow/main_flow.py`:

1. Import: `from .discovery_steps import DiscoveryFlowMixin`
2. Add `DiscoveryFlowMixin,` to the `EscposConfigFlow(...)` base list (after `NetworkFlowMixin,`).
3. In `__init__`, alongside `self._detected` (Task 2), add:

```python
        self._discovery_host: str | None = None
```

- [ ] **Step 6: Add strings**

In `custom_components/escpos_printer/strings.json` **and** `custom_components/escpos_printer/translations/en.json` (mirror exactly), inside the `"config"` object:

1. Top-level of `"config"` (sibling of `"step"`):

```json
"flow_title": "{name}",
```

2. In `"config"."abort"`, add:

```json
"cannot_connect": "The discovered device is not accepting printer connections."
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_config_flow_dhcp.py -v`
Expected: the abort tests PASS; the two form tests may still FAIL on host prefill (delivered by Task 6). If so, mark them `@pytest.mark.xfail(reason="host prefill lands in next task", strict=True)` **only** for `test_dhcp_discovery_shows_network_form`, and remove the xfail in Task 6. The title tests must pass now.

- [ ] **Step 8: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy custom_components/`

```bash
git add custom_components/escpos_printer/manifest.json custom_components/escpos_printer/_config_flow/discovery_steps.py custom_components/escpos_printer/_config_flow/main_flow.py custom_components/escpos_printer/strings.json custom_components/escpos_printer/translations/en.json tests/test_config_flow_dhcp.py
git commit -m "feat: DHCP discovery for Epson TM and Rongta network printers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Network form prefill + profile preselect for discovery flows

**Files:**
- Modify: `custom_components/escpos_printer/_config_flow/network_steps.py` (form-building tail of `async_step_network`, lines 101-115)
- Test: `tests/test_config_flow_dhcp.py` (extend; remove Task 5's xfail)

**Interfaces:**
- Consumes: `self._discovery_host`, `self._detected` (Tasks 2/5), `suggest_profile(product, vid, pid) -> str | None` from `..capabilities.suggestions` (existing).
- Produces: no new interface — discovery-initiated network forms open with host suggested and profile default preselected.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config_flow_dhcp.py`: remove the `xfail` marker from `test_dhcp_discovery_shows_network_form` (if applied), and append:

```python
async def test_dhcp_discovery_preselects_suggested_profile(hass):
    with patch(
        "custom_components.escpos_printer._config_flow.network_steps.suggest_profile",
        return_value="TM-T20II",
    ):
        result = await _start_dhcp_flow(hass, query_result={"model": "TM-T20II"})
    assert result["step_id"] == "network"
    defaults = result["data_schema"]({"host": "192.168.10.157"})
    assert defaults["profile"] == "TM-T20II"


async def test_dhcp_discovery_unknown_model_keeps_auto_profile(hass):
    from custom_components.escpos_printer.capabilities import PROFILE_AUTO

    result = await _start_dhcp_flow(hass, query_result={"model": "Mystery-9000"})
    defaults = result["data_schema"]({"host": "192.168.10.157"})
    assert defaults["profile"] == PROFILE_AUTO
```

(`suggest_profile` must be importable from `network_steps`' namespace — Step 3 imports it there. The second test uses the real `suggest_profile`, which returns no match for "Mystery-9000".)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_flow_dhcp.py -v`
Expected: new tests FAIL (`suggest_profile` not in `network_steps`, profile default is `PROFILE_AUTO`, host not prefilled)

- [ ] **Step 3: Implement**

In `custom_components/escpos_printer/_config_flow/network_steps.py`:

1. Add import: `from ..capabilities.suggestions import suggest_profile`
2. Declare the mixin-expected attribute under `_user_data` (line 47): `_discovery_host: str | None`
3. Replace the form-building tail (lines 101-115) with:

```python
        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        # Discovery flows ran the GS I query before this form is shown, so
        # the detected model can preselect the profile dropdown (preselect
        # only -- the user always confirms). Manual flows query on submit.
        default_profile = PROFILE_AUTO
        detected_model = self._detected.get("model") if self._discovery_host else None
        if detected_model:
            suggestion = await self.hass.async_add_executor_job(
                suggest_profile, detected_model, None, None
            )
            if suggestion and suggestion in profile_choices:
                default_profile = suggestion

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=default_profile): vol.In(profile_choices),
            }
        )
        if self._discovery_host:
            data_schema = self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                data_schema, {CONF_HOST: self._discovery_host}
            )

        return self.async_show_form(step_id="network", data_schema=data_schema, errors=errors)  # type: ignore[attr-defined,no-any-return]
```

Note: `add_suggested_values_to_schema` sets the form's suggested value; adjust Task 5's `test_dhcp_discovery_shows_network_form` host assertion to read the suggested value from the schema marker if `schema({})` doesn't materialize it:

```python
    host_marker = next(k for k in result["data_schema"].schema if k.schema == "host")
    assert host_marker.description["suggested_value"] == "192.168.10.157"
```

4. Also declare `_detected: dict[str, str]` in the mixin-expected attributes if Task 2 didn't already.

- [ ] **Step 4: Run the dhcp + network flow tests**

Run: `uv run pytest tests/test_config_flow_dhcp.py tests/test_config_flow.py -q`
Expected: all PASS (manual-flow tests unaffected: `_discovery_host` is None there, so default stays `PROFILE_AUTO` and no suggested host is injected)

- [ ] **Step 5: Lint, type-check, commit**

Run: `uv run ruff check . && uv run mypy custom_components/`

```bash
git add custom_components/escpos_printer/_config_flow/network_steps.py tests/test_config_flow_dhcp.py
git commit -m "feat: discovery prefills host and preselects suggested profile

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Docs — CHANGELOG and README

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]` section — file has uncommitted user edits; append without touching existing hunks, commit only if the staged diff contains only these lines, otherwise report)
- Modify: `README.md` (add a short "Discovery" subsection near the existing setup/connection docs)

**Interfaces:** none.

- [ ] **Step 1: CHANGELOG entries**

Under `## [Unreleased]` → `### Added` (create the subsection if absent, matching the file's existing style):

```markdown
- Network printers are identified at setup via ESC/POS `GS I` queries: the
  device page shows the real manufacturer/model (e.g. EPSON TM-T20II), and
  the calibration share link prefills the model name. Printers that don't
  answer (most clones) behave exactly as before.
- DHCP discovery for network thermal printers: Home Assistant now offers to
  set up Epson TM-series (`tm-*`) and Rongta (`rongta_*`) printers it sees
  join the network. Candidates are probed on port 9100 first, so matches
  that aren't printers are ignored silently. Discovered setups preselect
  the matching printer profile when one is known.
```

- [ ] **Step 2: README "Discovery" note**

Locate the network setup section (`grep -n "Network" README.md | head`) and add beneath it:

```markdown
### Automatic discovery

Epson TM-series and Rongta network printers announce recognizable DHCP
hostnames; Home Assistant will offer to set them up automatically when they
appear on your network (Settings → Devices & Services → Discovered). Other
brands and printers with hostname broadcasting disabled can always be added
manually by IP address. During setup, the integration asks the printer to
identify itself (ESC/POS `GS I`); Epson printers answer with their real
model name, which fills the device page and suggests the matching profile.
Printers that don't answer are configured exactly as before.
```

Adjust heading level/placement to match the README's existing structure.

- [ ] **Step 3: Verify docs and commit**

Run: `git diff --cached` after staging to confirm ONLY the new lines are included (CHANGELOG.md and ROADMAP.md carry unrelated uncommitted user edits — if the user's hunks can't be separated with a plain `git add`, stop and report rather than committing them).

```bash
git add README.md
git add CHANGELOG.md   # only if the diff check above confirmed separability; otherwise report
git commit -m "docs: changelog and README for GS I identification and DHCP discovery

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Full verification sweep**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy custom_components/`
Expected: all green. Report the final output verbatim.
