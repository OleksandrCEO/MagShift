#!/usr/bin/python3
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import InputBuffer, MAX_BUFFER_SIZE  # noqa: E402


class TestInputBuffer(unittest.TestCase):
    def test_long_phrase_is_kept_within_configured_buffer(self):
        buffer = InputBuffer()
        for code in [30] * 40:
            buffer.add(code, False)
        self.assertEqual(len(buffer.get_last_phrase()), 40)
        self.assertEqual(len(buffer.get_last_phrase()), MAX_BUFFER_SIZE if MAX_BUFFER_SIZE < 40 else 40)

    def test_space_is_part_of_phrase(self):
        buffer = InputBuffer()
        for code in [30, 31, 57, 32, 33, 34]:
            buffer.add(code, False)
        self.assertEqual(len(buffer.get_last_phrase()), 6)


if __name__ == "__main__":
    unittest.main()
