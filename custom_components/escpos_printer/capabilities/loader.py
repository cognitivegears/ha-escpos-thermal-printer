"""Capabilities loader for ESC/POS printer database."""

from __future__ import annotations

from functools import lru_cache
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_capabilities() -> dict[str, Any]:
    """Load capabilities from python-escpos (cached).

    Returns:
        Dictionary containing 'profiles' and 'encodings' data.
        Falls back to minimal capabilities if python-escpos unavailable.
    """
    try:
        from escpos.capabilities import CAPABILITIES  # noqa: PLC0415

        return CAPABILITIES  # type: ignore[no-any-return]  # noqa: TRY300
    except ImportError:
        _LOGGER.warning("python-escpos capabilities not available, using fallback")
        return _get_fallback_capabilities()
    except Exception as e:
        _LOGGER.warning("Failed to load escpos capabilities: %s", e)
        return _get_fallback_capabilities()


def _get_fallback_capabilities() -> dict[str, Any]:
    """Return fallback capabilities when python-escpos is unavailable.

    Returns:
        Minimal capabilities dict with common profiles and encodings.
    """
    return {
        "profiles": {
            "default": {
                "name": "Default",
                "vendor": "Generic",
                "codePages": {"0": "CP437"},
                "fonts": {"0": {"name": "Font A", "columns": 48}},
                "features": {
                    "paperFullCut": True,
                    "paperPartCut": True,
                },
            }
        },
        "encodings": {
            "CP437": {"name": "CP437", "python_encode": "cp437"},
            "CP850": {"name": "CP850", "python_encode": "cp850"},
            "CP852": {"name": "CP852", "python_encode": "cp852"},
            "CP858": {"name": "CP858", "python_encode": "cp858"},
            "CP1252": {"name": "CP1252", "python_encode": "cp1252"},
            "ISO_8859-1": {"name": "ISO_8859-1", "python_encode": "iso-8859-1"},
        },
    }


def clear_capabilities_cache() -> None:
    """Clear the capabilities cache.

    Useful for testing or when capabilities file changes.
    """
    _get_capabilities.cache_clear()
