"""Tests for emoji detection and the emoji-aware print path."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.services import emoji_printing
from custom_components.escpos_printer.services.emoji_printing import (
    TextPart,
    plan_parts,
    split_into_parts,
)
from custom_components.escpos_printer.text_effects.font_render import render_text_image
from custom_components.escpos_printer.text_utils.emoji import (
    contains_emoji,
    render_form,
    split_runs,
    strip_emoji,
)

from .test_services_text import _setup_entry


class TestSplitRuns:
    def test_plain_text_is_one_run(self):
        runs = split_runs("Hello, Welt!")
        assert [(r.text, r.emoji) for r in runs] == [("Hello, Welt!", False)]

    def test_empty_text(self):
        assert split_runs("") == []

    def test_emoji_between_text(self):
        runs = split_runs("Hi 😀 there")
        assert [(r.text, r.emoji) for r in runs] == [
            ("Hi ", False),
            ("😀", True),
            (" there", False),
        ]

    def test_adjacent_emoji_form_one_run(self):
        assert [(r.text, r.emoji) for r in split_runs("🎉🎂🍕")] == [("🎉🎂🍕", True)]

    @pytest.mark.parametrize(
        "sequence",
        [
            "👍🏽",  # skin tone
            "👩‍💻",  # ZWJ
            "👨‍👩‍👧‍👦",  # family
            "🇩🇪",  # flag
            "1️⃣",  # keycap
            "❤️",  # text-style symbol + VS16
            "🏴󠁧󠁢󠁥󠁮󠁧󠁿",  # subdivision flag with tag characters
        ],
    )
    def test_sequences_stay_in_one_cluster(self, sequence):
        runs = split_runs(f"a{sequence}b")
        assert [r.emoji for r in runs] == [False, True, False]
        assert runs[1].text == sequence

    @pytest.mark.parametrize("symbol", ["♥", "©", "™", "✔", "→", "5", "#"])
    def test_text_style_symbols_stay_text_without_variation_selector(self, symbol):
        assert not contains_emoji(f"x {symbol} y")

    def test_text_style_symbol_becomes_emoji_with_variation_selector(self):
        assert contains_emoji("©️")

    def test_lone_joiner_is_not_swallowed(self):
        assert [r.emoji for r in split_runs("😀‍")] == [True, False]

    def test_umlauts_and_cjk_are_not_emoji(self):
        assert not contains_emoji("Grüße ÄÖÜß 日本語 한국어")


class TestRenderForm:
    def test_drops_modifiers_and_joiners_but_keeps_pictographs(self):
        assert render_form("👩‍💻") == "👩💻"
        assert render_form("👍🏽") == "👍"
        assert render_form("❤️") == "❤"


class TestStripEmoji:
    def test_removes_emoji_and_the_space_they_leave(self):
        assert strip_emoji("Door 🚪 open") == "Door open"
        assert strip_emoji("Done ✅") == "Done"

    def test_untouched_lines_keep_their_spacing(self):
        assert strip_emoji("a  b\nc 😀 d") == "a  b\nc d"

    def test_text_without_emoji_is_unchanged(self):
        assert strip_emoji("nothing  to see ") == "nothing  to see "


class TestRenderer:
    def test_emoji_draws_ink(self):
        image = render_text_image("😀", font_size=24, max_width_px=100)
        assert image.getextrema()[0] < 128

    def test_emoji_text_width_matches_run_widths(self):
        plain = render_text_image("ab", font_size=20, max_width_px=200, align="left")
        mixed = render_text_image("ab😀", font_size=20, max_width_px=200, align="left")
        assert mixed.size[1] >= plain.size[1]
        # The smiley lands to the right of the text, inside the canvas.
        right_part = mixed.crop((30, 0, 200, mixed.size[1]))
        assert right_part.getextrema()[0] < 128

    def test_emoji_wrap_to_next_line_when_too_wide(self):
        image = render_text_image("😀 😀 😀 😀 😀 😀", font_size=24, max_width_px=60)
        single = render_text_image("😀", font_size=24, max_width_px=60)
        assert image.size[1] > single.size[1]

    def test_text_without_emoji_does_not_load_the_emoji_font(self):
        with patch(
            "custom_components.escpos_printer.text_effects.font_render._load_emoji_font"
        ) as loader:
            render_text_image("plain", font_size=16, max_width_px=100)
        loader.assert_not_called()

    def test_emoji_works_with_every_alignment_and_rotation(self):
        for align in ("left", "center", "right"):
            for rotation in (0, 90, 180, 270):
                image = render_text_image(
                    "a😀", font_size=16, max_width_px=100, align=align, rotation=rotation
                )
                assert image.size[0] > 0


class TestSplitIntoParts:
    def test_groups_consecutive_lines(self):
        parts = split_into_parts("one\ntwo\nthree 😀\nfour 🎉\nfive")
        assert parts == [
            TextPart("one\ntwo\n", emoji=False),
            TextPart("three 😀\nfour 🎉", emoji=True),
            TextPart("five", emoji=False),
        ]

    def test_text_part_keeps_trailing_newline_of_the_input(self):
        assert split_into_parts("a\n") == [TextPart("a\n", emoji=False)]

    def test_blank_line_between_emoji_lines_splits_parts(self):
        parts = split_into_parts("😀\n\n😀")
        assert [p.emoji for p in parts] == [True, False, True]
        assert parts[1].text == "\n"


class TestPlanParts:
    def test_auto_splits_when_emoji_present(self):
        text, parts = plan_parts("Hi 😀", "auto")
        assert text == "Hi 😀"
        assert parts == [TextPart("Hi 😀", emoji=True)]

    def test_auto_without_emoji_uses_the_plain_path(self):
        assert plan_parts("Hi", "auto") == ("Hi", None)

    def test_strip_removes_emoji(self):
        assert plan_parts("Hi 😀", "strip") == ("Hi", None)

    def test_off_keeps_text_untouched(self):
        assert plan_parts("Hi 😀", "off") == ("Hi 😀", None)


class TestPrintText:
    async def test_emoji_lines_print_as_images_between_native_text(self, hass):
        await _setup_entry(hass)
        fake = MagicMock()
        with patch("escpos.printer.Network", return_value=fake):
            await hass.services.async_call(
                DOMAIN,
                "print_text_utf8",
                {"text": "Heading\nDoor 🚪 open\nbye", "cut": "full", "feed": 2},
                blocking=True,
            )
        calls = [c for c in fake.method_calls if c[0] in ("text", "image", "ln", "cut", "close")]
        assert [c[0] for c in calls] == ["text", "image", "text", "ln", "cut", "close"]
        assert calls[0].args == ("Heading\n",)
        assert calls[2].args == ("bye",)
        # One connection for the whole receipt, feed and cut at the very end.
        assert calls[3].args == (2,)
        assert calls[4].kwargs["mode"] == "FULL"

    async def test_plain_text_still_takes_the_single_call_path(self, hass):
        await _setup_entry(hass)
        fake = MagicMock()
        with (
            patch("escpos.printer.Network", return_value=fake),
            patch.object(emoji_printing, "print_parts") as print_parts,
        ):
            await hass.services.async_call(
                DOMAIN, "print_text_utf8", {"text": "no emoji here"}, blocking=True
            )
        print_parts.assert_not_called()
        fake.text.assert_called_once_with("no emoji here")

    async def test_off_mode_prints_question_marks_like_before(self, hass):
        await _setup_entry(hass)
        fake = MagicMock()
        with patch("escpos.printer.Network", return_value=fake):
            await hass.services.async_call(
                DOMAIN, "print_text_utf8", {"text": "Hi 😀", "emoji": "off"}, blocking=True
            )
        fake.text.assert_called_once_with("Hi ?")

    async def test_strip_mode_drops_emoji(self, hass):
        await _setup_entry(hass)
        fake = MagicMock()
        with patch("escpos.printer.Network", return_value=fake):
            await hass.services.async_call(
                DOMAIN, "print_text_utf8", {"text": "Hi 😀", "emoji": "strip"}, blocking=True
            )
        fake.text.assert_called_once_with("Hi")

    async def test_unknown_mode_is_rejected(self, hass):
        await _setup_entry(hass)
        with pytest.raises(Exception, match="emoji"):
            await hass.services.async_call(
                DOMAIN, "print_text_utf8", {"text": "x", "emoji": "rainbow"}, blocking=True
            )


class TestEmojiFontSize:
    def test_follows_font_and_multiplier(self):
        size = emoji_printing._emoji_font_size
        assert size({}) == 20
        assert size({"font": "b"}) == 15
        assert size({"width": "double", "height": "normal"}) == 40
        assert size({"width": 8, "height": 8}) == 160
