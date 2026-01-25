"""Tests for config entry migration to version 3."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.escpos_printer import async_migrate_entry
from custom_components.escpos_printer.const import (
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONNECTION_TYPE_NETWORK,
)


class TestMigrationV2ToV3:
    """Tests for migration from version 2 to version 3."""

    @pytest.mark.asyncio
    async def test_migration_adds_connection_type(self, hass):
        """Test that migration adds connection_type to existing entries."""
        # Create a mock v2 config entry (network printer without connection_type)
        mock_entry = MagicMock()
        mock_entry.version = 2
        mock_entry.entry_id = "test_entry_123"
        mock_entry.data = {
            "host": "192.168.1.100",
            "port": 9100,
            "timeout": 4.0,
            CONF_PROFILE: "",
            CONF_CODEPAGE: "CP437",
            CONF_LINE_WIDTH: 48,
            CONF_DEFAULT_ALIGN: "left",
            CONF_DEFAULT_CUT: "none",
        }

        updated_data = None

        def capture_update(entry, *, data, version, minor_version):
            nonlocal updated_data
            updated_data = data

        with patch.object(
            hass.config_entries, "async_update_entry", side_effect=capture_update
        ):
            result = await async_migrate_entry(hass, mock_entry)

        assert result is True
        assert updated_data is not None
        assert updated_data.get(CONF_CONNECTION_TYPE) == CONNECTION_TYPE_NETWORK

    @pytest.mark.asyncio
    async def test_migration_preserves_existing_data(self, hass):
        """Test that migration preserves all existing data."""
        mock_entry = MagicMock()
        mock_entry.version = 2
        mock_entry.entry_id = "test_entry_456"
        mock_entry.data = {
            "host": "10.0.0.50",
            "port": 9200,
            "timeout": 5.0,
            CONF_PROFILE: "TM-T88V",
            CONF_CODEPAGE: "CP932",
            CONF_LINE_WIDTH: 42,
            CONF_DEFAULT_ALIGN: "center",
            CONF_DEFAULT_CUT: "full",
        }

        updated_data = None

        def capture_update(entry, *, data, version, minor_version):
            nonlocal updated_data
            updated_data = data

        with patch.object(
            hass.config_entries, "async_update_entry", side_effect=capture_update
        ):
            result = await async_migrate_entry(hass, mock_entry)

        assert result is True
        assert updated_data["host"] == "10.0.0.50"
        assert updated_data["port"] == 9200
        assert updated_data["timeout"] == 5.0
        assert updated_data[CONF_PROFILE] == "TM-T88V"
        assert updated_data[CONF_CODEPAGE] == "CP932"
        assert updated_data[CONF_LINE_WIDTH] == 42
        assert updated_data[CONF_DEFAULT_ALIGN] == "center"
        assert updated_data[CONF_DEFAULT_CUT] == "full"
        assert updated_data[CONF_CONNECTION_TYPE] == CONNECTION_TYPE_NETWORK


class TestMigrationV1ToV3:
    """Tests for migration from version 1 directly to version 3."""

    @pytest.mark.asyncio
    async def test_migration_v1_to_v3_adds_all_fields(self, hass):
        """Test that v1 to v3 migration adds connection_type and other fields."""
        mock_entry = MagicMock()
        mock_entry.version = 1
        mock_entry.entry_id = "test_entry_v1"
        mock_entry.data = {
            "host": "192.168.1.100",
            "port": 9100,
            "timeout": 4.0,
        }

        updates = []

        def capture_update(entry, *, data, version, minor_version):
            updates.append({"data": data, "version": version})
            # After v1->v2 migration, update mock to v2
            if version == 2:
                mock_entry.version = 2
                mock_entry.data = data

        with patch.object(
            hass.config_entries, "async_update_entry", side_effect=capture_update
        ):
            result = await async_migrate_entry(hass, mock_entry)

        assert result is True
        # Should have two updates: v1->v2 and v2->v3
        assert len(updates) == 2
        # Final data should have connection_type
        final_data = updates[-1]["data"]
        assert final_data.get(CONF_CONNECTION_TYPE) == CONNECTION_TYPE_NETWORK


class TestMigrationV3NoOp:
    """Tests for v3 entries (no migration needed)."""

    @pytest.mark.asyncio
    async def test_v3_entry_no_migration(self, hass):
        """Test that v3 entries don't trigger migration."""
        mock_entry = MagicMock()
        mock_entry.version = 3
        mock_entry.entry_id = "test_entry_v3"
        mock_entry.data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
            "host": "192.168.1.100",
            "port": 9100,
        }

        with patch.object(
            hass.config_entries, "async_update_entry"
        ) as mock_update:
            result = await async_migrate_entry(hass, mock_entry)

        assert result is True
        mock_update.assert_not_called()


class TestMigrationDoesNotOverwrite:
    """Tests that migration doesn't overwrite existing connection_type."""

    @pytest.mark.asyncio
    async def test_migration_does_not_overwrite_existing_connection_type(self, hass):
        """Test that migration uses setdefault and doesn't overwrite."""
        mock_entry = MagicMock()
        mock_entry.version = 2
        mock_entry.entry_id = "test_entry_with_type"
        # Simulate a v2 entry that somehow already has connection_type
        # (shouldn't happen, but good to test)
        mock_entry.data = {
            "host": "192.168.1.100",
            "port": 9100,
            CONF_CONNECTION_TYPE: "custom_type",  # Existing value
        }

        updated_data = None

        def capture_update(entry, *, data, version, minor_version):
            nonlocal updated_data
            updated_data = data

        with patch.object(
            hass.config_entries, "async_update_entry", side_effect=capture_update
        ):
            result = await async_migrate_entry(hass, mock_entry)

        assert result is True
        # setdefault should preserve existing value
        assert updated_data[CONF_CONNECTION_TYPE] == "custom_type"
