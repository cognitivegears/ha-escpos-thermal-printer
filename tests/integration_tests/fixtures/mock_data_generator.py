"""Mock data generator for ESCPOS integration testing."""

from __future__ import annotations

import random
import string
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont, ImageFont as PILImageFont


class MockDataGenerator:
    """Generates realistic mock data for testing ESCPOS printer integration."""

    @staticmethod
    def generate_text_content(length: int = 50, include_special: bool = False) -> str:
        """Generate random text content for testing."""
        if include_special:
            chars = string.ascii_letters + string.digits + string.punctuation + " \n"
        else:
            chars = string.ascii_letters + string.digits + " \n"

        # Generate paragraphs with some structure
        words = []
        for _ in range(length // 5):  # Approximate words
            word_length = random.randint(3, 10)
            word = ''.join(random.choice(chars.replace('\n', '')) for _ in range(word_length))
            words.append(word)

        # Add some line breaks to simulate realistic text
        text = ' '.join(words)
        lines = text.split(' ')
        result = []
        line_length = 0

        for word in lines:
            if line_length + len(word) > 40:  # Approximate line length
                result.append('\n')
                line_length = 0
            result.append(word)
            line_length += len(word) + 1

        return ' '.join(result)

    @staticmethod
    def generate_qr_data() -> str:
        """Generate realistic QR code data."""
        qr_options = [
            "https://example.com",
            "https://github.com/user/repo",
            "WIFI:S:MyNetwork;T:WPA;P:mypassword;;",
            "mailto:user@example.com",
            "tel:+1234567890",
            "BEGIN:VCARD\nVERSION:3.0\nFN:John Doe\nTEL:+1234567890\nEND:VCARD",
            "https://maps.google.com/?q=New+York",
            "bitcoin:1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
            "otpauth://totp/Example:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Example"
        ]
        return random.choice(qr_options)

    @staticmethod
    def generate_barcode_data(barcode_type: str = "CODE128") -> str:
        """Generate realistic barcode data based on type."""
        if barcode_type.upper() == "CODE128":
            # Code 128 can encode full ASCII
            return ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        elif barcode_type.upper() == "EAN13":
            # EAN-13 format
            return ''.join(random.choices(string.digits, k=12)) + MockDataGenerator._calculate_ean13_check_digit(''.join(random.choices(string.digits, k=12)))
        elif barcode_type.upper() == "UPCA":
            # UPC-A format
            return ''.join(random.choices(string.digits, k=11)) + MockDataGenerator._calculate_upca_check_digit(''.join(random.choices(string.digits, k=11)))
        else:
            # Generic fallback
            return ''.join(random.choices(string.digits, k=10))

    @staticmethod
    def _calculate_ean13_check_digit(data: str) -> str:
        """Calculate EAN-13 check digit."""
        if len(data) != 12:
            return '0'

        # EAN-13 check digit calculation
        total = 0
        for i, digit in enumerate(data):
            multiplier = 3 if i % 2 == 0 else 1
            total += int(digit) * multiplier

        check_digit = (10 - (total % 10)) % 10
        return str(check_digit)

    @staticmethod
    def _calculate_upca_check_digit(data: str) -> str:
        """Calculate UPC-A check digit."""
        if len(data) != 11:
            return '0'

        # UPC-A check digit calculation (similar to EAN-13 but different weighting)
        total = 0
        for i, digit in enumerate(data):
            multiplier = 3 if i % 2 == 1 else 1  # Note: different from EAN-13
            total += int(digit) * multiplier

        check_digit = (10 - (total % 10)) % 10
        return str(check_digit)

    @staticmethod
    def generate_test_image(width: int = 200, height: int = 100,
                           format_type: str = "receipt") -> Image.Image:
        """Generate a test image for printing."""
        # Create a new image with white background
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)

        font: FreeTypeFont | PILImageFont
        try:
            # Try to use a default font
            font = ImageFont.truetype("arial.ttf", 20)
        except OSError:
            # Fallback to default font
            font = ImageFont.load_default()

        if format_type == "receipt":
            # Generate a receipt-like image
            draw.text((10, 10), "TEST RECEIPT", fill='black', font=font)
            draw.text((10, 35), f"Date: {random.randint(1, 12):02d}/{random.randint(1, 28):02d}/2024", fill='black', font=font)
            draw.text((10, 60), f"Amount: ${random.randint(10, 999):.2f}", fill='black', font=font)

            # Add some random lines
            for i in range(3):
                y_pos = 85 + i * 15
                line_text = MockDataGenerator.generate_text_content(20)
                draw.text((10, y_pos), line_text[:30], fill='black', font=font)

        elif format_type == "logo":
            # Generate a simple logo-like image
            # Draw a border
            draw.rectangle([5, 5, width-5, height-5], outline='black', width=2)

            # Draw some geometric shapes
            draw.ellipse([width//2-20, height//2-20, width//2+20, height//2+20], fill='blue')
            draw.rectangle([20, 20, 60, 60], fill='red')
            draw.polygon([(width-60, 20), (width-20, 20), (width-40, 60)], fill='green')

        elif format_type == "qr_placeholder":
            # Generate an image with QR code placeholder
            draw.rectangle([10, 10, width-10, height-10], outline='black', width=1)
            draw.text((width//2-40, height//2-10), "QR CODE", fill='black', font=font)
            draw.text((width//2-60, height//2+10), "PLACEHOLDER", fill='black', font=font)

        else:
            # Random pattern
            for _ in range(20):
                x1 = random.randint(0, width)
                y1 = random.randint(0, height)
                x2 = random.randint(0, width)
                y2 = random.randint(0, height)
                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                draw.line([x1, y1, x2, y2], fill=color, width=2)

        return img

    @staticmethod
    def generate_print_job_data(job_type: str) -> dict[str, Any]:
        """Generate complete print job data for testing."""
        if job_type == "text":
            return {
                'type': 'print_text',
                'data': {
                    'text': MockDataGenerator.generate_text_content(100),
                    'align': random.choice(['left', 'center', 'right']),
                    'bold': random.choice([True, False]),
                    'underline': random.choice(['none', 'single', 'double']),
                    'width': random.choice(['normal', 'double', 'triple']),
                    'height': random.choice(['normal', 'double', 'triple']),
                    'encoding': random.choice(['cp437', 'cp850', 'cp1252']),
                    'feed': random.randint(0, 5),
                    'cut': random.choice(['none', 'full', 'partial'])
                }
            }

        elif job_type == "qr":
            return {
                'type': 'print_qr',
                'data': {
                    'data': MockDataGenerator.generate_qr_data(),
                    'size': random.randint(1, 16),
                    'ec': random.choice(['L', 'M', 'Q', 'H']),
                    'align': random.choice(['left', 'center', 'right']),
                    'feed': random.randint(0, 3),
                    'cut': random.choice(['none', 'full', 'partial'])
                }
            }

        elif job_type == "barcode":
            barcode_types = ['CODE128', 'EAN13', 'UPCA']
            selected_type = random.choice(barcode_types)
            return {
                'type': 'print_barcode',
                'data': {
                    'code': MockDataGenerator.generate_barcode_data(selected_type),
                    'bc': selected_type,
                    'height': random.randint(1, 255),
                    'width': random.randint(2, 6),
                    'pos': random.choice(['ABOVE', 'BELOW', 'BOTH', 'OFF']),
                    'font': random.choice(['A', 'B']),
                    'align_ct': random.choice([True, False]),
                    'check': random.choice([True, False]),
                    'align': random.choice(['left', 'center', 'right']),
                    'feed': random.randint(0, 3),
                    'cut': random.choice(['none', 'full', 'partial'])
                }
            }

        elif job_type == "image":
            return {
                'type': 'print_image',
                'data': {
                    'image': 'test_image.png',  # Would be generated separately
                    'high_density': random.choice([True, False]),
                    'align': random.choice(['left', 'center', 'right']),
                    'feed': random.randint(0, 3),
                    'cut': random.choice(['none', 'full', 'partial'])
                }
            }

        else:
            return {
                'type': 'feed',
                'data': {
                    'lines': random.randint(1, 10)
                }
            }

    @staticmethod
    def generate_automation_config(trigger_type: str = "state") -> dict[str, Any]:
        """Generate realistic automation configuration for testing."""
        if trigger_type == "state":
            return {
                'id': f'test_automation_{random.randint(1000, 9999)}',
                'alias': 'Test Print Automation',
                'trigger': {
                    'platform': 'state',
                    'entity_id': f'sensor.test_sensor_{random.randint(1, 100)}',
                    'from': 'off',
                    'to': 'on'
                },
                'condition': [],
                'action': {
                    'service': 'escpos_printer.print_text',
                    'data': {
                        'text': MockDataGenerator.generate_text_content(30),
                        'align': 'center'
                    }
                }
            }

        elif trigger_type == "time":
            return {
                'id': f'test_automation_{random.randint(1000, 9999)}',
                'alias': 'Scheduled Print',
                'trigger': {
                    'platform': 'time',
                    'at': f'{random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00'
                },
                'condition': [],
                'action': {
                    'service': 'escpos_printer.print_qr',
                    'data': {
                        'data': MockDataGenerator.generate_qr_data(),
                        'size': 6
                    }
                }
            }

        else:
            # Event trigger
            return {
                'id': f'test_automation_{random.randint(1000, 9999)}',
                'alias': 'Event Print',
                'trigger': {
                    'platform': 'event',
                    'event_type': 'test_print_event'
                },
                'condition': [],
                'action': {
                    'service': 'escpos_printer.print_barcode',
                    'data': {
                        'code': MockDataGenerator.generate_barcode_data(),
                        'bc': 'CODE128'
                    }
                }
            }

    @staticmethod
    def generate_notification_data() -> dict[str, Any]:
        """Generate realistic notification data for testing."""
        return {
            'message': MockDataGenerator.generate_text_content(50),
            'title': f"Test Notification {random.randint(1, 100)}",
            'target': 'escpos_printer'
        }

    @staticmethod
    def generate_error_scenario() -> dict[str, Any]:
        """Generate error scenario data for testing."""
        error_types = ['offline', 'paper_out', 'timeout', 'connection_error']
        error_type = random.choice(error_types)

        return {
            'error_type': error_type,
            'trigger_after': random.randint(1, 10),  # commands or seconds
            'duration': random.randint(5, 30),  # seconds
            'recovery_type': random.choice(['auto', 'manual'])
        }
