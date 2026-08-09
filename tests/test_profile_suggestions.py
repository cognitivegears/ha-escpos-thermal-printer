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
