"""Schema + services.yaml tests.

Covers:

- The integration's ``services.yaml`` validates against HA's expected
  service-metadata schema (so action forms render correctly).
- Every action registered via :func:`async_setup_services` has a
  non-``None`` voluptuous schema (Bronze quality-scale ``action-setup``
  rule, Phase 4 BP-C1).
- ``print_image`` schema rejects unknown fields and oversized
  ``image`` strings at the service-registry layer (Phase 3 T-H4).
"""

from __future__ import annotations

import json
from pathlib import Path
import re

from homeassistant.helpers.service import _SERVICES_SCHEMA
from homeassistant.util.yaml import load_yaml_dict
import pytest
import voluptuous as vol

from custom_components.escpos_printer.const import (
    DOMAIN,
    SERVICE_BEEP,
    SERVICE_CUT,
    SERVICE_FEED,
    SERVICE_PRINT_BARCODE,
    SERVICE_PRINT_IMAGE,
    SERVICE_PRINT_IMAGE_PATH,
    SERVICE_PRINT_QR,
    SERVICE_PRINT_TEXT,
    SERVICE_PRINT_TEXT_UTF8,
)
from custom_components.escpos_printer.services.schemas import PRINT_IMAGE_SCHEMA


def test_services_yaml_validates_against_homeassistant_schema() -> None:
    """Integration service metadata stays valid for HA action forms."""
    services_yaml = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "escpos_printer"
        / "services.yaml"
    )

    services = load_yaml_dict(str(services_yaml))
    _SERVICES_SCHEMA(services)


# ---------------------------------------------------------------------------
# BP-C1: every registered service has a real schema.
# ---------------------------------------------------------------------------


from custom_components.escpos_printer.const import (
    SERVICE_PRINT_BOX,
    SERVICE_PRINT_TABLE,
    SERVICE_PRINT_TEXT_IMAGE,
)

_ALL_SERVICES = (
    SERVICE_PRINT_TEXT_UTF8,
    SERVICE_PRINT_TEXT,
    SERVICE_PRINT_QR,
    SERVICE_PRINT_IMAGE,
    SERVICE_PRINT_IMAGE_PATH,
    SERVICE_PRINT_BARCODE,
    SERVICE_PRINT_BOX,
    SERVICE_PRINT_TABLE,
    SERVICE_PRINT_TEXT_IMAGE,
    SERVICE_FEED,
    SERVICE_CUT,
    SERVICE_BEEP,
)


@pytest.mark.parametrize("service_name", _ALL_SERVICES)
async def test_every_service_has_schema(hass, service_name):  # type: ignore[no-untyped-def]
    """After setup, every action's `Service.schema` is non-None."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={"host": "1.2.3.4", "port": 9100},
        unique_id="1.2.3.4:9100",
        version=3,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    services = hass.services.async_services_for_domain(DOMAIN)
    svc = services[service_name]
    assert svc.schema is not None, (
        f"{service_name} registered with schema=None — Bronze action-setup violation"
    )


# ---------------------------------------------------------------------------
# T-H4: schema-level reject tests for print_image.
# ---------------------------------------------------------------------------


def test_print_image_schema_rejects_unknown_field():  # type: ignore[no-untyped-def]
    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_SCHEMA({"image": "/config/x.png", "totally_unknown_field": 1})


def test_print_image_schema_rejects_out_of_range_width():  # type: ignore[no-untyped-def]
    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_SCHEMA({"image": "/config/x.png", "image_width": 99999})


def test_print_image_schema_rejects_invalid_dither():  # type: ignore[no-untyped-def]
    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_SCHEMA({"image": "/config/x.png", "dither": "ordered"})


def test_print_image_schema_rejects_oversized_image_string():  # type: ignore[no-untyped-def]
    huge = "data:image/png;base64," + "A" * (200 * 1024 * 1024)
    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_SCHEMA({"image": huge})


def test_print_image_schema_applies_defaults():  # type: ignore[no-untyped-def]
    out = PRINT_IMAGE_SCHEMA({"image": "/config/x.png"})
    assert out["rotation"] == 0
    assert out["dither"] == "floyd-steinberg"
    assert out["threshold"] == 128
    assert out["center"] is False
    assert out["autocontrast"] is False
    assert out["invert"] is False
    assert out["mirror"] is False
    assert out["auto_resize"] is False
    assert out["high_density"] is True
    # impl, fragment_height, chunk_delay_ms intentionally have no schema-
    # level default so the per-printer reliability profile (and the
    # transport's per-chunk delay) can decide.
    assert "impl" not in out
    assert "fragment_height" not in out
    assert "chunk_delay_ms" not in out


def test_print_camera_snapshot_schema_requires_camera_entity():  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import (
        PRINT_CAMERA_SNAPSHOT_SCHEMA,
    )

    with pytest.raises(vol.Invalid):
        PRINT_CAMERA_SNAPSHOT_SCHEMA({})
    out = PRINT_CAMERA_SNAPSHOT_SCHEMA({"camera_entity": "camera.front_door"})
    assert out["camera_entity"] == "camera.front_door"


def test_print_camera_snapshot_schema_rejects_wrong_domain():  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import (
        PRINT_CAMERA_SNAPSHOT_SCHEMA,
    )

    with pytest.raises(vol.Invalid):
        PRINT_CAMERA_SNAPSHOT_SCHEMA({"camera_entity": "image.foo"})


def test_print_image_url_schema_caps_length():  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_URL_SCHEMA,
    )

    long_url = "https://example.com/" + "x" * 2001
    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_URL_SCHEMA({"url": long_url})


def test_print_image_url_schema_rejects_non_url():
    """The URL service must refuse paths / entities so the contract is enforced at the schema."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_URL_SCHEMA,
    )

    for bad in (
        "/config/www/logo.png",
        "camera.front_door",
        "image.weather_radar",
        "data:image/png;base64,iVBOR...",
        "ftp://example.com/x.png",
    ):
        with pytest.raises(vol.Invalid):
            PRINT_IMAGE_URL_SCHEMA({"url": bad})


def test_print_image_url_schema_auto_resize_default_is_true():
    """The UI form pre-fills ``auto_resize: true`` for the URL service; the schema must agree."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_URL_SCHEMA,
    )

    out = PRINT_IMAGE_URL_SCHEMA({"url": "https://example.com/x.png"})
    assert out["auto_resize"] is True


def test_print_image_path_schema_requires_path():  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_PATH_SCHEMA,
    )

    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_PATH_SCHEMA({})
    out = PRINT_IMAGE_PATH_SCHEMA({"path": "/config/www/logo.png"})
    assert out["path"] == "/config/www/logo.png"


def test_print_image_path_schema_caps_length():  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_PATH_SCHEMA,
    )

    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_PATH_SCHEMA({"path": "/" + "x" * 1025})


def test_print_image_path_schema_rejects_non_path():
    """The path service must refuse URLs / entities so the contract is enforced at the schema."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_PATH_SCHEMA,
    )

    for bad in (
        "https://example.com/x.png",
        "http://example.com/x.png",
        "camera.front_door",
        "image.weather_radar",
        "data:image/png;base64,iVBOR...",
    ):
        with pytest.raises(vol.Invalid):
            PRINT_IMAGE_PATH_SCHEMA({"path": bad})


def test_print_image_path_schema_auto_resize_default_is_true():
    """The UI form pre-fills ``auto_resize: true`` for the path service; the schema must agree."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_PATH_SCHEMA,
    )

    out = PRINT_IMAGE_PATH_SCHEMA({"path": "/config/www/logo.png"})
    assert out["auto_resize"] is True


def test_print_image_path_schema_strips_and_rejects_whitespace_prefixed_entity():
    """A leading-space value must be checked/rejected using the same shape ``_classify`` will see.

    ``_classify()`` strips the source before classifying it, so
    ``" camera.front_door"`` (leading space) is really a camera entity —
    the path-only schema must reject it, not silently accept it as an
    unmatched (non-URL, non-entity-looking) local path because it only
    checked the un-stripped string.
    """
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_PATH_SCHEMA,
    )

    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_PATH_SCHEMA({"path": " camera.front_door"})


def test_print_image_path_schema_strips_leading_whitespace_from_local_path():
    """A leading-space local path is still a local path once stripped; the schema accepts it."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_PATH_SCHEMA,
    )

    out = PRINT_IMAGE_PATH_SCHEMA({"path": " /config/www/x.png"})
    assert out["path"] == "/config/www/x.png"


def test_print_image_url_schema_strips_and_rejects_whitespace_prefixed_path():
    """A leading-space local-path value must be rejected by the URL-only schema."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_URL_SCHEMA,
    )

    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_URL_SCHEMA({"url": " /config/www/x.png"})


def test_print_image_url_schema_strips_leading_whitespace_from_url():
    """A leading-space URL is still a URL once stripped; the schema accepts it."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_URL_SCHEMA,
    )

    out = PRINT_IMAGE_URL_SCHEMA({"url": " http://example.com/x.png"})
    assert out["url"] == "http://example.com/x.png"


def test_print_camera_snapshot_schema_defaults_match_ui():
    """services.yaml prefills autocontrast=true and auto_resize=true; the schema must agree."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_CAMERA_SNAPSHOT_SCHEMA,
    )

    out = PRINT_CAMERA_SNAPSHOT_SCHEMA({"camera_entity": "camera.front_door"})
    assert out["autocontrast"] is True
    assert out["auto_resize"] is True


def test_print_image_entity_schema_defaults_match_print_image():
    """The image-entity service uses the conservative (no opt-in) defaults like print_image."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_ENTITY_SCHEMA,
    )

    out = PRINT_IMAGE_ENTITY_SCHEMA({"image_entity": "image.weather_radar"})
    assert out["autocontrast"] is False
    assert out["auto_resize"] is False


def test_print_image_path_schema_accepts_image_options():  # type: ignore[no-untyped-def]
    """All image options (rotation, mirror, threshold, impl, etc) must validate on the new service."""
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_PATH_SCHEMA,
    )

    out = PRINT_IMAGE_PATH_SCHEMA(
        {
            "path": "/config/www/logo.png",
            "rotation": 90,
            "mirror": True,
            "invert": True,
            "threshold": 200,
            "dither": "threshold",
            "impl": "graphics",
            "fragment_height": 256,
            "chunk_delay_ms": 50,
        }
    )
    assert out["rotation"] == 90
    assert out["mirror"] is True
    assert out["impl"] == "graphics"


def test_preview_image_schema_optional_output_path():  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import (
        PREVIEW_IMAGE_SCHEMA,
    )

    out = PREVIEW_IMAGE_SCHEMA({"image": "/config/x.png"})
    assert "output_path" not in out
    out2 = PREVIEW_IMAGE_SCHEMA(
        {"image": "/config/x.png", "output_path": "/tmp/p.png"}  # noqa: S108
    )
    assert out2["output_path"] == "/tmp/p.png"  # noqa: S108


# ---------------------------------------------------------------------------
# Target-picker keys (entity_id/area_id/floor_id/label_id): HA core merges
# these into call.data when a service declares `target:`. The schemas must
# accept them (str or [str]) and keep them mutually exclusive with
# broadcast, same as device_id.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["entity_id", "area_id", "floor_id", "label_id"])
@pytest.mark.parametrize("shape", ["single", "list"])
def test_print_text_schema_accepts_target_picker_keys(key, shape):  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import PRINT_TEXT_SCHEMA

    value = "abc123" if shape == "single" else ["abc123", "def456"]
    out = PRINT_TEXT_SCHEMA({"text": "hi", key: value})
    assert out[key] == value


@pytest.mark.parametrize("key", ["entity_id", "area_id"])
def test_print_text_schema_rejects_broadcast_with_target_key(key):  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import PRINT_TEXT_SCHEMA

    with pytest.raises(vol.Invalid):
        PRINT_TEXT_SCHEMA({"text": "hi", "broadcast": True, key: "abc123"})


def test_calibration_print_schema_defaults():  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services.schemas import (
        CALIBRATION_PRINT_SCHEMA,
    )

    out = CALIBRATION_PRINT_SCHEMA({})
    assert out["cut"] == "full"
    assert out["feed"] == 2


def test_print_text_image_schema_rejects_fallback_image():  # type: ignore[no-untyped-def]
    """Phase 2 S-M4 regression — ``print_text_image`` must NOT inherit
    the ``fallback_image`` field from ``_image_option_fragment``.

    The service produces its own image bytes, so a source-shaped
    fallback is meaningless. Accepting it would silently broaden the
    parity invariant documented in CLAUDE.md and re-introduce an SSRF-
    adjacent attack surface (the underlying field is template-typed).
    """
    from custom_components.escpos_printer.services.schemas import (
        PRINT_TEXT_IMAGE_SCHEMA,
    )

    with pytest.raises(vol.Invalid, match="extra keys not allowed"):
        PRINT_TEXT_IMAGE_SCHEMA(
            {
                "text": "hi",
                "fallback_image": "http://attacker.example/probe",
            }
        )


# ---------------------------------------------------------------------------
# services.yaml parity: every focused image service must declare the same
# common-field metadata (name / description / selector) as the canonical
# print_image service. Per-service `default:` is intentionally allowed to
# differ (e.g. `feed` and `auto_resize` vary across services), but the
# field shape and tooltip text must stay aligned. This test would have
# caught the YAML `#`-comment truncation bug across four services.
# ---------------------------------------------------------------------------


_FOCUSED_IMAGE_SERVICES = (
    "print_image_url",
    "print_image_path",
    "print_camera_snapshot",
    "print_image_entity",
    "preview_image",
)

# Fields that every image service must expose with identical UI metadata.
# `cut` is excluded because it's absent from the focused services' common
# fragment entirely. `rotation`, `dither`, etc. carry their own per-service
# defaults but should be uniform in name/description/selector.
_PARITY_FIELDS = (
    "rotation",
    "dither",
    "threshold",
    "mirror",
    "invert",
    "autocontrast",
    "align",
    "high_density",
    "impl",
    "fragment_height",
    "chunk_delay_ms",
    "fallback_image",
    "broadcast",
    "auto_resize",
    "feed",
    "image_width",
)

# Fields whose default *may* differ between services (documented per-service
# UX choice). Listed explicitly so the parity test stays loud about any
# *unintended* drift on other fields.
_DEFAULT_MAY_VARY = frozenset({"auto_resize", "autocontrast", "feed"})

# preview_image deliberately omits the printer-communication knobs
# (CLAUDE.md "Image services: field-set parity invariant") because they
# have no effect on the PNG written to disk — exempt from the "every
# _PARITY_FIELDS entry must exist" check rather than failing as missing.
_PARITY_EXEMPT_FIELDS: dict[str, frozenset[str]] = {
    "preview_image": frozenset(
        {"high_density", "impl", "fragment_height", "chunk_delay_ms", "broadcast", "feed"}
    ),
}


def _load_services_yaml() -> dict:
    services_yaml = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "escpos_printer"
        / "services.yaml"
    )
    return load_yaml_dict(str(services_yaml))


def _flatten_fields(svc_def: dict) -> dict[str, tuple[str | None, dict]]:
    """Flatten a service's ``fields`` map, resolving collapsed sections.

    A section is a fields-map entry that is itself a mapping containing a
    nested ``fields`` key (HA's collapsed-section syntax). Returns
    ``{field_name: (section_id_or_None, field_def)}`` so callers can check
    both a field's own metadata and which section (if any) it lives under.
    """
    flat: dict[str, tuple[str | None, dict]] = {}
    for name, fdef in (svc_def.get("fields") or {}).items():
        if isinstance(fdef, dict) and isinstance(fdef.get("fields"), dict):
            for child_name, child_def in fdef["fields"].items():
                flat[child_name] = (name, child_def)
        else:
            flat[name] = (None, fdef)
    return flat


def test_image_services_share_common_field_metadata() -> None:
    """All focused image services must expose the same field metadata as print_image."""
    services = _load_services_yaml()
    canonical_fields = services["print_image"]["fields"]
    canonical = _flatten_fields(services["print_image"])
    mismatches: list[str] = []
    for svc in _FOCUSED_IMAGE_SERVICES:
        svc_def = services[svc]
        svc_fields = _flatten_fields(svc_def)
        exempt = _PARITY_EXEMPT_FIELDS.get(svc, frozenset())
        for f in _PARITY_FIELDS:
            if f in exempt:
                continue
            if f not in svc_fields:
                mismatches.append(f"{svc}.{f} missing entirely")
                continue
            expected_section, expected_def = canonical[f]
            actual_section, actual_def = svc_fields[f]
            if expected_section != actual_section:
                mismatches.append(
                    f"{svc}.{f} section mismatch: expected {expected_section!r}, "
                    f"got {actual_section!r}"
                )
            for attr in ("name", "description", "selector"):
                expected = expected_def.get(attr)
                actual = actual_def.get(attr)
                if expected != actual:
                    mismatches.append(
                        f"{svc}.{f}.{attr} mismatch:\n"
                        f"  expected: {expected!r}\n"
                        f"  actual:   {actual!r}"
                    )
            # Defaults: must match canonical *unless* listed in _DEFAULT_MAY_VARY.
            if f not in _DEFAULT_MAY_VARY:
                expected_default = expected_def.get("default")
                actual_default = actual_def.get("default")
                if expected_default != actual_default:
                    mismatches.append(
                        f"{svc}.{f}.default mismatch (not in _DEFAULT_MAY_VARY):\n"
                        f"  expected: {expected_default!r}\n"
                        f"  actual:   {actual_default!r}"
                    )
        # Every section print_image declares must exist on this service with
        # identical name/description/collapsed.
        for section_id, section_def in canonical_fields.items():
            if not (isinstance(section_def, dict) and isinstance(section_def.get("fields"), dict)):
                continue
            actual_section_def = svc_def["fields"].get(section_id)
            if not isinstance(actual_section_def, dict):
                mismatches.append(f"{svc} missing section {section_id!r}")
                continue
            for attr in ("name", "description", "collapsed"):
                expected = section_def.get(attr)
                actual = actual_section_def.get(attr)
                if expected != actual:
                    mismatches.append(
                        f"{svc}.{section_id}.{attr} mismatch:\n"
                        f"  expected: {expected!r}\n"
                        f"  actual:   {actual!r}"
                    )
    assert not mismatches, "services.yaml image-service field parity drift:\n  " + "\n  ".join(
        mismatches
    )


def test_no_stale_raster_epson_only_label() -> None:
    """Raster works on most printers, not just Epson -- the presets-era label was stale."""
    services = _load_services_yaml()
    for svc, svc_def in services.items():
        for field_name, (_section, fdef) in _flatten_fields(svc_def).items():
            options = ((fdef.get("selector") or {}).get("select") or {}).get("options") or []
            for opt in options:
                if isinstance(opt, dict):
                    label = opt.get("label") or ""
                    assert "Raster" not in label or "Epson" not in label, (
                        f"{svc}.{field_name} still has an Epson-only-sounding Raster label: "
                        f"{label!r}"
                    )


def test_print_message_image_impl_description_matches_image_services_wording() -> None:
    """print_message.image_impl's description no longer references a Reliability profile."""
    services = _load_services_yaml()
    desc = services["print_message"]["fields"]["advanced_options"]["fields"]["image_impl"][
        "description"
    ]
    assert "Leave unset to follow the printer profile" in desc
    assert "Reliability profile" not in desc


def test_image_services_no_truncated_descriptions() -> None:
    """Regression guard for unquoted YAML descriptions containing `#`."""
    services = _load_services_yaml()
    for svc in ("print_image", *_FOCUSED_IMAGE_SERVICES):
        svc_def = services[svc]
        for fname, (_section, fdef) in _flatten_fields(svc_def).items():
            desc = fdef.get("description")
            if desc is not None:
                _assert_description_not_truncated(svc, fname, desc)
    # Sections carry their own tooltip description too — check them on every
    # service, not just the image family (print_barcode, print_message and
    # print_text_image have sections as well).
    for svc, svc_def in services.items():
        for field_name, field_def in svc_def.get("fields", {}).items():
            if isinstance(field_def, dict) and isinstance(field_def.get("fields"), dict):
                desc = field_def.get("description")
                if desc is not None:
                    _assert_description_not_truncated(svc, field_name, desc)


def test_no_icu_tag_like_angle_brackets_in_user_visible_strings() -> None:
    """Regression guard for 'Translation error: UNCLOSED_TAG' in the HA UI.

    The frontend parses translation strings as ICU messages, where ``<word``
    opens a rich-text tag; an unclosed one (e.g. ``camera.<id>`` or
    ``<config>/fonts/``) makes the whole description render as
    'Translation error: UNCLOSED_TAG'. Use ``[placeholder]`` instead.
    """
    root = Path(__file__).resolve().parents[1] / "custom_components" / "escpos_printer"
    tag_open = re.compile(r"<[A-Za-z/]")
    offenders = [
        f"{rel}:{lineno}: {line.strip()[:100]}"
        for rel in ("services.yaml", "strings.json", "translations/en.json")
        for lineno, line in enumerate(
            (root / rel).read_text(encoding="utf-8").splitlines(), start=1
        )
        if tag_open.search(line)
    ]
    assert not offenders, (
        "ICU-tag-like '<' in user-visible strings (frontend raises UNCLOSED_TAG):\n  "
        + "\n  ".join(offenders)
    )


def test_no_icu_invalid_braces_in_user_visible_strings() -> None:
    """Regression guard for 'Translation error: INVALID_ARGUMENT_TYPE'.

    The frontend parses translation strings as ICU messages, where ``{...}``
    is a placeholder. Literal brace text like ``{path, width, line_count}``
    parses as a placeholder with a bogus argument type and the whole string
    renders as 'Translation error: INVALID_ARGUMENT_TYPE'. Only simple
    ``{identifier}`` placeholders are allowed; spell out literal lists
    without braces.

    Also rejects an apostrophe directly before ``{`` or ``<``: ICU quoting
    rules turn ``'{value}'`` into the literal text ``{value}``, silently
    skipping placeholder substitution. Quote values with ``"`` instead.
    """
    root = Path(__file__).resolve().parents[1] / "custom_components" / "escpos_printer"
    simple_placeholder = re.compile(r"^\{[A-Za-z0-9_]+\}$")
    offenders: list[str] = []

    def check(value: object, where: str) -> None:
        if isinstance(value, str):
            offenders.extend(
                f"{where}: {match}"
                for match in re.findall(r"\{[^{}]*\}", value)
                if not simple_placeholder.match(match)
            )
            if value.count("{") != value.count("}"):
                offenders.append(f"{where}: unbalanced braces")
            if re.search(r"'[{<]", value):
                offenders.append(f"{where}: ICU apostrophe-escape before {{ or <")
        elif isinstance(value, dict):
            for key, sub in value.items():
                check(sub, f"{where}.{key}")
        elif isinstance(value, list):
            for index, sub in enumerate(value):
                check(sub, f"{where}[{index}]")

    check(_load_services_yaml(), "services.yaml")
    for rel in ("strings.json", "translations/en.json"):
        check(json.loads((root / rel).read_text(encoding="utf-8")), rel)

    assert not offenders, (
        "Non-{identifier} braces in user-visible strings "
        "(frontend raises INVALID_ARGUMENT_TYPE):\n  " + "\n  ".join(offenders)
    )


def test_no_unquoted_hash_in_plain_scalar_descriptions() -> None:
    """Regression guard for the YAML `#`-comment-truncation bug class,
    scanned across every service in services.yaml (not just the image
    family). An unquoted `#` in a plain-scalar ``description:`` value
    starts a YAML comment, silently dropping everything after it before
    PyYAML ever hands the value back — so this scans the raw text, not
    the parsed result.
    """
    root = Path(__file__).resolve().parents[1] / "custom_components" / "escpos_printer"
    lines = (root / "services.yaml").read_text(encoding="utf-8").splitlines()

    # A plain-scalar `description:` value: not quoted (`"`/`'`) and not a
    # block-scalar indicator (`>`/`|`).
    plain_scalar_desc = re.compile(r'^(\s*)description:\s+(?!["\'>|])(.*)$')
    offenders = [
        f"services.yaml:{lineno}: {line.strip()[:100]}"
        for lineno, line in enumerate(lines, start=1)
        if (match := plain_scalar_desc.match(line))
        # `#` preceded by whitespace (or leading the value) opens a
        # comment in a plain scalar.
        and re.search(r"(^|\s)#", match.group(2))
    ]
    assert not offenders, (
        "Unquoted '#' in a plain-scalar description silently truncates the "
        "value at YAML-parse time — quote the description or use a '>' "
        "folded scalar:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# target: block declaration (1.2.0) -- lets these services be offered from
# the entity/device "create as a new action" picker while keeping device_id
# fully supported for backward compatibility.
# ---------------------------------------------------------------------------

_TARGETED_SERVICES = frozenset(
    {
        "print_text_utf8",
        "print_text",
        "print_qr",
        "print_image",
        "print_image_url",
        "print_image_path",
        "print_camera_snapshot",
        "print_image_entity",
        "print_barcode",
        "print_box",
        "print_table",
        "print_text_image",
        "print_separator",
        "print_kvtable",
        "feed",
        "cut",
        "beep",
        "calibration_print",
    }
)

_UNTARGETED_WITH_DEVICE_ID = frozenset({"preview_image", "preview_box", "preview_table"})

_EXPECTED_TARGET_BLOCK = {
    "entity": {"domain": "notify", "integration": "escpos_printer"},
    "device": {"integration": "escpos_printer"},
}


def test_services_declare_target_and_drop_device_id_field() -> None:
    """The 18 automation-facing services declare `target:` and no longer
    duplicate device selection as a `device_id` field; the three preview_*
    services (SupportsResponse.ONLY) keep the old device_id field and stay
    target-less.
    """
    services = _load_services_yaml()
    assert _TARGETED_SERVICES | _UNTARGETED_WITH_DEVICE_ID | {"print_message"} <= set(services)
    for svc in _TARGETED_SERVICES:
        svc_def = services[svc]
        assert svc_def.get("target") == _EXPECTED_TARGET_BLOCK, (
            f"{svc}.target missing or wrong: {svc_def.get('target')!r}"
        )
        assert "device_id" not in svc_def.get("fields", {}), (
            f"{svc}.fields still declares device_id; the target picker replaces it"
        )
    for svc in _UNTARGETED_WITH_DEVICE_ID:
        svc_def = services[svc]
        assert "target" not in svc_def, f"{svc} unexpectedly declares target"
        assert "device_id" in svc_def.get("fields", {}), (
            f"{svc}.fields must keep device_id (not offered as an automation action)"
        )


def test_icons_json_services_match_services_yaml() -> None:
    """icons.json's service icon keys must exactly match services.yaml's
    registered services — no stale entries for removed/renamed services,
    no service missing an automation-picker icon.
    """
    services = _load_services_yaml()
    root = Path(__file__).resolve().parents[1] / "custom_components" / "escpos_printer"
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))
    assert set(icons["services"].keys()) == set(services.keys())


def _assert_description_not_truncated(svc: str, fname: str, desc: object) -> None:
    # Description should end with sentence-terminating punctuation or be a
    # single short phrase. The bug we're guarding against left tooltips
    # ending mid-word (e.g. ending in "(issue").
    assert isinstance(desc, str), f"{svc}.{fname} description not a string"
    assert desc.strip(), f"{svc}.{fname} description is empty"
    stripped = desc.rstrip().rstrip("\n")
    assert stripped[-1] in ".)>!?\"'", (
        f"{svc}.{fname} description appears truncated; ends with: {stripped[-30:]!r}"
    )
