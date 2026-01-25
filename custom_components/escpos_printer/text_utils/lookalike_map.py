"""Look-alike character mapping for Unicode to ASCII fallback.

This module provides the LOOKALIKE_MAP dictionary which maps Unicode characters
to their ASCII look-alike equivalents. This map is ONLY consulted when direct
encoding to the target codepage fails. Characters that exist in the target
codepage (e.g., box drawing in CP437) are preserved as-is, not replaced with
these fallbacks.
"""

from __future__ import annotations

# Fallback character mapping for Unicode characters not in the target codepage.
# Maps Unicode characters to ASCII/basic Latin equivalents.
#
# NOTE: This map is ONLY consulted when direct encoding to the target codepage
# fails. Characters that exist in the target codepage (e.g., box drawing in
# CP437) are preserved as-is, not replaced with these fallbacks.
LOOKALIKE_MAP: dict[str, str] = {
    # ==========================================================================
    # UNIVERSAL LOOKALIKES
    # These characters don't exist in most legacy codepages and should always
    # be converted to their ASCII equivalents.
    # ==========================================================================
    # Typographic quotes -> straight quotes
    "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
    "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK
    "\u201a": ",",  # SINGLE LOW-9 QUOTATION MARK
    "\u201b": "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
    "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
    "\u201e": '"',  # DOUBLE LOW-9 QUOTATION MARK
    "\u201f": '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    "\u2032": "'",  # PRIME
    "\u2033": '"',  # DOUBLE PRIME
    "\u2034": "'''",  # TRIPLE PRIME
    "\u2035": "'",  # REVERSED PRIME
    "\u2036": '"',  # REVERSED DOUBLE PRIME
    "\u2037": "'''",  # REVERSED TRIPLE PRIME
    "\u00ab": "<<",  # LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
    "\u00bb": ">>",  # RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
    "\u2039": "<",  # SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    "\u203a": ">",  # SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    # Dashes and hyphens
    "\u2010": "-",  # HYPHEN
    "\u2011": "-",  # NON-BREAKING HYPHEN
    "\u2012": "-",  # FIGURE DASH
    "\u2013": "-",  # EN DASH
    "\u2014": "--",  # EM DASH
    "\u2015": "--",  # HORIZONTAL BAR
    "\u2212": "-",  # MINUS SIGN
    "\ufe58": "-",  # SMALL EM DASH
    "\ufe63": "-",  # SMALL HYPHEN-MINUS
    "\uff0d": "-",  # FULLWIDTH HYPHEN-MINUS
    # Spaces
    "\u00a0": " ",  # NO-BREAK SPACE
    "\u2000": " ",  # EN QUAD
    "\u2001": " ",  # EM QUAD
    "\u2002": " ",  # EN SPACE
    "\u2003": " ",  # EM SPACE
    "\u2004": " ",  # THREE-PER-EM SPACE
    "\u2005": " ",  # FOUR-PER-EM SPACE
    "\u2006": " ",  # SIX-PER-EM SPACE
    "\u2007": " ",  # FIGURE SPACE
    "\u2008": " ",  # PUNCTUATION SPACE
    "\u2009": " ",  # THIN SPACE
    "\u200a": " ",  # HAIR SPACE
    "\u200b": "",  # ZERO WIDTH SPACE
    "\u202f": " ",  # NARROW NO-BREAK SPACE
    "\u205f": " ",  # MEDIUM MATHEMATICAL SPACE
    "\u3000": " ",  # IDEOGRAPHIC SPACE
    "\ufeff": "",  # ZERO WIDTH NO-BREAK SPACE (BOM)
    # Ellipsis and dots
    "\u2026": "...",  # HORIZONTAL ELLIPSIS
    "\u22ee": ":",  # VERTICAL ELLIPSIS
    "\u22ef": "...",  # MIDLINE HORIZONTAL ELLIPSIS
    "\u00b7": ".",  # MIDDLE DOT
    "\u2022": "*",  # BULLET
    "\u2023": ">",  # TRIANGULAR BULLET
    "\u2024": ".",  # ONE DOT LEADER
    "\u2025": "..",  # TWO DOT LEADER
    "\u2027": "-",  # HYPHENATION POINT
    # Arrows
    "\u2190": "<-",  # LEFTWARDS ARROW
    "\u2191": "^",  # UPWARDS ARROW
    "\u2192": "->",  # RIGHTWARDS ARROW
    "\u2193": "v",  # DOWNWARDS ARROW
    "\u2194": "<->",  # LEFT RIGHT ARROW
    "\u21d0": "<=",  # LEFTWARDS DOUBLE ARROW
    "\u21d2": "=>",  # RIGHTWARDS DOUBLE ARROW
    "\u21d4": "<=>",  # LEFT RIGHT DOUBLE ARROW
    # Math symbols (only those NOT in common codepages like CP437)
    "\u00d7": "x",  # MULTIPLICATION SIGN (not in CP437)
    "\u2260": "!=",  # NOT EQUAL TO
    "\u2264": "<=",  # LESS-THAN OR EQUAL TO
    "\u2265": ">=",  # GREATER-THAN OR EQUAL TO
    "\u2248": "~=",  # ALMOST EQUAL TO
    "\u221e": "inf",  # INFINITY
    "\u2030": "o/oo",  # PER MILLE SIGN
    "\u00be": "3/4",  # VULGAR FRACTION THREE QUARTERS (not in CP437)
    "\u2153": "1/3",  # VULGAR FRACTION ONE THIRD
    "\u2154": "2/3",  # VULGAR FRACTION TWO THIRDS
    # Currency (only those NOT in common codepages)
    "\u20ac": "EUR",  # EURO SIGN (not in CP437)
    "\u20a4": "GBP",  # LIRA SIGN
    "\u20b9": "INR",  # INDIAN RUPEE SIGN
    "\u20bd": "RUB",  # RUBLE SIGN
    "\u20bf": "BTC",  # BITCOIN SIGN
    # Trademark and copyright
    "\u00a9": "(C)",  # COPYRIGHT SIGN
    "\u00ae": "(R)",  # REGISTERED SIGN
    "\u2122": "(TM)",  # TRADE MARK SIGN
    "\u2120": "(SM)",  # SERVICE MARK
    # Degree and temperature
    "\u2103": "C",  # DEGREE CELSIUS
    "\u2109": "F",  # DEGREE FAHRENHEIT
    # Superscripts
    "\u00b2": "2",  # SUPERSCRIPT TWO
    "\u00b3": "3",  # SUPERSCRIPT THREE
    "\u00b9": "1",  # SUPERSCRIPT ONE
    "\u2070": "0",  # SUPERSCRIPT ZERO
    "\u2074": "4",  # SUPERSCRIPT FOUR
    "\u2075": "5",  # SUPERSCRIPT FIVE
    "\u2076": "6",  # SUPERSCRIPT SIX
    "\u2077": "7",  # SUPERSCRIPT SEVEN
    "\u2078": "8",  # SUPERSCRIPT EIGHT
    "\u2079": "9",  # SUPERSCRIPT NINE
    # Subscripts
    "\u2080": "0",  # SUBSCRIPT ZERO
    "\u2081": "1",  # SUBSCRIPT ONE
    "\u2082": "2",  # SUBSCRIPT TWO
    "\u2083": "3",  # SUBSCRIPT THREE
    "\u2084": "4",  # SUBSCRIPT FOUR
    "\u2085": "5",  # SUBSCRIPT FIVE
    "\u2086": "6",  # SUBSCRIPT SIX
    "\u2087": "7",  # SUBSCRIPT SEVEN
    "\u2088": "8",  # SUBSCRIPT EIGHT
    "\u2089": "9",  # SUBSCRIPT NINE
    # Common punctuation
    "\u2016": "||",  # DOUBLE VERTICAL LINE
    "\u2017": "_",  # DOUBLE LOW LINE
    "\u2043": "-",  # HYPHEN BULLET
    "\u2044": "/",  # FRACTION SLASH
    "\u2052": "%",  # COMMERCIAL MINUS SIGN
    "\u20dd": "()",  # COMBINING ENCLOSING CIRCLE
    "\u2116": "No.",  # NUMERO SIGN
    "\u2117": "(P)",  # SOUND RECORDING COPYRIGHT
    "\u211e": "Rx",  # PRESCRIPTION TAKE
    "\u2234": "therefore",  # THEREFORE
    "\u2235": "because",  # BECAUSE
    # ==========================================================================
    # CODEPAGE-SPECIFIC FALLBACKS
    # These characters exist in some codepages (e.g., CP437 has box drawing)
    # but not others (e.g., ISO-8859-1). When the target codepage supports them,
    # they're preserved as-is. These ASCII fallbacks are only used when the
    # target codepage doesn't include the character.
    # ==========================================================================
    # Box drawing -> ASCII art (native to CP437, fallback for ISO-8859-x)
    "\u2500": "-",  # BOX DRAWINGS LIGHT HORIZONTAL
    "\u2501": "-",  # BOX DRAWINGS HEAVY HORIZONTAL
    "\u2502": "|",  # BOX DRAWINGS LIGHT VERTICAL
    "\u2503": "|",  # BOX DRAWINGS HEAVY VERTICAL
    "\u250c": "+",  # BOX DRAWINGS LIGHT DOWN AND RIGHT
    "\u250d": "+",  # BOX DRAWINGS DOWN LIGHT AND RIGHT HEAVY
    "\u250e": "+",  # BOX DRAWINGS DOWN HEAVY AND RIGHT LIGHT
    "\u250f": "+",  # BOX DRAWINGS HEAVY DOWN AND RIGHT
    "\u2510": "+",  # BOX DRAWINGS LIGHT DOWN AND LEFT
    "\u2514": "+",  # BOX DRAWINGS LIGHT UP AND RIGHT
    "\u2518": "+",  # BOX DRAWINGS LIGHT UP AND LEFT
    "\u251c": "+",  # BOX DRAWINGS LIGHT VERTICAL AND RIGHT
    "\u2524": "+",  # BOX DRAWINGS LIGHT VERTICAL AND LEFT
    "\u252c": "+",  # BOX DRAWINGS LIGHT DOWN AND HORIZONTAL
    "\u2534": "+",  # BOX DRAWINGS LIGHT UP AND HORIZONTAL
    "\u253c": "+",  # BOX DRAWINGS LIGHT VERTICAL AND HORIZONTAL
    "\u2550": "=",  # BOX DRAWINGS DOUBLE HORIZONTAL
    "\u2551": "|",  # BOX DRAWINGS DOUBLE VERTICAL
    "\u2552": "+",  # BOX DRAWINGS DOWN SINGLE AND RIGHT DOUBLE
    "\u2553": "+",  # BOX DRAWINGS DOWN DOUBLE AND RIGHT SINGLE
    "\u2554": "+",  # BOX DRAWINGS DOUBLE DOWN AND RIGHT
    "\u2555": "+",  # BOX DRAWINGS DOWN SINGLE AND LEFT DOUBLE
    "\u2556": "+",  # BOX DRAWINGS DOWN DOUBLE AND LEFT SINGLE
    "\u2557": "+",  # BOX DRAWINGS DOUBLE DOWN AND LEFT
    "\u2558": "+",  # BOX DRAWINGS UP SINGLE AND RIGHT DOUBLE
    "\u2559": "+",  # BOX DRAWINGS UP DOUBLE AND RIGHT SINGLE
    "\u255a": "+",  # BOX DRAWINGS DOUBLE UP AND RIGHT
    "\u255b": "+",  # BOX DRAWINGS UP SINGLE AND LEFT DOUBLE
    "\u255c": "+",  # BOX DRAWINGS UP DOUBLE AND LEFT SINGLE
    "\u255d": "+",  # BOX DRAWINGS DOUBLE UP AND LEFT
    "\u255e": "+",  # BOX DRAWINGS VERTICAL SINGLE AND RIGHT DOUBLE
    "\u255f": "+",  # BOX DRAWINGS VERTICAL DOUBLE AND RIGHT SINGLE
    "\u2560": "+",  # BOX DRAWINGS DOUBLE VERTICAL AND RIGHT
    "\u2561": "+",  # BOX DRAWINGS VERTICAL SINGLE AND LEFT DOUBLE
    "\u2562": "+",  # BOX DRAWINGS VERTICAL DOUBLE AND LEFT SINGLE
    "\u2563": "+",  # BOX DRAWINGS DOUBLE VERTICAL AND LEFT
    "\u2564": "+",  # BOX DRAWINGS DOWN SINGLE AND HORIZONTAL DOUBLE
    "\u2565": "+",  # BOX DRAWINGS DOWN DOUBLE AND HORIZONTAL SINGLE
    "\u2566": "+",  # BOX DRAWINGS DOUBLE DOWN AND HORIZONTAL
    "\u2567": "+",  # BOX DRAWINGS UP SINGLE AND HORIZONTAL DOUBLE
    "\u2568": "+",  # BOX DRAWINGS UP DOUBLE AND HORIZONTAL SINGLE
    "\u2569": "+",  # BOX DRAWINGS DOUBLE UP AND HORIZONTAL
    "\u256a": "+",  # BOX DRAWINGS VERTICAL SINGLE AND HORIZONTAL DOUBLE
    "\u256b": "+",  # BOX DRAWINGS VERTICAL DOUBLE AND HORIZONTAL SINGLE
    "\u256c": "+",  # BOX DRAWINGS DOUBLE VERTICAL AND HORIZONTAL
    # Block elements -> ASCII art (native to CP437, fallback for ISO-8859-x)
    "\u2588": "#",  # FULL BLOCK
    "\u2591": ".",  # LIGHT SHADE
    "\u2592": "+",  # MEDIUM SHADE
    "\u2593": "#",  # DARK SHADE
    "\u2580": "^",  # UPPER HALF BLOCK
    "\u2584": "_",  # LOWER HALF BLOCK
    "\u258c": "|",  # LEFT HALF BLOCK
    "\u2590": "|",  # RIGHT HALF BLOCK
    # Misc symbols
    "\u2605": "*",  # BLACK STAR
    "\u2606": "*",  # WHITE STAR
    "\u2610": "[ ]",  # BALLOT BOX
    "\u2611": "[x]",  # BALLOT BOX WITH CHECK
    "\u2612": "[X]",  # BALLOT BOX WITH X
    "\u2713": "v",  # CHECK MARK
    "\u2714": "v",  # HEAVY CHECK MARK
    "\u2715": "x",  # MULTIPLICATION X
    "\u2716": "x",  # HEAVY MULTIPLICATION X
    "\u2717": "x",  # BALLOT X
    "\u2718": "x",  # HEAVY BALLOT X
    "\u2720": "+",  # MALTESE CROSS
    "\u2756": "*",  # BLACK DIAMOND MINUS WHITE X
    "\u2764": "<3",  # HEAVY BLACK HEART
    "\u00a6": "|",  # BROKEN BAR
    "\u00a7": "S",  # SECTION SIGN
    "\u00b6": "P",  # PILCROW SIGN
    "\u00ac": "-",  # NOT SIGN
    "\u00af": "-",  # MACRON
}
