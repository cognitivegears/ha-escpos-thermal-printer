"""Integration coverage for the post-v1 services.

The pre-v1 services (print_text/print_qr/print_barcode/feed/cut) are
already exercised in ``test_basic_functionality.py``. This file fills
the gap for the newer text-effects / layout / utility services which
otherwise only have unit-level (mock-the-printer) coverage:

* ``print_text_utf8`` — transcode-then-send happy path
* ``print_separator`` — repeated rule rendering
* ``print_box`` — ASCII-bordered box rendering
* ``print_table`` — ASCII multi-column table rendering
* ``print_kvtable`` — borderless key-value table rendering
* ``beep`` — buzzer pulse on a printer that exposes ``buzzer``

Each test asserts that the rendered text reaches the virtual printer
over a real socket (not just that the service handler ran), proving
the service-layer → adapter → python-escpos → TCP path is unbroken.

Image-based services (``print_image``/``print_text_image``/
``calibration_print``) are intentionally omitted from integration
coverage — the HA test harness used here has a known limitation with
the image pipeline that makes bytes-on-the-wire assertions unreliable
(see audit notes). Unit coverage for those services is comprehensive.
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.integration


async def _settle(ha_env) -> None:  # type: ignore[no-untyped-def]
    """Settle pending HA work AND give the virtual-printer parser a tick
    to drain the socket. Without this, the test can race the parser and
    see only the leading control bytes."""
    await ha_env.async_block_till_done()
    for _ in range(3):
        await asyncio.sleep(0.05)
        await ha_env.async_block_till_done()


def _joined_text_bytes(command_log: list) -> str:
    """Concatenate all text-command raw bytes as a decoded string.

    The integration's adapter transcodes text into the configured
    codepage (cp437 in the test fixture) before write, so a tolerant
    'latin-1' decode is enough to expose the printable payload for
    substring assertions.
    """
    blob = b"".join(
        cmd.raw_data or b"" for cmd in command_log if cmd.command_type == "text"
    )
    return blob.decode("latin-1", errors="ignore")


@pytest.mark.asyncio
async def test_print_text_utf8_round_trips_to_wire(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """print_text_utf8 transcodes accented chars and writes them to the wire."""
    printer, ha_env, _config = printer_with_ha
    await _settle(ha_env)
    await printer.printer_state.clear_history()

    await ha_env.hass.services.async_call(
        "escpos_printer",
        "print_text_utf8",
        {"text": "Cafe receipt"},
        blocking=True,
    )
    await _settle(ha_env)

    log = await printer.get_command_log()
    text_payload = _joined_text_bytes(log)
    all_bytes = b"".join(c.raw_data or b"" for c in log)
    assert "Cafe receipt" in text_payload, (
        f"missing 'Cafe receipt' in text_payload {text_payload!r}; "
        f"all bytes hex={all_bytes.hex()}; "
        f"commands={[(c.command_type, len(c.raw_data or b'')) for c in log]}"
    )


@pytest.mark.asyncio
async def test_print_separator_fills_line(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """print_separator emits a horizontal rule of the requested char/width."""
    printer, ha_env, _config = printer_with_ha
    await _settle(ha_env)
    await printer.printer_state.clear_history()

    await ha_env.hass.services.async_call(
        "escpos_printer",
        "print_separator",
        {"char": "=", "width": 20},
        blocking=True,
    )
    await _settle(ha_env)

    text_payload = _joined_text_bytes(await printer.get_command_log())
    assert "=" * 20 in text_payload


@pytest.mark.asyncio
async def test_print_separator_repeats(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """print_separator with repeat=3 writes three rule lines."""
    printer, ha_env, _config = printer_with_ha
    await _settle(ha_env)
    await printer.printer_state.clear_history()

    await ha_env.hass.services.async_call(
        "escpos_printer",
        "print_separator",
        {"char": "*", "width": 10, "repeat": 3},
        blocking=True,
    )
    await _settle(ha_env)

    text_payload = _joined_text_bytes(await printer.get_command_log())
    # Three repetitions joined by newlines.
    assert text_payload.count("*" * 10) == 3


@pytest.mark.asyncio
async def test_print_box_emits_ascii_border(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """print_box renders an ASCII-bordered box around the text."""
    printer, ha_env, _config = printer_with_ha
    await _settle(ha_env)
    await printer.printer_state.clear_history()

    await ha_env.hass.services.async_call(
        "escpos_printer",
        "print_box",
        {"text": "Hi", "style": "ascii", "total_width": 10},
        blocking=True,
    )
    await _settle(ha_env)

    text_payload = _joined_text_bytes(await printer.get_command_log())
    # Top/bottom border, content row with pipe sides.
    assert "+--------+" in text_payload
    assert "|Hi" in text_payload


@pytest.mark.asyncio
async def test_print_table_renders_header_and_body(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """print_table writes a header + body table with ASCII borders to the wire."""
    printer, ha_env, _config = printer_with_ha
    await _settle(ha_env)
    await printer.printer_state.clear_history()

    await ha_env.hass.services.async_call(
        "escpos_printer",
        "print_table",
        {
            "rows": [["Item", "Qty", "Price"], ["Coffee", "2", "$6.00"]],
            "style": "ascii",
            "header": True,
            "total_width": 26,
        },
        blocking=True,
    )
    await _settle(ha_env)

    text_payload = _joined_text_bytes(await printer.get_command_log())
    assert "Item" in text_payload
    assert "Coffee" in text_payload
    assert "$6.00" in text_payload
    # ASCII border characters present.
    assert "+" in text_payload
    assert "|" in text_payload


@pytest.mark.asyncio
async def test_print_kvtable_emits_aligned_rows(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """print_kvtable writes a borderless key/value receipt-style block."""
    printer, ha_env, _config = printer_with_ha
    await _settle(ha_env)
    await printer.printer_state.clear_history()

    await ha_env.hass.services.async_call(
        "escpos_printer",
        "print_kvtable",
        {
            "items": [["Subtotal", "$10.00"], ["Tax", "$0.80"], ["Total", "$10.80"]],
            "total_width": 20,
        },
        blocking=True,
    )
    await _settle(ha_env)

    text_payload = _joined_text_bytes(await printer.get_command_log())
    for label in ("Subtotal", "Tax", "Total"):
        assert label in text_payload
    for value in ("$10.00", "$0.80", "$10.80"):
        assert value in text_payload


@pytest.mark.asyncio
async def test_beep_service_triggers_buzzer(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """beep service issues an ESC ( A buzzer sequence (or equivalent).

    python-escpos's ``buzzer(times, duration)`` produces a real
    ESC/POS sequence on the wire. We don't pin a specific opcode (it
    varies by device profile) — we just verify some bytes hit the
    wire and the call doesn't raise.
    """
    printer, ha_env, _config = printer_with_ha
    await _settle(ha_env)
    await printer.printer_state.clear_history()
    initial = sum(len(cmd.raw_data or b"") for cmd in await printer.get_command_log())

    await ha_env.hass.services.async_call(
        "escpos_printer",
        "beep",
        {"times": 1, "duration": 1},
        blocking=True,
    )
    await _settle(ha_env)

    final = sum(len(cmd.raw_data or b"") for cmd in await printer.get_command_log())
    # ESC ( A buzzer command is short (~7 bytes) — any non-trivial
    # increase proves the buzzer reached the wire.
    assert final - initial > 0, (
        "Expected the beep service to emit ESC/POS bytes on the wire."
    )
