"""Exhaustive coverage of the packed PTQ1_0 digit lookup's byte domain."""

import re
import unittest
from pathlib import Path


class PTQDecodeTableTests(unittest.TestCase):
    def test_every_byte_preserves_the_five_base_three_digits(self):
        header = (
            Path(__file__).resolve().parents[3]
            / "runtime/metal/kernels/common/quant_formats.h"
        )
        source = header.read_text()
        match = re.search(r"quant_ptq10_digits\[256\]\s*=\s*\{([^}]*)\}", source)
        self.assertIsNotNone(match)
        values = [int(value) for value in re.findall(r"\d+", match[1])]
        self.assertEqual(len(values), 256)
        for byte, packed in enumerate(values):
            remaining, digits = byte, []
            for _ in range(5):
                remaining, digit = divmod(remaining, 3)
                digits.append(digit)
            expected = list(reversed(digits))
            actual = [(packed >> (2 * index)) & 3 for index in range(5)]
            self.assertEqual(actual, expected, f"packed byte {byte}")
            self.assertLessEqual(packed, 0x3FF)


if __name__ == "__main__":
    unittest.main()
