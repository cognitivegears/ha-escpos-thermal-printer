"""ESCPOS command parser for the virtual printer emulator."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class EscposCommandParser:
    """Parser for ESCPOS commands received by the virtual printer."""

    # ESCPOS command constants
    ESC = 0x1B  # ESC character
    GS = 0x1D   # GS character
    LF = 0x0A   # Line feed
    CR = 0x0D   # Carriage return

    def __init__(self) -> None:
        """Initialize the command parser."""
        self._buffer = bytearray()
        self._current_encoding = "cp437"  # Default encoding

    def parse_command(self, data: bytes) -> dict[str, Any] | None:
        """Parse ESCPOS command from raw data.

        When called with an empty bytes object, this still attempts to parse
        from any data already accumulated in the internal buffer. This allows
        callers to drain all pending commands by repeatedly invoking this
        method with empty input after an initial read.
        """
        # Add data to buffer when provided; otherwise, continue parsing the
        # already-buffered bytes.
        if data:
            self._buffer.extend(data)

        # Try to parse complete commands from buffer
        commands = []
        while self._buffer:
            command = self._parse_single_command()
            if command:
                commands.append(command)
            else:
                # No complete command found, keep remaining data in buffer
                break

        return commands[0] if commands else None

    def _parse_single_command(self) -> dict[str, Any] | None:
        """Parse a single command from the buffer."""
        if len(self._buffer) < 1:
            return None

        first_byte = self._buffer[0]

        if first_byte == self.ESC:
            return self._parse_esc_command()
        elif first_byte == self.GS:
            return self._parse_gs_command()
        elif first_byte == self.LF:
            return self._parse_simple_command("feed", 1)
        elif first_byte == self.CR:
            return self._parse_simple_command("carriage_return", 1)
        else:
            # Regular text data
            return self._parse_text_data()

    def _parse_esc_command(self) -> dict[str, Any] | None:
        """Parse ESC-prefixed commands."""
        if len(self._buffer) < 2:
            return None

        command_byte = self._buffer[1]

        if command_byte == ord('@'):
            # ESC @ - Initialize printer
            return self._parse_simple_command("initialize", 2)
        elif command_byte == ord('!'):
            # ESC ! n - Select print mode
            return self._parse_print_mode_command()
        elif command_byte == ord('-'):
            # ESC - n - Underline mode
            return self._parse_underline_command()
        elif command_byte == ord('a'):
            # ESC a n - Select justification
            return self._parse_justification_command()
        elif command_byte == ord('d'):
            # ESC d n - Print and feed n lines
            return self._parse_feed_command()
        elif command_byte == ord('i'):
            # ESC i - Partial cut
            return self._parse_simple_command("cut_partial", 2)
        elif command_byte == ord('m'):
            # ESC m - Full cut
            return self._parse_simple_command("cut_full", 2)
        elif command_byte == ord('t'):
            # ESC t n - Select character code table
            return self._parse_codepage_command()
        else:
            # Unknown ESC command, consume ESC and command byte
            self._buffer = self._buffer[2:]
            return None

    def _parse_gs_command(self) -> dict[str, Any] | None:
        """Parse GS-prefixed commands."""
        if len(self._buffer) < 2:
            return None

        command_byte = self._buffer[1]

        if command_byte == ord('V'):
            # GS V m - Cut paper
            return self._parse_cut_command()
        elif command_byte == ord('k'):
            # GS k m d1...dk - Print barcode
            return self._parse_barcode_command()
        elif command_byte == ord('('):
            # GS ( L pL pH m d1...dk - Image command
            return self._parse_image_command()
        elif command_byte == ord('H'):
            # GS H n - Select print position of HRI characters
            return self._parse_hri_position_command()
        elif command_byte == ord('f'):
            # GS f n - Select font for HRI characters
            return self._parse_hri_font_command()
        elif command_byte == ord('w'):
            # GS w n - Set barcode width
            return self._parse_barcode_width_command()
        elif command_byte == ord('h'):
            # GS h n - Set barcode height
            return self._parse_barcode_height_command()
        else:
            # Unknown GS command, consume GS and command byte
            self._buffer = self._buffer[2:]
            return None

    def _parse_simple_command(self, command_type: str, length: int) -> dict[str, Any] | None:
        """Parse a simple command with fixed length."""
        if len(self._buffer) < length:
            return None  # Insufficient data in buffer

        raw_data = bytes(self._buffer[:length])
        self._buffer = self._buffer[length:]

        return {
            'type': command_type,
            'raw_data': raw_data,
            'parameters': {}
        }

    def _parse_print_mode_command(self) -> dict[str, Any] | None:
        """Parse ESC ! n - Select print mode."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        # Parse print mode bits
        parameters = {
            'bold': bool(n & 0x08),
            'double_height': bool(n & 0x10),
            'double_width': bool(n & 0x20),
            'underline': bool(n & 0x80)
        }

        return {
            'type': 'print_mode',
            'raw_data': raw_data,
            'parameters': parameters
        }

    def _parse_underline_command(self) -> dict[str, Any] | None:
        """Parse ESC - n - Underline mode."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        underline_modes = {0: 'none', 1: 'single', 2: 'double'}

        return {
            'type': 'underline',
            'raw_data': raw_data,
            'parameters': {'mode': underline_modes.get(n, 'none')}
        }

    def _parse_justification_command(self) -> dict[str, Any] | None:
        """Parse ESC a n - Select justification."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        alignments = {0: 'left', 1: 'center', 2: 'right'}

        return {
            'type': 'alignment',
            'raw_data': raw_data,
            'parameters': {'alignment': alignments.get(n, 'left')}
        }

    def _parse_feed_command(self) -> dict[str, Any] | None:
        """Parse ESC d n - Print and feed n lines."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        return {
            'type': 'feed',
            'raw_data': raw_data,
            'parameters': {'lines': n}
        }

    def _parse_codepage_command(self) -> dict[str, Any] | None:
        """Parse ESC t n - Select character code table."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        # Map codepage numbers to encoding names
        codepages = {
            0: 'cp437', 1: 'cp932', 2: 'cp850', 3: 'cp860',
            4: 'cp863', 5: 'cp865', 16: 'cp1252', 17: 'cp866',
            18: 'cp852', 19: 'cp858'
        }

        encoding = codepages.get(n, 'cp437')
        self._current_encoding = encoding

        return {
            'type': 'codepage',
            'raw_data': raw_data,
            'parameters': {'codepage': n, 'encoding': encoding}
        }

    def _parse_cut_command(self) -> dict[str, Any] | None:
        """Parse GS V m - Cut paper."""
        if len(self._buffer) < 3:
            return None

        m = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        cut_modes = {65: 'partial', 66: 'full'}

        return {
            'type': 'cut',
            'raw_data': raw_data,
            'parameters': {'mode': cut_modes.get(m, 'full')}
        }

    def _parse_barcode_command(self) -> dict[str, Any] | None:
        """Parse GS k m d1...dk - Print barcode."""
        if len(self._buffer) < 4:
            return None

        m = self._buffer[2]  # Barcode type
        k = self._buffer[3]  # Data length

        total_length = 4 + k
        if len(self._buffer) < total_length:
            return None

        barcode_data = bytes(self._buffer[4:4+k])
        raw_data = bytes(self._buffer[:total_length])
        self._buffer = self._buffer[total_length:]

        return {
            'type': 'barcode',
            'raw_data': raw_data,
            'parameters': {
                'barcode_type': m,
                'data': barcode_data.decode(self._current_encoding, errors='ignore')
            }
        }

    def _parse_image_command(self) -> dict[str, Any] | None:
        """Parse GS ( L pL pH m d1...dk - Image command."""
        if len(self._buffer) < 6:
            return None

        pL = self._buffer[2]
        pH = self._buffer[3]
        m = self._buffer[4]

        # Calculate data length
        data_length = pL + (pH * 256)
        total_length = 5 + data_length

        if len(self._buffer) < total_length:
            return None

        image_data = bytes(self._buffer[5:5+data_length])
        raw_data = bytes(self._buffer[:total_length])
        self._buffer = self._buffer[total_length:]

        return {
            'type': 'image',
            'raw_data': raw_data,
            'parameters': {
                'function': m,
                'data_length': data_length,
                'image_data': image_data
            }
        }

    def _parse_hri_position_command(self) -> dict[str, Any] | None:
        """Parse GS H n - Select print position of HRI characters."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        positions = {0: 'not_printed', 1: 'above', 2: 'below', 3: 'both'}

        return {
            'type': 'hri_position',
            'raw_data': raw_data,
            'parameters': {'position': positions.get(n, 'below')}
        }

    def _parse_hri_font_command(self) -> dict[str, Any] | None:
        """Parse GS f n - Select font for HRI characters."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        fonts = {0: 'A', 1: 'B'}

        return {
            'type': 'hri_font',
            'raw_data': raw_data,
            'parameters': {'font': fonts.get(n, 'A')}
        }

    def _parse_barcode_width_command(self) -> dict[str, Any] | None:
        """Parse GS w n - Set barcode width."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        return {
            'type': 'barcode_width',
            'raw_data': raw_data,
            'parameters': {'width': max(2, min(6, n))}
        }

    def _parse_barcode_height_command(self) -> dict[str, Any] | None:
        """Parse GS h n - Set barcode height."""
        if len(self._buffer) < 3:
            return None

        n = self._buffer[2]
        raw_data = bytes(self._buffer[:3])
        self._buffer = self._buffer[3:]

        return {
            'type': 'barcode_height',
            'raw_data': raw_data,
            'parameters': {'height': max(1, min(255, n))}
        }

    def _parse_text_data(self) -> dict[str, Any] | None:
        """Parse regular text data."""
        # Find the next command or control character
        end_pos = 0
        for i, byte in enumerate(self._buffer):
            if byte in (self.ESC, self.GS, self.LF, self.CR):
                end_pos = i
                break
        else:
            end_pos = len(self._buffer)

        if end_pos == 0:
            return None

        text_data = bytes(self._buffer[:end_pos])
        self._buffer = self._buffer[end_pos:]

        try:
            text = text_data.decode(self._current_encoding)
        except UnicodeDecodeError:
            text = text_data.decode('latin-1')  # Fallback encoding

        return {
            'type': 'text',
            'raw_data': text_data,
            'parameters': {'text': text}
        }

    def clear_buffer(self) -> None:
        """Clear the internal buffer."""
        self._buffer.clear()
