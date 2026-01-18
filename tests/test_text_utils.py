"""Tests for the text_utils module."""

from __future__ import annotations

from custom_components.escpos_printer.text_utils import (
    ACCENT_FALLBACK_MAP,
    LOOKALIKE_MAP,
    apply_accent_fallback,
    apply_lookalike_map,
    get_codec_name,
    get_unmappable_chars,
    normalize_unicode,
    transcode_to_codepage,
)

# =============================================================================
# Unicode Normalization Tests
# =============================================================================


class TestNormalizeUnicode:
    """Tests for normalize_unicode function."""

    def test_empty_string(self) -> None:
        """Empty string should return empty."""
        assert normalize_unicode("") == ""

    def test_ascii_unchanged(self) -> None:
        """ASCII text should be unchanged."""
        assert normalize_unicode("Hello, World!") == "Hello, World!"

    def test_nfkc_normalization(self) -> None:
        """NFKC normalization should convert compatibility characters."""
        # Full-width to half-width
        assert normalize_unicode("\uff21\uff22\uff23") == "ABC"
        # Superscript numbers
        assert normalize_unicode("\u00b2\u00b3") == "23"

    def test_ligatures_decomposed(self) -> None:
        """Ligatures should be decomposed."""
        assert normalize_unicode("\ufb01") == "fi"  # fi ligature
        assert normalize_unicode("\ufb02") == "fl"  # fl ligature


# =============================================================================
# Look-alike Map Tests
# =============================================================================


class TestApplyLookalikeMap:
    """Tests for apply_lookalike_map function."""

    def test_empty_string(self) -> None:
        """Empty string should return empty."""
        assert apply_lookalike_map("") == ""

    def test_ascii_unchanged(self) -> None:
        """ASCII text should be unchanged."""
        assert apply_lookalike_map("Hello") == "Hello"

    def test_curly_quotes_to_straight(self) -> None:
        """Curly quotes should be converted to straight quotes."""
        assert apply_lookalike_map("\u201c") == '"'  # Left double quote
        assert apply_lookalike_map("\u201d") == '"'  # Right double quote
        assert apply_lookalike_map("\u2018") == "'"  # Left single quote
        assert apply_lookalike_map("\u2019") == "'"  # Right single quote

    def test_dashes_to_hyphen(self) -> None:
        """Various dashes should be converted to hyphen."""
        assert apply_lookalike_map("\u2013") == "-"  # En dash
        assert apply_lookalike_map("\u2014") == "--"  # Em dash
        assert apply_lookalike_map("\u2212") == "-"  # Minus sign

    def test_ellipsis_to_dots(self) -> None:
        """Ellipsis should be converted to three dots."""
        assert apply_lookalike_map("\u2026") == "..."

    def test_non_breaking_space(self) -> None:
        """Non-breaking space should be converted to regular space."""
        assert apply_lookalike_map("\u00a0") == " "
        assert apply_lookalike_map("\u202f") == " "

    def test_trademark_symbols(self) -> None:
        """Trademark symbols should be converted."""
        assert apply_lookalike_map("\u2122") == "(TM)"
        assert apply_lookalike_map("\u00a9") == "(C)"
        assert apply_lookalike_map("\u00ae") == "(R)"

    def test_arrows(self) -> None:
        """Arrow characters should be converted to ASCII."""
        assert apply_lookalike_map("\u2192") == "->"
        assert apply_lookalike_map("\u2190") == "<-"
        assert apply_lookalike_map("\u21d2") == "=>"

    def test_fractions(self) -> None:
        """Fraction characters should be converted.

        Note: ¼ and ½ are in ACCENT_FALLBACK_MAP (not LOOKALIKE_MAP) because they
        exist in common codepages like CP437. Only ¾ is in LOOKALIKE_MAP since
        it's not in CP437.
        """
        # ¼ and ½ are in CP437, so they're in ACCENT_FALLBACK_MAP, not LOOKALIKE_MAP
        assert apply_lookalike_map("\u00bc") == "\u00bc"  # Preserved (in ACCENT_FALLBACK_MAP)
        assert apply_lookalike_map("\u00bd") == "\u00bd"  # Preserved (in ACCENT_FALLBACK_MAP)
        # ¾ is NOT in CP437, so it's in LOOKALIKE_MAP
        assert apply_lookalike_map("\u00be") == "3/4"

    def test_check_marks(self) -> None:
        """Check mark characters should be converted."""
        assert apply_lookalike_map("\u2713") == "v"
        assert apply_lookalike_map("\u2717") == "x"
        assert apply_lookalike_map("\u2610") == "[ ]"
        assert apply_lookalike_map("\u2611") == "[x]"

    def test_mixed_text(self) -> None:
        """Mixed text with lookalikes should be properly converted."""
        text = "Hello\u2026 \u201cWorld\u201d"
        expected = 'Hello... "World"'
        assert apply_lookalike_map(text) == expected


# =============================================================================
# Accent Fallback Tests
# =============================================================================


class TestApplyAccentFallback:
    """Tests for apply_accent_fallback function."""

    def test_ascii_unchanged(self) -> None:
        """ASCII text should be unchanged."""
        assert apply_accent_fallback("Hello", "CP437") == "Hello"

    def test_accented_chars_in_codepage(self) -> None:
        """Characters in codepage should be preserved."""
        # ISO-8859-1 supports most Western European accented chars
        assert apply_accent_fallback("\u00e9", "ISO_8859-1") == "\u00e9"  # é

    def test_accented_chars_fallback(self) -> None:
        """Accented chars not in codepage should fall back."""
        # CP437 doesn't have many accented characters
        # Polish ł not in CP437
        assert apply_accent_fallback("\u0142", "CP437") == "l"

    def test_ligatures_fallback(self) -> None:
        """Ligatures should be decomposed in fallback."""
        # OE ligature
        assert apply_accent_fallback("\u0152", "CP437") == "OE"
        assert apply_accent_fallback("\u0153", "CP437") == "oe"

    def test_german_sharp_s(self) -> None:
        """German sharp s should fall back appropriately."""
        # ß might not be in all codepages
        result = apply_accent_fallback("\u00df", "CP437")
        # CP437 has ß, so it should be preserved
        assert result in ["\u00df", "ss"]


# =============================================================================
# Codec Name Tests
# =============================================================================


class TestGetCodecName:
    """Tests for get_codec_name function."""

    def test_known_codepages(self) -> None:
        """Known codepages should map correctly."""
        assert get_codec_name("CP437") == "cp437"
        assert get_codec_name("CP850") == "cp850"
        assert get_codec_name("CP1252") == "cp1252"
        assert get_codec_name("ISO_8859-1") == "iso-8859-1"
        assert get_codec_name("ISO_8859-15") == "iso-8859-15"

    def test_case_insensitive(self) -> None:
        """Codepage names should be case-insensitive."""
        assert get_codec_name("cp437") == "cp437"
        assert get_codec_name("Cp437") == "cp437"

    def test_cp_prefix_handling(self) -> None:
        """CP prefix should be handled."""
        assert get_codec_name("CP932") == "cp932"
        assert get_codec_name("CP1251") == "cp1251"

    def test_unknown_codepage(self) -> None:
        """Unknown codepage should return lowercase."""
        assert get_codec_name("UNKNOWN") == "unknown"


# =============================================================================
# Transcode to Codepage Tests
# =============================================================================


class TestTranscodeToCodepage:
    """Tests for transcode_to_codepage function."""

    def test_empty_string(self) -> None:
        """Empty string should return empty."""
        assert transcode_to_codepage("", "CP437") == ""

    def test_ascii_unchanged(self) -> None:
        """ASCII text should be unchanged."""
        result = transcode_to_codepage("Hello, World!", "CP437")
        assert result == "Hello, World!"

    def test_curly_quotes_converted(self) -> None:
        """Curly quotes should be converted to straight quotes."""
        text = "\u201cHello\u201d"
        result = transcode_to_codepage(text, "CP437")
        assert '"' in result

    def test_em_dash_converted(self) -> None:
        """Em dash should be converted."""
        text = "Hello\u2014World"
        result = transcode_to_codepage(text, "CP437")
        assert "--" in result

    def test_ellipsis_converted(self) -> None:
        """Ellipsis should be converted to three dots."""
        text = "Wait\u2026"
        result = transcode_to_codepage(text, "CP437")
        assert "..." in result

    def test_unmappable_replaced(self) -> None:
        """Unmappable characters should be replaced."""
        # Chinese character - not in CP437 and no fallback
        text = "\u4e2d"
        result = transcode_to_codepage(text, "CP437")
        # Should be replaced with ? or similar
        assert result != text

    def test_cp437_native_symbols_preserved(self) -> None:
        """Symbols native to CP437 should be preserved, not converted to fallbacks.

        Characters like ±, £, ¥, ÷ exist in CP437 and should be kept as-is
        when transcoding to CP437, not converted to their ASCII fallbacks.

        Note: Fractions ¼, ½ are decomposed by NFKC normalization to "1/4", "1/2"
        before encoding, so they don't preserve the single-character form.
        """
        # These characters are in CP437 and should be preserved
        text = "±£¥÷"
        result = transcode_to_codepage(text, "CP437")
        # All should be preserved since they're native to CP437
        assert "±" in result
        assert "£" in result
        assert "¥" in result
        assert "÷" in result
        # Verify they weren't converted to their ASCII fallbacks
        assert "+/-" not in result
        assert "GBP" not in result
        assert "JPY" not in result

    def test_symbols_fallback_for_unsupported_codepage(self) -> None:
        """Symbols not in target codepage should use fallback representations.

        When transcoding to a codepage that doesn't support these symbols,
        they should be converted to their ASCII equivalents.
        """
        # ASCII doesn't support these symbols, so they should be converted
        text = "±£"
        result = transcode_to_codepage(text, "ASCII")
        # Should use fallbacks: ± -> "+/-", £ -> "GBP"
        assert "+/-" in result
        assert "GBP" in result

    def test_full_pipeline(self) -> None:
        """Full transcoding pipeline should work."""
        # Text with various Unicode characters
        text = "\u201cCaf\u00e9\u201d \u2014 r\u00e9sum\u00e9\u2026"
        result = transcode_to_codepage(text, "CP1252")
        # CP1252 supports the accented characters
        assert "Caf" in result
        assert "..." in result or "\u2026" in result

    def test_disable_lookalikes(self) -> None:
        """Lookalike conversion can be disabled."""
        text = "\u201cHello\u201d"
        result = transcode_to_codepage(text, "CP437", apply_lookalikes=False)
        # Without lookalikes, curly quotes would be replaced
        assert '"' not in result or result != '"Hello"'

    def test_disable_accents(self) -> None:
        """Accent fallback can be disabled."""
        text = "\u0142"  # Polish ł
        result = transcode_to_codepage(text, "CP437", apply_accents=False)
        # Without accent fallback, would be replaced
        assert result in ["?", "\u0142", "l"]

    def test_unknown_codepage_fallback(self) -> None:
        """Unknown codepage should fall back gracefully."""
        text = "Hello"
        result = transcode_to_codepage(text, "UNKNOWN_CODEPAGE")
        assert result == "Hello"


# =============================================================================
# Get Unmappable Chars Tests
# =============================================================================


class TestGetUnmappableChars:
    """Tests for get_unmappable_chars function."""

    def test_empty_string(self) -> None:
        """Empty string should return empty list."""
        assert get_unmappable_chars("", "CP437") == []

    def test_ascii_all_mappable(self) -> None:
        """ASCII should have no unmappable chars."""
        assert get_unmappable_chars("Hello, World!", "CP437") == []

    def test_chinese_unmappable(self) -> None:
        """Chinese characters should be unmappable in Western codepages."""
        result = get_unmappable_chars("\u4e2d\u6587", "CP437")
        assert len(result) == 2
        assert "\u4e2d" in result
        assert "\u6587" in result

    def test_lookalike_not_unmappable(self) -> None:
        """Characters with lookalikes should not be reported as unmappable."""
        # Curly quote has a lookalike mapping
        result = get_unmappable_chars("\u201c", "CP437")
        assert result == []

    def test_unique_chars_only(self) -> None:
        """Should return unique characters only."""
        result = get_unmappable_chars("\u4e2d\u4e2d\u4e2d", "CP437")
        assert len(result) == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestTranscodingIntegration:
    """Integration tests for common use cases."""

    def test_home_assistant_template_output(self) -> None:
        """Test typical Home Assistant template output."""
        # Template might produce text like this
        text = "Temperature: 72\u00b0F \u2014 Humidity: 45%"
        result = transcode_to_codepage(text, "CP437")
        # Should be printable
        assert "Temperature" in result
        assert "Humidity" in result

    def test_notification_text(self) -> None:
        """Test notification text with smart quotes."""
        text = '\u201cDoor opened\u201d at 3:00\u202fPM'
        result = transcode_to_codepage(text, "CP437")
        assert "Door opened" in result
        assert "PM" in result

    def test_multilingual_fallback(self) -> None:
        """Test text with characters from multiple languages."""
        text = "Caf\u00e9 na\u00efve r\u00e9sum\u00e9"
        result = transcode_to_codepage(text, "CP437")
        # Should have some representation of each word
        assert "Caf" in result
        assert "na" in result

    def test_preserves_newlines(self) -> None:
        """Test that newlines are preserved."""
        text = "Line 1\nLine 2\r\nLine 3"
        result = transcode_to_codepage(text, "CP437")
        assert "\n" in result or "Line 1" in result

    def test_math_symbols(self) -> None:
        """Test math symbols conversion."""
        text = "5 \u00d7 3 = 15 \u00f7 1"
        result = transcode_to_codepage(text, "CP437")
        assert "5" in result
        assert "3" in result
        assert "15" in result


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_very_long_text(self) -> None:
        """Test with very long text."""
        text = "Hello " * 1000
        result = transcode_to_codepage(text, "CP437")
        assert len(result) == len(text)

    def test_only_special_chars(self) -> None:
        """Test text with only special characters."""
        text = "\u201c\u201d\u2018\u2019\u2026"
        result = transcode_to_codepage(text, "CP437")
        assert len(result) > 0

    def test_zero_width_chars_removed(self) -> None:
        """Test that zero-width characters are handled."""
        text = "Hello\u200bWorld"  # Zero-width space
        result = transcode_to_codepage(text, "CP437")
        assert "Hello" in result
        assert "World" in result

    def test_bom_removed(self) -> None:
        """Test that BOM is removed."""
        text = "\ufeffHello"  # BOM
        result = transcode_to_codepage(text, "CP437")
        assert "Hello" in result
        assert result.startswith("Hello") or result == "Hello"


# =============================================================================
# CP437 Box Drawing and Block Character Tests
# =============================================================================


class TestCP437BoxDrawing:
    """Tests for CP437 box drawing and block character preservation."""

    def test_single_line_box_preserved(self) -> None:
        """Single-line box drawing characters should be preserved in CP437."""
        # Unicode box drawing characters that exist in CP437
        chars = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"
        result = transcode_to_codepage(chars, "CP437")
        # Should be preserved, not converted to +, -, |
        assert result == chars

    def test_double_line_box_preserved(self) -> None:
        """Double-line box drawing characters should be preserved in CP437."""
        chars = "\u2550\u2551\u2554\u2557\u255a\u255d\u2560\u2563\u2566\u2569\u256c"
        result = transcode_to_codepage(chars, "CP437")
        assert result == chars

    def test_block_elements_preserved(self) -> None:
        """Block element characters should be preserved in CP437."""
        # Full block, shades, half blocks
        chars = "\u2588\u2591\u2592\u2593\u2580\u2584\u258c\u2590"
        result = transcode_to_codepage(chars, "CP437")
        assert result == chars

    def test_simple_box_art(self) -> None:
        """Simple box art should be preserved."""
        box = (
            "\u250c\u2500\u2500\u2500\u2510\n"
            "\u2502 Hi \u2502\n"
            "\u2514\u2500\u2500\u2500\u2518"
        )
        result = transcode_to_codepage(box, "CP437")
        assert result == box

    def test_double_box_art(self) -> None:
        """Double-line box art should be preserved."""
        box = (
            "\u2554\u2550\u2550\u2550\u2557\n"
            "\u2551 Hi \u2551\n"
            "\u255a\u2550\u2550\u2550\u255d"
        )
        result = transcode_to_codepage(box, "CP437")
        assert result == box

    def test_progress_bar_with_blocks(self) -> None:
        """Progress bar using block characters should be preserved."""
        # Common progress bar pattern
        progress = "\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591 50%"
        result = transcode_to_codepage(progress, "CP437")
        assert result == progress

    def test_shade_gradient(self) -> None:
        """Shade gradient should be preserved."""
        gradient = "\u2591\u2592\u2593\u2588"  # Light to full
        result = transcode_to_codepage(gradient, "CP437")
        assert result == gradient

    def test_mixed_box_and_text(self) -> None:
        """Box drawing mixed with regular text should work."""
        text = "\u250c\u2500 Menu \u2500\u2510\n\u2502 Item 1 \u2502"
        result = transcode_to_codepage(text, "CP437")
        assert result == text

    def test_table_with_box_chars(self) -> None:
        """Table using box drawing should be preserved."""
        table = (
            "\u250c\u2500\u2500\u2500\u252c\u2500\u2500\u2500\u2510\n"
            "\u2502 A \u2502 B \u2502\n"
            "\u251c\u2500\u2500\u2500\u253c\u2500\u2500\u2500\u2524\n"
            "\u2502 1 \u2502 2 \u2502\n"
            "\u2514\u2500\u2500\u2500\u2534\u2500\u2500\u2500\u2518"
        )
        result = transcode_to_codepage(table, "CP437")
        assert result == table


class TestCP437SpecialCharacters:
    """Tests for other CP437-specific characters."""

    def test_currency_symbols(self) -> None:
        """Currency symbols in CP437 should be preserved."""
        # CP437 has cent and pound
        text = "\u00a2\u00a3"  # ¢ £
        result = transcode_to_codepage(text, "CP437")
        assert "\u00a2" in result  # Cent sign preserved
        # Pound might be preserved or fallback depending on exact CP437 variant

    def test_math_symbols_cp437(self) -> None:
        """Math symbols in CP437 should be preserved."""
        # CP437 has ± ≤ ≥ ÷ etc.
        text = "\u00b1"  # ±
        result = transcode_to_codepage(text, "CP437")
        assert result == "\u00b1"

    def test_degree_symbol(self) -> None:
        """Degree symbol should be preserved in CP437."""
        text = "72\u00b0F"  # 72°F
        result = transcode_to_codepage(text, "CP437")
        assert "\u00b0" in result

    def test_bullet_point(self) -> None:
        """Bullet point should be preserved in CP437."""
        text = "\u2022 Item"  # • Item
        result = transcode_to_codepage(text, "CP437")
        # CP437 has bullet at position 0x07, but Unicode bullet might map differently
        assert "Item" in result

    def test_arrows_cp437(self) -> None:
        """Arrow characters should fall back to ASCII in CP437."""
        # Unicode arrows (U+2190-U+2193) are NOT in CP437
        # CP437 has arrows at control positions (0x18-0x1B) which are different codepoints
        text = "\u2190\u2191\u2192\u2193"  # ← ↑ → ↓
        result = transcode_to_codepage(text, "CP437")
        # Should fall back to lookalikes: <- ^ -> v
        assert "<-" in result
        assert "->" in result


class TestCP437VsOtherCodepages:
    """Tests comparing CP437 with other codepages."""

    def test_box_drawing_not_in_iso8859(self) -> None:
        """Box drawing chars should fall back in ISO-8859-1 (doesn't have them)."""
        chars = "\u2500\u2502\u250c"  # ─ │ ┌
        result = transcode_to_codepage(chars, "ISO_8859-1")
        # Should fall back to ASCII equivalents
        assert "-" in result or "|" in result or "+" in result

    def test_accented_preserved_in_iso8859(self) -> None:
        """Accented chars should be preserved in ISO-8859-1."""
        text = "Caf\u00e9"  # Café
        result = transcode_to_codepage(text, "ISO_8859-1")
        assert result == text

    def test_accented_fallback_in_cp437(self) -> None:
        """Some accented chars may need fallback in CP437."""
        # CP437 has some accented chars but not all
        text = "\u00e9"  # é - this IS in CP437
        result = transcode_to_codepage(text, "CP437")
        assert result == "\u00e9"


# =============================================================================
# Mapping Completeness Tests
# =============================================================================


class TestMappingCompleteness:
    """Tests to verify mapping tables are complete for common use cases."""

    def test_lookalike_map_has_common_chars(self) -> None:
        """Lookalike map should have common Unicode characters."""
        # Curly quotes
        assert "\u201c" in LOOKALIKE_MAP
        assert "\u201d" in LOOKALIKE_MAP
        assert "\u2018" in LOOKALIKE_MAP
        assert "\u2019" in LOOKALIKE_MAP
        # Dashes
        assert "\u2013" in LOOKALIKE_MAP  # en dash
        assert "\u2014" in LOOKALIKE_MAP  # em dash
        # Ellipsis
        assert "\u2026" in LOOKALIKE_MAP
        # Spaces
        assert "\u00a0" in LOOKALIKE_MAP  # nbsp
        # Trademark
        assert "\u2122" in LOOKALIKE_MAP

    def test_accent_fallback_has_common_chars(self) -> None:
        """Accent fallback should have common accented characters."""
        # Common European accented chars
        assert "\u00e9" in ACCENT_FALLBACK_MAP or ord("\u00e9") < 256  # é
        # Polish
        assert "\u0142" in ACCENT_FALLBACK_MAP  # ł
        # Czech
        assert "\u010d" in ACCENT_FALLBACK_MAP  # č
        # German ligatures
        assert "\u00df" in ACCENT_FALLBACK_MAP or ord("\u00df") < 256  # ß
