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


_ALL_SERVICES = (
    SERVICE_PRINT_TEXT_UTF8,
    SERVICE_PRINT_TEXT,
    SERVICE_PRINT_QR,
    SERVICE_PRINT_IMAGE,
    SERVICE_PRINT_BARCODE,
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
        f"{service_name} registered with schema=None — Bronze action-setup "
        f"violation"
    )


# ---------------------------------------------------------------------------
# T-H4: schema-level reject tests for print_image.
# ---------------------------------------------------------------------------


def test_print_image_schema_rejects_unknown_field():  # type: ignore[no-untyped-def]
    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_SCHEMA(
            {"image": "/config/x.png", "totally_unknown_field": 1}
        )


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

    with pytest.raises(vol.Invalid):
        PRINT_IMAGE_URL_SCHEMA({"url": "x" * 2001})


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
