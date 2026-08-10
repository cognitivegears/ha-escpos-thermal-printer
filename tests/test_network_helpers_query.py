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
            raise TimeoutError("timed out")
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
