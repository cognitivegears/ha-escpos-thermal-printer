"""Tests for the capabilities module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.escpos_printer.capabilities import (
    COMMON_CODEPAGES,
    COMMON_LINE_WIDTHS,
    DEFAULT_CUT_MODES,
    OPTION_CUSTOM,
    PROFILE_AUTO,
    PROFILE_CUSTOM,
    clear_capabilities_cache,
    get_all_codepages,
    get_all_line_widths,
    get_profile_choices,
    get_profile_choices_dict,
    get_profile_codepages,
    get_profile_cut_modes,
    get_profile_features,
    get_profile_info,
    get_profile_line_widths,
    is_valid_codepage_for_profile,
    is_valid_profile,
    profile_supports_feature,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear capabilities cache before each test."""
    clear_capabilities_cache()
    yield
    clear_capabilities_cache()


# =============================================================================
# Profile Choice Tests
# =============================================================================


class TestGetProfileChoices:
    """Tests for get_profile_choices function."""

    def test_returns_list_of_tuples(self):
        """Should return list of (key, display) tuples."""
        choices = get_profile_choices()
        assert isinstance(choices, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in choices)

    def test_auto_detect_first(self):
        """Auto-detect should be first option."""
        choices = get_profile_choices()
        assert len(choices) > 0
        assert choices[0] == (PROFILE_AUTO, "Auto-detect (Default)")

    def test_custom_option_last(self):
        """Custom option should be last."""
        choices = get_profile_choices()
        assert len(choices) > 1
        assert choices[-1] == (PROFILE_CUSTOM, "Custom (enter profile name)...")

    def test_includes_known_profiles(self):
        """Should include known profiles from escpos-printer-db."""
        choices = get_profile_choices()
        keys = [k for k, v in choices]

        # These profiles should exist in escpos-printer-db
        # At minimum, the fallback 'default' should exist
        assert PROFILE_AUTO in keys
        assert PROFILE_CUSTOM in keys

    def test_profiles_sorted_alphabetically(self):
        """Profile list (excluding Auto and Custom) should be sorted."""
        choices = get_profile_choices()
        # Extract middle portion (excluding first Auto and last Custom)
        middle = choices[1:-1]
        display_names = [v for k, v in middle]
        assert display_names == sorted(display_names, key=str.lower)


class TestGetProfileChoicesDict:
    """Tests for get_profile_choices_dict function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_profile_choices_dict()
        assert isinstance(result, dict)

    def test_contains_auto_and_custom(self):
        """Should contain auto and custom keys."""
        result = get_profile_choices_dict()
        assert PROFILE_AUTO in result
        assert PROFILE_CUSTOM in result


class TestIsValidProfile:
    """Tests for is_valid_profile function."""

    def test_empty_string_valid(self):
        """Empty string (auto) should be valid."""
        assert is_valid_profile("") is True
        assert is_valid_profile(PROFILE_AUTO) is True

    def test_none_valid(self):
        """None should be valid (treated as auto)."""
        assert is_valid_profile(None) is True

    def test_custom_marker_valid(self):
        """Custom marker should be valid."""
        assert is_valid_profile(PROFILE_CUSTOM) is True

    def test_unknown_profile_invalid(self):
        """Unknown profile should be invalid."""
        assert is_valid_profile("NONEXISTENT-PRINTER-XYZ") is False

    def test_default_profile_valid(self):
        """Default profile should be valid (from fallback)."""
        assert is_valid_profile("default") is True


# =============================================================================
# Codepage Tests
# =============================================================================


class TestGetProfileCodepages:
    """Tests for get_profile_codepages function."""

    def test_auto_returns_common_codepages(self):
        """Auto profile should return common codepages."""
        result = get_profile_codepages(PROFILE_AUTO)
        assert result == COMMON_CODEPAGES

    def test_empty_returns_common_codepages(self):
        """Empty profile should return common codepages."""
        result = get_profile_codepages("")
        assert result == COMMON_CODEPAGES

    def test_none_returns_common_codepages(self):
        """None profile should return common codepages."""
        result = get_profile_codepages(None)
        assert result == COMMON_CODEPAGES

    def test_custom_returns_all_codepages(self):
        """Custom profile should return all available codepages."""
        result = get_profile_codepages(PROFILE_CUSTOM)
        # Should return more than just common codepages (all available)
        assert len(result) >= len(COMMON_CODEPAGES)

    def test_unknown_profile_returns_common(self):
        """Unknown profile should return common codepages."""
        result = get_profile_codepages("NONEXISTENT-PRINTER-XYZ")
        assert result == COMMON_CODEPAGES

    def test_result_is_sorted(self):
        """Result should be sorted alphabetically."""
        result = get_profile_codepages(PROFILE_AUTO)
        assert result == sorted(result)

    def test_excludes_unknown_codepages(self):
        """Should not include 'Unknown' codepages."""
        result = get_profile_codepages(PROFILE_CUSTOM)
        assert "Unknown" not in result

    def test_default_profile_has_codepages(self):
        """Default fallback profile should have codepages."""
        result = get_profile_codepages("default")
        assert len(result) > 0
        assert "CP437" in result


class TestGetAllCodepages:
    """Tests for get_all_codepages function."""

    def test_returns_list(self):
        """Should return a list."""
        result = get_all_codepages()
        assert isinstance(result, list)

    def test_includes_common_codepages(self):
        """Should include common codepages."""
        result = get_all_codepages()
        for cp in COMMON_CODEPAGES:
            assert cp in result

    def test_result_is_sorted(self):
        """Result should be sorted."""
        result = get_all_codepages()
        assert result == sorted(result)


class TestIsValidCodepageForProfile:
    """Tests for is_valid_codepage_for_profile function."""

    def test_empty_codepage_always_valid(self):
        """Empty codepage should always be valid."""
        assert is_valid_codepage_for_profile("", "default") is True
        assert is_valid_codepage_for_profile(None, "default") is True

    def test_custom_marker_valid(self):
        """Custom marker should be valid."""
        assert is_valid_codepage_for_profile(OPTION_CUSTOM, "default") is True

    def test_common_codepage_valid_for_auto(self):
        """Common codepages should be valid for auto profile."""
        for cp in COMMON_CODEPAGES:
            assert is_valid_codepage_for_profile(cp, PROFILE_AUTO) is True

    def test_common_codepage_valid_for_any_profile(self):
        """Common codepages should be accepted as fallback."""
        for cp in COMMON_CODEPAGES:
            assert is_valid_codepage_for_profile(cp, "default") is True


# =============================================================================
# Line Width Tests
# =============================================================================


class TestGetProfileLineWidths:
    """Tests for get_profile_line_widths function."""

    def test_auto_returns_common_widths(self):
        """Auto profile should return common line widths."""
        result = get_profile_line_widths(PROFILE_AUTO)
        assert result == COMMON_LINE_WIDTHS

    def test_empty_returns_common_widths(self):
        """Empty profile should return common line widths."""
        result = get_profile_line_widths("")
        assert result == COMMON_LINE_WIDTHS

    def test_none_returns_common_widths(self):
        """None profile should return common line widths."""
        result = get_profile_line_widths(None)
        assert result == COMMON_LINE_WIDTHS

    def test_custom_returns_common_widths(self):
        """Custom profile should return common line widths."""
        result = get_profile_line_widths(PROFILE_CUSTOM)
        assert result == COMMON_LINE_WIDTHS

    def test_unknown_profile_returns_common(self):
        """Unknown profile should return common widths."""
        result = get_profile_line_widths("NONEXISTENT-PRINTER-XYZ")
        assert result == COMMON_LINE_WIDTHS

    def test_result_is_sorted(self):
        """Result should be sorted."""
        result = get_profile_line_widths(PROFILE_AUTO)
        assert result == sorted(result)

    def test_default_profile_has_widths(self):
        """Default fallback profile should have line widths."""
        result = get_profile_line_widths("default")
        assert len(result) > 0
        assert 48 in result  # Default fallback has Font A with 48 columns


class TestGetAllLineWidths:
    """Tests for get_all_line_widths function."""

    def test_returns_common_widths(self):
        """Should return common line widths."""
        result = get_all_line_widths()
        assert result == COMMON_LINE_WIDTHS


# =============================================================================
# Cut Mode Tests
# =============================================================================


class TestGetProfileCutModes:
    """Tests for get_profile_cut_modes function."""

    def test_auto_returns_all_modes(self):
        """Auto profile should return all cut modes."""
        result = get_profile_cut_modes(PROFILE_AUTO)
        assert result == DEFAULT_CUT_MODES

    def test_empty_returns_all_modes(self):
        """Empty profile should return all cut modes."""
        result = get_profile_cut_modes("")
        assert result == DEFAULT_CUT_MODES

    def test_none_returns_all_modes(self):
        """None profile should return all cut modes."""
        result = get_profile_cut_modes(None)
        assert result == DEFAULT_CUT_MODES

    def test_custom_returns_all_modes(self):
        """Custom profile should return all cut modes."""
        result = get_profile_cut_modes(PROFILE_CUSTOM)
        assert result == DEFAULT_CUT_MODES

    def test_always_includes_none(self):
        """Result should always include 'none'."""
        result = get_profile_cut_modes("default")
        assert "none" in result

    def test_default_profile_has_cut_modes(self):
        """Default fallback profile should have cut modes."""
        result = get_profile_cut_modes("default")
        assert "none" in result
        assert "partial" in result  # Fallback has paperPartCut
        assert "full" in result  # Fallback has paperFullCut


# =============================================================================
# Feature Query Tests
# =============================================================================


class TestProfileSupportsFeature:
    """Tests for profile_supports_feature function."""

    def test_auto_assumes_all_features(self):
        """Auto profile should assume all features supported."""
        assert profile_supports_feature(PROFILE_AUTO, "qrCode") is True
        assert profile_supports_feature(PROFILE_AUTO, "barcodeB") is True

    def test_empty_assumes_all_features(self):
        """Empty profile should assume all features supported."""
        assert profile_supports_feature("", "graphics") is True

    def test_none_assumes_all_features(self):
        """None profile should assume all features supported."""
        assert profile_supports_feature(None, "highDensity") is True

    def test_custom_assumes_all_features(self):
        """Custom profile should assume all features supported."""
        assert profile_supports_feature(PROFILE_CUSTOM, "pdf417Code") is True

    def test_unknown_profile_assumes_features(self):
        """Unknown profile should assume all features supported."""
        assert profile_supports_feature("NONEXISTENT-PRINTER", "qrCode") is True

    def test_default_profile_features(self):
        """Default fallback profile should have defined features."""
        assert profile_supports_feature("default", "paperFullCut") is True
        assert profile_supports_feature("default", "paperPartCut") is True


class TestGetProfileFeatures:
    """Tests for get_profile_features function."""

    def test_auto_returns_empty(self):
        """Auto profile should return empty dict."""
        result = get_profile_features(PROFILE_AUTO)
        assert result == {}

    def test_empty_returns_empty(self):
        """Empty profile should return empty dict."""
        result = get_profile_features("")
        assert result == {}

    def test_none_returns_empty(self):
        """None profile should return empty dict."""
        result = get_profile_features(None)
        assert result == {}

    def test_custom_returns_empty(self):
        """Custom profile should return empty dict."""
        result = get_profile_features(PROFILE_CUSTOM)
        assert result == {}

    def test_default_profile_returns_features(self):
        """Default profile should return features dict."""
        result = get_profile_features("default")
        assert isinstance(result, dict)
        assert result.get("paperFullCut") is True


# =============================================================================
# Utility Tests
# =============================================================================


class TestGetProfileInfo:
    """Tests for get_profile_info function."""

    def test_auto_returns_empty(self):
        """Auto profile should return empty dict."""
        result = get_profile_info(PROFILE_AUTO)
        assert result == {}

    def test_default_returns_profile_data(self):
        """Default profile should return profile data."""
        result = get_profile_info("default")
        assert isinstance(result, dict)
        assert "name" in result
        assert "vendor" in result


class TestClearCapabilitiesCache:
    """Tests for clear_capabilities_cache function."""

    def test_can_clear_cache(self):
        """Should be able to clear cache without error."""
        # First call to populate cache
        get_profile_choices()
        # Clear cache
        clear_capabilities_cache()
        # Second call should work
        choices = get_profile_choices()
        assert len(choices) > 0


# =============================================================================
# Graceful Degradation Tests
# =============================================================================


class TestGracefulDegradation:
    """Tests for graceful degradation when escpos unavailable."""

    def test_fallback_when_import_fails(self):
        """Should use fallback when escpos import fails."""
        with patch(
            "custom_components.escpos_printer.capabilities._get_capabilities"
        ) as mock_cap:
            mock_cap.return_value = {
                "profiles": {},
                "encodings": {},
            }

            # Should still return something useful
            choices = get_profile_choices()
            assert len(choices) >= 2  # At least Auto and Custom

    def test_handles_missing_profile_data(self):
        """Should handle profiles with missing data gracefully."""
        with patch(
            "custom_components.escpos_printer.capabilities._get_capabilities"
        ) as mock_cap:
            mock_cap.return_value = {
                "profiles": {
                    "incomplete": {
                        # Missing name, vendor, codePages, fonts, features
                    }
                },
                "encodings": {},
            }

            # Should not crash
            codepages = get_profile_codepages("incomplete")
            assert codepages == COMMON_CODEPAGES

            widths = get_profile_line_widths("incomplete")
            assert widths == COMMON_LINE_WIDTHS

            cuts = get_profile_cut_modes("incomplete")
            assert "none" in cuts
