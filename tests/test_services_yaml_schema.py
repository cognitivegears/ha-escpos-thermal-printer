from pathlib import Path

from homeassistant.helpers.service import _SERVICES_SCHEMA
from homeassistant.util.yaml import load_yaml_dict


def test_services_yaml_validates_against_homeassistant_schema() -> None:
    """Ensure integration service metadata stays valid for HA action forms."""
    services_yaml = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "escpos_printer"
        / "services.yaml"
    )

    services = load_yaml_dict(str(services_yaml))
    _SERVICES_SCHEMA(services)
