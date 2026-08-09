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
            candidates: list[str] = [
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
