"""Per-test reset for text-effects module-level state.

The renderers use module-level "warned once" flags so the CJK alignment
warning doesn't spam HA logs from every render call (Q-H2). Tests need
those flags reset between cases so the once-per-process behaviour is
observable on each individual test.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_wide_char_warning_flags():
    """Reset the per-renderer warned-once flags before and after each test."""
    from custom_components.escpos_printer.text_effects import box as _box
    from custom_components.escpos_printer.text_effects import table as _table

    _box._WARNED_WIDE_CHARS_BOX = False
    _table._WARNED_WIDE_CHARS_TABLE = False
    yield
    _box._WARNED_WIDE_CHARS_BOX = False
    _table._WARNED_WIDE_CHARS_TABLE = False
