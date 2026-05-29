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

from pathlib import Path

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


def test_print_image_path_schema_auto_resize_default_is_false():
    """Local files are almost always already-sized; auto_resize defaults to false.

    The 40 MB / thumbnail path that helps phone-JPEG and camera-snapshot
    callers adds latency without a payoff for local files. services.yaml
    pre-fills ``auto_resize: false`` for the path service; the schema must
    agree so a programmatic call without the key produces the same shape
    as the UI form.
    """
    from custom_components.escpos_printer.services.schemas import (
        PRINT_IMAGE_PATH_SCHEMA,
    )

    out = PRINT_IMAGE_PATH_SCHEMA({"path": "/config/www/logo.png"})
    assert out["auto_resize"] is False


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
)

# Fields that every image service must expose with identical UI metadata.
# `image_width` / `cut` / `feed` are excluded because their YAML defaults
# legitimately vary per service. `rotation`, `dither`, etc. carry their
# own defaults but should be uniform.
_PARITY_FIELDS = (
    "rotation",
    "dither",
    "threshold",
    "mirror",
    "invert",
    "autocontrast",
    "align",
    "center",
    "high_density",
    "impl",
    "fragment_height",
    "chunk_delay_ms",
    "fallback_image",
)

# Fields whose default *may* differ between services (documented per-service
# UX choice). Listed explicitly so the parity test stays loud about any
# *unintended* drift on other fields.
_DEFAULT_MAY_VARY = frozenset({"auto_resize", "autocontrast", "feed"})


def _load_services_yaml() -> dict:
    services_yaml = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "escpos_printer"
        / "services.yaml"
    )
    return load_yaml_dict(str(services_yaml))


def test_image_services_share_common_field_metadata() -> None:
    """All focused image services must expose the same field metadata as print_image."""
    services = _load_services_yaml()
    canonical = services["print_image"]["fields"]
    mismatches: list[str] = []
    for svc in _FOCUSED_IMAGE_SERVICES:
        svc_fields = services[svc]["fields"]
        for f in _PARITY_FIELDS:
            if f not in svc_fields:
                mismatches.append(f"{svc}.{f} missing entirely")
                continue
            for attr in ("name", "description", "selector"):
                expected = canonical[f].get(attr)
                actual = svc_fields[f].get(attr)
                if expected != actual:
                    mismatches.append(
                        f"{svc}.{f}.{attr} mismatch:\n"
                        f"  expected: {expected!r}\n"
                        f"  actual:   {actual!r}"
                    )
            # Defaults: must match canonical *unless* listed in _DEFAULT_MAY_VARY.
            if f not in _DEFAULT_MAY_VARY:
                expected_default = canonical[f].get("default")
                actual_default = svc_fields[f].get("default")
                if expected_default != actual_default:
                    mismatches.append(
                        f"{svc}.{f}.default mismatch (not in _DEFAULT_MAY_VARY):\n"
                        f"  expected: {expected_default!r}\n"
                        f"  actual:   {actual_default!r}"
                    )
    assert not mismatches, "services.yaml image-service field parity drift:\n  " + "\n  ".join(
        mismatches
    )


def test_image_services_no_truncated_descriptions() -> None:
    """Regression guard for unquoted YAML descriptions containing `#`."""
    services = _load_services_yaml()
    for svc in ("print_image", *_FOCUSED_IMAGE_SERVICES):
        for fname, fdef in services[svc]["fields"].items():
            desc = fdef.get("description")
            if desc is None:
                continue
            # Description should end with sentence-terminating punctuation
            # or be a single short phrase. The bug we're guarding against
            # left tooltips ending mid-word (e.g. ending in "(issue").
            assert isinstance(desc, str), f"{svc}.{fname} description not a string"
            assert desc.strip(), f"{svc}.{fname} description is empty"
            stripped = desc.rstrip().rstrip("\n")
            assert stripped[-1] in ".)>!?\"'", (
                f"{svc}.{fname} description appears truncated; ends with: {stripped[-30:]!r}"
            )
