#!/usr/bin/python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import InputBuffer, ShiftTapDetector  # noqa: E402


class TestInputBuffer(unittest.TestCase):
    def test_last_word_is_only_text_after_final_space(self):
        buffer = InputBuffer()
        buffer.buffer = [(30, False), (44, False), (57, False), (48, False)]
        self.assertEqual(buffer.get_last_word(), [(48, False)])

    def test_last_word_empty_after_trailing_space(self):
        buffer = InputBuffer()
        buffer.buffer = [(30, False), (57, False)]
        self.assertEqual(buffer.get_last_word(), [])


class TestShiftTapDetector(unittest.TestCase):
    def test_double_tap_resolves_to_word_after_timeout(self):
        detector = ShiftTapDetector(delay=0.4)
        detector.press(10.0)
        detector.release()
        detector.press(10.1)
        detector.release()
        self.assertIsNone(detector.flush(10.3))
        self.assertEqual(detector.flush(10.51), "word")

    def test_triple_tap_resolves_to_phrase_immediately(self):
        detector = ShiftTapDetector(delay=0.4)
        detector.press(10.0)
        detector.release()
        detector.press(10.1)
        detector.release()
        self.assertEqual(detector.press(10.2), "phrase")
        detector.release()
        self.assertIsNone(detector.flush(10.8))

    def test_single_tap_expires_without_action(self):
        detector = ShiftTapDetector(delay=0.4)
        detector.press(10.0)
        detector.release()
        self.assertIsNone(detector.flush(10.5))


if __name__ == "__main__":
    unittest.main()
