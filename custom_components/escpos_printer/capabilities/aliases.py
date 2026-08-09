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
