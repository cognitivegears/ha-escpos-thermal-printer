"""Text utilities for UTF-8 to codepage transcoding.

This module provides functions to transcode UTF-8 text to legacy codepages
used by ESC/POS thermal printers, with support for look-alike character
substitution when direct mapping is not available.
"""

from __future__ import annotations

import logging
import unicodedata

_LOGGER = logging.getLogger(__name__)

# Look-alike character mapping for common Unicode characters
# Maps Unicode characters to their ASCII/basic Latin equivalents
LOOKALIKE_MAP: dict[str, str] = {
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
    # Math symbols
    "\u00d7": "x",  # MULTIPLICATION SIGN
    "\u00f7": "/",  # DIVISION SIGN
    "\u2260": "!=",  # NOT EQUAL TO
    "\u2264": "<=",  # LESS-THAN OR EQUAL TO
    "\u2265": ">=",  # GREATER-THAN OR EQUAL TO
    "\u00b1": "+/-",  # PLUS-MINUS SIGN
    "\u2248": "~=",  # ALMOST EQUAL TO
    "\u221e": "inf",  # INFINITY
    "\u2030": "o/oo",  # PER MILLE SIGN
    "\u00bc": "1/4",  # VULGAR FRACTION ONE QUARTER
    "\u00bd": "1/2",  # VULGAR FRACTION ONE HALF
    "\u00be": "3/4",  # VULGAR FRACTION THREE QUARTERS
    "\u2153": "1/3",  # VULGAR FRACTION ONE THIRD
    "\u2154": "2/3",  # VULGAR FRACTION TWO THIRDS
    # Currency (fallbacks for currencies not in target codepage)
    "\u20ac": "EUR",  # EURO SIGN
    "\u00a3": "GBP",  # POUND SIGN (fallback if not in codepage)
    "\u00a5": "JPY",  # YEN SIGN (fallback if not in codepage)
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
    # Box drawing (simplified to ASCII)
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
    # Block elements
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

# Extended mapping for accented characters to base characters
# Used when the target codepage doesn't support the accented version
ACCENT_FALLBACK_MAP: dict[str, str] = {
    # Latin Extended-A and Extended-B characters
    "\u0100": "A",  # LATIN CAPITAL LETTER A WITH MACRON
    "\u0101": "a",  # LATIN SMALL LETTER A WITH MACRON
    "\u0102": "A",  # LATIN CAPITAL LETTER A WITH BREVE
    "\u0103": "a",  # LATIN SMALL LETTER A WITH BREVE
    "\u0104": "A",  # LATIN CAPITAL LETTER A WITH OGONEK
    "\u0105": "a",  # LATIN SMALL LETTER A WITH OGONEK
    "\u0106": "C",  # LATIN CAPITAL LETTER C WITH ACUTE
    "\u0107": "c",  # LATIN SMALL LETTER C WITH ACUTE
    "\u0108": "C",  # LATIN CAPITAL LETTER C WITH CIRCUMFLEX
    "\u0109": "c",  # LATIN SMALL LETTER C WITH CIRCUMFLEX
    "\u010a": "C",  # LATIN CAPITAL LETTER C WITH DOT ABOVE
    "\u010b": "c",  # LATIN SMALL LETTER C WITH DOT ABOVE
    "\u010c": "C",  # LATIN CAPITAL LETTER C WITH CARON
    "\u010d": "c",  # LATIN SMALL LETTER C WITH CARON
    "\u010e": "D",  # LATIN CAPITAL LETTER D WITH CARON
    "\u010f": "d",  # LATIN SMALL LETTER D WITH CARON
    "\u0110": "D",  # LATIN CAPITAL LETTER D WITH STROKE
    "\u0111": "d",  # LATIN SMALL LETTER D WITH STROKE
    "\u0112": "E",  # LATIN CAPITAL LETTER E WITH MACRON
    "\u0113": "e",  # LATIN SMALL LETTER E WITH MACRON
    "\u0114": "E",  # LATIN CAPITAL LETTER E WITH BREVE
    "\u0115": "e",  # LATIN SMALL LETTER E WITH BREVE
    "\u0116": "E",  # LATIN CAPITAL LETTER E WITH DOT ABOVE
    "\u0117": "e",  # LATIN SMALL LETTER E WITH DOT ABOVE
    "\u0118": "E",  # LATIN CAPITAL LETTER E WITH OGONEK
    "\u0119": "e",  # LATIN SMALL LETTER E WITH OGONEK
    "\u011a": "E",  # LATIN CAPITAL LETTER E WITH CARON
    "\u011b": "e",  # LATIN SMALL LETTER E WITH CARON
    "\u011c": "G",  # LATIN CAPITAL LETTER G WITH CIRCUMFLEX
    "\u011d": "g",  # LATIN SMALL LETTER G WITH CIRCUMFLEX
    "\u011e": "G",  # LATIN CAPITAL LETTER G WITH BREVE
    "\u011f": "g",  # LATIN SMALL LETTER G WITH BREVE
    "\u0120": "G",  # LATIN CAPITAL LETTER G WITH DOT ABOVE
    "\u0121": "g",  # LATIN SMALL LETTER G WITH DOT ABOVE
    "\u0122": "G",  # LATIN CAPITAL LETTER G WITH CEDILLA
    "\u0123": "g",  # LATIN SMALL LETTER G WITH CEDILLA
    "\u0124": "H",  # LATIN CAPITAL LETTER H WITH CIRCUMFLEX
    "\u0125": "h",  # LATIN SMALL LETTER H WITH CIRCUMFLEX
    "\u0126": "H",  # LATIN CAPITAL LETTER H WITH STROKE
    "\u0127": "h",  # LATIN SMALL LETTER H WITH STROKE
    "\u0128": "I",  # LATIN CAPITAL LETTER I WITH TILDE
    "\u0129": "i",  # LATIN SMALL LETTER I WITH TILDE
    "\u012a": "I",  # LATIN CAPITAL LETTER I WITH MACRON
    "\u012b": "i",  # LATIN SMALL LETTER I WITH MACRON
    "\u012c": "I",  # LATIN CAPITAL LETTER I WITH BREVE
    "\u012d": "i",  # LATIN SMALL LETTER I WITH BREVE
    "\u012e": "I",  # LATIN CAPITAL LETTER I WITH OGONEK
    "\u012f": "i",  # LATIN SMALL LETTER I WITH OGONEK
    "\u0130": "I",  # LATIN CAPITAL LETTER I WITH DOT ABOVE
    "\u0131": "i",  # LATIN SMALL LETTER DOTLESS I
    "\u0134": "J",  # LATIN CAPITAL LETTER J WITH CIRCUMFLEX
    "\u0135": "j",  # LATIN SMALL LETTER J WITH CIRCUMFLEX
    "\u0136": "K",  # LATIN CAPITAL LETTER K WITH CEDILLA
    "\u0137": "k",  # LATIN SMALL LETTER K WITH CEDILLA
    "\u0139": "L",  # LATIN CAPITAL LETTER L WITH ACUTE
    "\u013a": "l",  # LATIN SMALL LETTER L WITH ACUTE
    "\u013b": "L",  # LATIN CAPITAL LETTER L WITH CEDILLA
    "\u013c": "l",  # LATIN SMALL LETTER L WITH CEDILLA
    "\u013d": "L",  # LATIN CAPITAL LETTER L WITH CARON
    "\u013e": "l",  # LATIN SMALL LETTER L WITH CARON
    "\u0141": "L",  # LATIN CAPITAL LETTER L WITH STROKE
    "\u0142": "l",  # LATIN SMALL LETTER L WITH STROKE
    "\u0143": "N",  # LATIN CAPITAL LETTER N WITH ACUTE
    "\u0144": "n",  # LATIN SMALL LETTER N WITH ACUTE
    "\u0145": "N",  # LATIN CAPITAL LETTER N WITH CEDILLA
    "\u0146": "n",  # LATIN SMALL LETTER N WITH CEDILLA
    "\u0147": "N",  # LATIN CAPITAL LETTER N WITH CARON
    "\u0148": "n",  # LATIN SMALL LETTER N WITH CARON
    "\u014c": "O",  # LATIN CAPITAL LETTER O WITH MACRON
    "\u014d": "o",  # LATIN SMALL LETTER O WITH MACRON
    "\u014e": "O",  # LATIN CAPITAL LETTER O WITH BREVE
    "\u014f": "o",  # LATIN SMALL LETTER O WITH BREVE
    "\u0150": "O",  # LATIN CAPITAL LETTER O WITH DOUBLE ACUTE
    "\u0151": "o",  # LATIN SMALL LETTER O WITH DOUBLE ACUTE
    "\u0152": "OE",  # LATIN CAPITAL LIGATURE OE
    "\u0153": "oe",  # LATIN SMALL LIGATURE OE
    "\u0154": "R",  # LATIN CAPITAL LETTER R WITH ACUTE
    "\u0155": "r",  # LATIN SMALL LETTER R WITH ACUTE
    "\u0156": "R",  # LATIN CAPITAL LETTER R WITH CEDILLA
    "\u0157": "r",  # LATIN SMALL LETTER R WITH CEDILLA
    "\u0158": "R",  # LATIN CAPITAL LETTER R WITH CARON
    "\u0159": "r",  # LATIN SMALL LETTER R WITH CARON
    "\u015a": "S",  # LATIN CAPITAL LETTER S WITH ACUTE
    "\u015b": "s",  # LATIN SMALL LETTER S WITH ACUTE
    "\u015c": "S",  # LATIN CAPITAL LETTER S WITH CIRCUMFLEX
    "\u015d": "s",  # LATIN SMALL LETTER S WITH CIRCUMFLEX
    "\u015e": "S",  # LATIN CAPITAL LETTER S WITH CEDILLA
    "\u015f": "s",  # LATIN SMALL LETTER S WITH CEDILLA
    "\u0160": "S",  # LATIN CAPITAL LETTER S WITH CARON
    "\u0161": "s",  # LATIN SMALL LETTER S WITH CARON
    "\u0162": "T",  # LATIN CAPITAL LETTER T WITH CEDILLA
    "\u0163": "t",  # LATIN SMALL LETTER T WITH CEDILLA
    "\u0164": "T",  # LATIN CAPITAL LETTER T WITH CARON
    "\u0165": "t",  # LATIN SMALL LETTER T WITH CARON
    "\u0166": "T",  # LATIN CAPITAL LETTER T WITH STROKE
    "\u0167": "t",  # LATIN SMALL LETTER T WITH STROKE
    "\u0168": "U",  # LATIN CAPITAL LETTER U WITH TILDE
    "\u0169": "u",  # LATIN SMALL LETTER U WITH TILDE
    "\u016a": "U",  # LATIN CAPITAL LETTER U WITH MACRON
    "\u016b": "u",  # LATIN SMALL LETTER U WITH MACRON
    "\u016c": "U",  # LATIN CAPITAL LETTER U WITH BREVE
    "\u016d": "u",  # LATIN SMALL LETTER U WITH BREVE
    "\u016e": "U",  # LATIN CAPITAL LETTER U WITH RING ABOVE
    "\u016f": "u",  # LATIN SMALL LETTER U WITH RING ABOVE
    "\u0170": "U",  # LATIN CAPITAL LETTER U WITH DOUBLE ACUTE
    "\u0171": "u",  # LATIN SMALL LETTER U WITH DOUBLE ACUTE
    "\u0172": "U",  # LATIN CAPITAL LETTER U WITH OGONEK
    "\u0173": "u",  # LATIN SMALL LETTER U WITH OGONEK
    "\u0174": "W",  # LATIN CAPITAL LETTER W WITH CIRCUMFLEX
    "\u0175": "w",  # LATIN SMALL LETTER W WITH CIRCUMFLEX
    "\u0176": "Y",  # LATIN CAPITAL LETTER Y WITH CIRCUMFLEX
    "\u0177": "y",  # LATIN SMALL LETTER Y WITH CIRCUMFLEX
    "\u0178": "Y",  # LATIN CAPITAL LETTER Y WITH DIAERESIS
    "\u0179": "Z",  # LATIN CAPITAL LETTER Z WITH ACUTE
    "\u017a": "z",  # LATIN SMALL LETTER Z WITH ACUTE
    "\u017b": "Z",  # LATIN CAPITAL LETTER Z WITH DOT ABOVE
    "\u017c": "z",  # LATIN SMALL LETTER Z WITH DOT ABOVE
    "\u017d": "Z",  # LATIN CAPITAL LETTER Z WITH CARON
    "\u017e": "z",  # LATIN SMALL LETTER Z WITH CARON
    # Greek letters (common in technical contexts)
    "\u0391": "A",  # GREEK CAPITAL LETTER ALPHA
    "\u0392": "B",  # GREEK CAPITAL LETTER BETA
    "\u0393": "G",  # GREEK CAPITAL LETTER GAMMA
    "\u0394": "D",  # GREEK CAPITAL LETTER DELTA
    "\u0395": "E",  # GREEK CAPITAL LETTER EPSILON
    "\u0396": "Z",  # GREEK CAPITAL LETTER ZETA
    "\u0397": "H",  # GREEK CAPITAL LETTER ETA
    "\u0398": "TH",  # GREEK CAPITAL LETTER THETA
    "\u0399": "I",  # GREEK CAPITAL LETTER IOTA
    "\u039a": "K",  # GREEK CAPITAL LETTER KAPPA
    "\u039b": "L",  # GREEK CAPITAL LETTER LAMDA
    "\u039c": "M",  # GREEK CAPITAL LETTER MU
    "\u039d": "N",  # GREEK CAPITAL LETTER NU
    "\u039e": "X",  # GREEK CAPITAL LETTER XI
    "\u039f": "O",  # GREEK CAPITAL LETTER OMICRON
    "\u03a0": "P",  # GREEK CAPITAL LETTER PI
    "\u03a1": "R",  # GREEK CAPITAL LETTER RHO
    "\u03a3": "S",  # GREEK CAPITAL LETTER SIGMA
    "\u03a4": "T",  # GREEK CAPITAL LETTER TAU
    "\u03a5": "Y",  # GREEK CAPITAL LETTER UPSILON
    "\u03a6": "PH",  # GREEK CAPITAL LETTER PHI
    "\u03a7": "CH",  # GREEK CAPITAL LETTER CHI
    "\u03a8": "PS",  # GREEK CAPITAL LETTER PSI
    "\u03a9": "O",  # GREEK CAPITAL LETTER OMEGA
    "\u03b1": "a",  # GREEK SMALL LETTER ALPHA
    "\u03b2": "b",  # GREEK SMALL LETTER BETA
    "\u03b3": "g",  # GREEK SMALL LETTER GAMMA
    "\u03b4": "d",  # GREEK SMALL LETTER DELTA
    "\u03b5": "e",  # GREEK SMALL LETTER EPSILON
    "\u03b6": "z",  # GREEK SMALL LETTER ZETA
    "\u03b7": "h",  # GREEK SMALL LETTER ETA
    "\u03b8": "th",  # GREEK SMALL LETTER THETA
    "\u03b9": "i",  # GREEK SMALL LETTER IOTA
    "\u03ba": "k",  # GREEK SMALL LETTER KAPPA
    "\u03bb": "l",  # GREEK SMALL LETTER LAMDA
    "\u03bc": "u",  # GREEK SMALL LETTER MU
    "\u03bd": "v",  # GREEK SMALL LETTER NU
    "\u03be": "x",  # GREEK SMALL LETTER XI
    "\u03bf": "o",  # GREEK SMALL LETTER OMICRON
    "\u03c0": "pi",  # GREEK SMALL LETTER PI
    "\u03c1": "r",  # GREEK SMALL LETTER RHO
    "\u03c2": "s",  # GREEK SMALL LETTER FINAL SIGMA
    "\u03c3": "s",  # GREEK SMALL LETTER SIGMA
    "\u03c4": "t",  # GREEK SMALL LETTER TAU
    "\u03c5": "y",  # GREEK SMALL LETTER UPSILON
    "\u03c6": "ph",  # GREEK SMALL LETTER PHI
    "\u03c7": "ch",  # GREEK SMALL LETTER CHI
    "\u03c8": "ps",  # GREEK SMALL LETTER PSI
    "\u03c9": "o",  # GREEK SMALL LETTER OMEGA
    # Cyrillic (basic transliteration)
    "\u0410": "A",  # CYRILLIC CAPITAL LETTER A
    "\u0411": "B",  # CYRILLIC CAPITAL LETTER BE
    "\u0412": "V",  # CYRILLIC CAPITAL LETTER VE
    "\u0413": "G",  # CYRILLIC CAPITAL LETTER GHE
    "\u0414": "D",  # CYRILLIC CAPITAL LETTER DE
    "\u0415": "E",  # CYRILLIC CAPITAL LETTER IE
    "\u0416": "ZH",  # CYRILLIC CAPITAL LETTER ZHE
    "\u0417": "Z",  # CYRILLIC CAPITAL LETTER ZE
    "\u0418": "I",  # CYRILLIC CAPITAL LETTER I
    "\u0419": "Y",  # CYRILLIC CAPITAL LETTER SHORT I
    "\u041a": "K",  # CYRILLIC CAPITAL LETTER KA
    "\u041b": "L",  # CYRILLIC CAPITAL LETTER EL
    "\u041c": "M",  # CYRILLIC CAPITAL LETTER EM
    "\u041d": "N",  # CYRILLIC CAPITAL LETTER EN
    "\u041e": "O",  # CYRILLIC CAPITAL LETTER O
    "\u041f": "P",  # CYRILLIC CAPITAL LETTER PE
    "\u0420": "R",  # CYRILLIC CAPITAL LETTER ER
    "\u0421": "S",  # CYRILLIC CAPITAL LETTER ES
    "\u0422": "T",  # CYRILLIC CAPITAL LETTER TE
    "\u0423": "U",  # CYRILLIC CAPITAL LETTER U
    "\u0424": "F",  # CYRILLIC CAPITAL LETTER EF
    "\u0425": "KH",  # CYRILLIC CAPITAL LETTER HA
    "\u0426": "TS",  # CYRILLIC CAPITAL LETTER TSE
    "\u0427": "CH",  # CYRILLIC CAPITAL LETTER CHE
    "\u0428": "SH",  # CYRILLIC CAPITAL LETTER SHA
    "\u0429": "SHCH",  # CYRILLIC CAPITAL LETTER SHCHA
    "\u042a": "",  # CYRILLIC CAPITAL LETTER HARD SIGN
    "\u042b": "Y",  # CYRILLIC CAPITAL LETTER YERU
    "\u042c": "",  # CYRILLIC CAPITAL LETTER SOFT SIGN
    "\u042d": "E",  # CYRILLIC CAPITAL LETTER E
    "\u042e": "YU",  # CYRILLIC CAPITAL LETTER YU
    "\u042f": "YA",  # CYRILLIC CAPITAL LETTER YA
    "\u0430": "a",  # CYRILLIC SMALL LETTER A
    "\u0431": "b",  # CYRILLIC SMALL LETTER BE
    "\u0432": "v",  # CYRILLIC SMALL LETTER VE
    "\u0433": "g",  # CYRILLIC SMALL LETTER GHE
    "\u0434": "d",  # CYRILLIC SMALL LETTER DE
    "\u0435": "e",  # CYRILLIC SMALL LETTER IE
    "\u0436": "zh",  # CYRILLIC SMALL LETTER ZHE
    "\u0437": "z",  # CYRILLIC SMALL LETTER ZE
    "\u0438": "i",  # CYRILLIC SMALL LETTER I
    "\u0439": "y",  # CYRILLIC SMALL LETTER SHORT I
    "\u043a": "k",  # CYRILLIC SMALL LETTER KA
    "\u043b": "l",  # CYRILLIC SMALL LETTER EL
    "\u043c": "m",  # CYRILLIC SMALL LETTER EM
    "\u043d": "n",  # CYRILLIC SMALL LETTER EN
    "\u043e": "o",  # CYRILLIC SMALL LETTER O
    "\u043f": "p",  # CYRILLIC SMALL LETTER PE
    "\u0440": "r",  # CYRILLIC SMALL LETTER ER
    "\u0441": "s",  # CYRILLIC SMALL LETTER ES
    "\u0442": "t",  # CYRILLIC SMALL LETTER TE
    "\u0443": "u",  # CYRILLIC SMALL LETTER U
    "\u0444": "f",  # CYRILLIC SMALL LETTER EF
    "\u0445": "kh",  # CYRILLIC SMALL LETTER HA
    "\u0446": "ts",  # CYRILLIC SMALL LETTER TSE
    "\u0447": "ch",  # CYRILLIC SMALL LETTER CHE
    "\u0448": "sh",  # CYRILLIC SMALL LETTER SHA
    "\u0449": "shch",  # CYRILLIC SMALL LETTER SHCHA
    "\u044a": "",  # CYRILLIC SMALL LETTER HARD SIGN
    "\u044b": "y",  # CYRILLIC SMALL LETTER YERU
    "\u044c": "",  # CYRILLIC SMALL LETTER SOFT SIGN
    "\u044d": "e",  # CYRILLIC SMALL LETTER E
    "\u044e": "yu",  # CYRILLIC SMALL LETTER YU
    "\u044f": "ya",  # CYRILLIC SMALL LETTER YA
    # Common Latin-1 Supplement (fallbacks when not in codepage)
    "\u00c0": "A",  # LATIN CAPITAL LETTER A WITH GRAVE
    "\u00c1": "A",  # LATIN CAPITAL LETTER A WITH ACUTE
    "\u00c2": "A",  # LATIN CAPITAL LETTER A WITH CIRCUMFLEX
    "\u00c3": "A",  # LATIN CAPITAL LETTER A WITH TILDE
    "\u00c4": "A",  # LATIN CAPITAL LETTER A WITH DIAERESIS
    "\u00c5": "A",  # LATIN CAPITAL LETTER A WITH RING ABOVE
    "\u00c6": "AE",  # LATIN CAPITAL LETTER AE
    "\u00c7": "C",  # LATIN CAPITAL LETTER C WITH CEDILLA
    "\u00c8": "E",  # LATIN CAPITAL LETTER E WITH GRAVE
    "\u00c9": "E",  # LATIN CAPITAL LETTER E WITH ACUTE
    "\u00ca": "E",  # LATIN CAPITAL LETTER E WITH CIRCUMFLEX
    "\u00cb": "E",  # LATIN CAPITAL LETTER E WITH DIAERESIS
    "\u00cc": "I",  # LATIN CAPITAL LETTER I WITH GRAVE
    "\u00cd": "I",  # LATIN CAPITAL LETTER I WITH ACUTE
    "\u00ce": "I",  # LATIN CAPITAL LETTER I WITH CIRCUMFLEX
    "\u00cf": "I",  # LATIN CAPITAL LETTER I WITH DIAERESIS
    "\u00d0": "D",  # LATIN CAPITAL LETTER ETH
    "\u00d1": "N",  # LATIN CAPITAL LETTER N WITH TILDE
    "\u00d2": "O",  # LATIN CAPITAL LETTER O WITH GRAVE
    "\u00d3": "O",  # LATIN CAPITAL LETTER O WITH ACUTE
    "\u00d4": "O",  # LATIN CAPITAL LETTER O WITH CIRCUMFLEX
    "\u00d5": "O",  # LATIN CAPITAL LETTER O WITH TILDE
    "\u00d6": "O",  # LATIN CAPITAL LETTER O WITH DIAERESIS
    "\u00d8": "O",  # LATIN CAPITAL LETTER O WITH STROKE
    "\u00d9": "U",  # LATIN CAPITAL LETTER U WITH GRAVE
    "\u00da": "U",  # LATIN CAPITAL LETTER U WITH ACUTE
    "\u00db": "U",  # LATIN CAPITAL LETTER U WITH CIRCUMFLEX
    "\u00dc": "U",  # LATIN CAPITAL LETTER U WITH DIAERESIS
    "\u00dd": "Y",  # LATIN CAPITAL LETTER Y WITH ACUTE
    "\u00de": "TH",  # LATIN CAPITAL LETTER THORN
    "\u00df": "ss",  # LATIN SMALL LETTER SHARP S
    "\u00e0": "a",  # LATIN SMALL LETTER A WITH GRAVE
    "\u00e1": "a",  # LATIN SMALL LETTER A WITH ACUTE
    "\u00e2": "a",  # LATIN SMALL LETTER A WITH CIRCUMFLEX
    "\u00e3": "a",  # LATIN SMALL LETTER A WITH TILDE
    "\u00e4": "a",  # LATIN SMALL LETTER A WITH DIAERESIS
    "\u00e5": "a",  # LATIN SMALL LETTER A WITH RING ABOVE
    "\u00e6": "ae",  # LATIN SMALL LETTER AE
    "\u00e7": "c",  # LATIN SMALL LETTER C WITH CEDILLA
    "\u00e8": "e",  # LATIN SMALL LETTER E WITH GRAVE
    "\u00e9": "e",  # LATIN SMALL LETTER E WITH ACUTE
    "\u00ea": "e",  # LATIN SMALL LETTER E WITH CIRCUMFLEX
    "\u00eb": "e",  # LATIN SMALL LETTER E WITH DIAERESIS
    "\u00ec": "i",  # LATIN SMALL LETTER I WITH GRAVE
    "\u00ed": "i",  # LATIN SMALL LETTER I WITH ACUTE
    "\u00ee": "i",  # LATIN SMALL LETTER I WITH CIRCUMFLEX
    "\u00ef": "i",  # LATIN SMALL LETTER I WITH DIAERESIS
    "\u00f0": "d",  # LATIN SMALL LETTER ETH
    "\u00f1": "n",  # LATIN SMALL LETTER N WITH TILDE
    "\u00f2": "o",  # LATIN SMALL LETTER O WITH GRAVE
    "\u00f3": "o",  # LATIN SMALL LETTER O WITH ACUTE
    "\u00f4": "o",  # LATIN SMALL LETTER O WITH CIRCUMFLEX
    "\u00f5": "o",  # LATIN SMALL LETTER O WITH TILDE
    "\u00f6": "o",  # LATIN SMALL LETTER O WITH DIAERESIS
    "\u00f8": "o",  # LATIN SMALL LETTER O WITH STROKE
    "\u00f9": "u",  # LATIN SMALL LETTER U WITH GRAVE
    "\u00fa": "u",  # LATIN SMALL LETTER U WITH ACUTE
    "\u00fb": "u",  # LATIN SMALL LETTER U WITH CIRCUMFLEX
    "\u00fc": "u",  # LATIN SMALL LETTER U WITH DIAERESIS
    "\u00fd": "y",  # LATIN SMALL LETTER Y WITH ACUTE
    "\u00fe": "th",  # LATIN SMALL LETTER THORN
    "\u00ff": "y",  # LATIN SMALL LETTER Y WITH DIAERESIS
}

# Mapping from common codepage names to Python codec names
CODEPAGE_TO_CODEC: dict[str, str] = {
    "CP437": "cp437",
    "CP850": "cp850",
    "CP852": "cp852",
    "CP858": "cp858",
    "CP860": "cp860",
    "CP863": "cp863",
    "CP865": "cp865",
    "CP866": "cp866",
    "CP932": "cp932",
    "CP1250": "cp1250",
    "CP1251": "cp1251",
    "CP1252": "cp1252",
    "CP1253": "cp1253",
    "CP1254": "cp1254",
    "CP1255": "cp1255",
    "CP1256": "cp1256",
    "CP1257": "cp1257",
    "CP1258": "cp1258",
    "ISO_8859-1": "iso-8859-1",
    "ISO_8859-2": "iso-8859-2",
    "ISO_8859-7": "iso-8859-7",
    "ISO_8859-15": "iso-8859-15",
    "LATIN1": "latin-1",
    "UTF-8": "utf-8",
}


def normalize_unicode(text: str) -> str:
    """Normalize Unicode text using NFKC normalization.

    NFKC normalization converts compatibility characters to their canonical
    equivalents (e.g., ligatures to separate characters, full-width to half-width).

    Args:
        text: Unicode text to normalize.

    Returns:
        Normalized text.
    """
    return unicodedata.normalize("NFKC", text)


def apply_lookalike_map(text: str) -> str:
    """Apply look-alike character substitution.

    Replaces Unicode characters with their ASCII look-alike equivalents.

    Args:
        text: Text to process.

    Returns:
        Text with look-alike substitutions applied.
    """
    result = []
    for char in text:
        if char in LOOKALIKE_MAP:
            result.append(LOOKALIKE_MAP[char])
        else:
            result.append(char)
    return "".join(result)


def apply_accent_fallback(text: str, codepage: str) -> str:
    """Apply accent fallback for characters not in target codepage.

    First tries to encode each character in the target codepage.
    If that fails, tries the accent fallback map.

    Args:
        text: Text to process.
        codepage: Target codepage name.

    Returns:
        Text with accent fallbacks applied where needed.
    """
    codec = get_codec_name(codepage)
    result = []

    for char in text:
        # Try to encode directly
        try:
            char.encode(codec)
            result.append(char)
        except (UnicodeEncodeError, LookupError):
            # Character not in codepage, try fallback
            if char in ACCENT_FALLBACK_MAP:
                result.append(ACCENT_FALLBACK_MAP[char])
            else:
                result.append(char)

    return "".join(result)


def get_codec_name(codepage: str) -> str:
    """Get Python codec name for a codepage.

    Args:
        codepage: Codepage name (e.g., "CP437", "ISO_8859-1").

    Returns:
        Python codec name.
    """
    # Check mapping first
    if codepage.upper() in CODEPAGE_TO_CODEC:
        return CODEPAGE_TO_CODEC[codepage.upper()]

    # Try common transformations
    normalized = codepage.upper().replace("-", "_").replace(" ", "")

    # Handle CP prefix
    if normalized.startswith("CP") and normalized[2:].isdigit():
        return f"cp{normalized[2:]}"

    # Handle ISO_8859 prefix
    if normalized.startswith("ISO_8859_") or normalized.startswith("ISO8859_"):
        num = normalized.split("_")[-1]
        return f"iso-8859-{num}"

    # Fall back to lowercase
    return codepage.lower()


def transcode_to_codepage(
    text: str,
    codepage: str,
    replace_char: str = "?",
    apply_lookalikes: bool = True,
    apply_accents: bool = True,
) -> str:
    """Transcode UTF-8 text to a target codepage.

    This function performs intelligent character-by-character transcoding:
    1. NFKC Unicode normalization (compatibility decomposition)
    2. For each character:
       a. Try direct encoding to target codepage (preserves native chars like CP437 box drawing)
       b. If that fails, try look-alike substitution
       c. If that fails, try accent fallback
       d. If all fail, use replacement character

    This approach preserves characters native to the target codepage (e.g., box drawing
    and block characters in CP437) while still providing fallbacks for unsupported chars.

    Args:
        text: UTF-8 text to transcode.
        codepage: Target codepage name (e.g., "CP437", "ISO_8859-1").
        replace_char: Character to use for unmappable characters.
        apply_lookalikes: Whether to apply look-alike substitutions.
        apply_accents: Whether to apply accent fallbacks.

    Returns:
        Transcoded text as a string (decoded back from the codepage).
    """
    if not text:
        return text

    # Step 1: Normalize Unicode
    normalized = normalize_unicode(text)

    codec = get_codec_name(codepage)

    # Verify codec exists
    try:
        "".encode(codec)
    except LookupError:
        _LOGGER.warning("Unknown codepage '%s', using UTF-8", codepage)
        return normalized

    # Step 2: Process each character with smart fallback
    result_chars: list[str] = []

    for char in normalized:
        # Try direct encoding first (preserves native codepage characters)
        try:
            char.encode(codec)
            result_chars.append(char)
            continue
        except UnicodeEncodeError:
            pass

        # Try look-alike substitution
        if apply_lookalikes and char in LOOKALIKE_MAP:
            replacement = LOOKALIKE_MAP[char]
            # Verify the replacement can be encoded
            try:
                replacement.encode(codec)
                result_chars.append(replacement)
                continue
            except UnicodeEncodeError:
                pass  # Lookalike also can't be encoded, try next fallback

        # Try accent fallback
        if apply_accents and char in ACCENT_FALLBACK_MAP:
            replacement = ACCENT_FALLBACK_MAP[char]
            try:
                replacement.encode(codec)
                result_chars.append(replacement)
                continue
            except UnicodeEncodeError:
                pass  # Fallback also can't be encoded

        # All fallbacks failed, use replacement character
        result_chars.append(replace_char)

    return "".join(result_chars)


def get_unmappable_chars(text: str, codepage: str) -> list[str]:
    """Get list of characters that cannot be mapped to the codepage.

    Useful for debugging or warning users about characters that will
    be replaced.

    Args:
        text: Text to check.
        codepage: Target codepage name.

    Returns:
        List of unique characters that cannot be mapped.
    """
    if not text:
        return []

    codec = get_codec_name(codepage)
    unmappable = []

    # Normalize first
    normalized = normalize_unicode(text)

    for char in normalized:
        if char in unmappable:
            continue
        try:
            char.encode(codec)
        except (UnicodeEncodeError, LookupError):
            # Check if it has a look-alike
            if char not in LOOKALIKE_MAP and char not in ACCENT_FALLBACK_MAP:
                unmappable.append(char)

    return unmappable
