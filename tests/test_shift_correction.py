#!/usr/bin/python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import InputBuffer, ShiftTapDetector  # noqa: E402


class TestInputBuffer(unittest.TestCase):
    def test_last_word_is_only_text_after_final_space(self):
        buffer = InputBuffer()
        buffer.buffer = [(30, False), (31, False), (57, False), (32, False), (33, False)]
        self.assertEqual(buffer.get_last_word(), [(32, False), (33, False)])

    def test_phrase_keeps_all_words(self):
        buffer = InputBuffer()
        buffer.buffer = [(30, False), (57, False), (31, False)]
        self.assertEqual(len(buffer.get_last_phrase()), 3)


class TestShiftTapDetector(unittest.TestCase):
    def test_two_taps_resolve_to_word_after_window(self):
        detector = ShiftTapDetector(delay=0.4)
        self.assertIsNone(detector.press(10.0))
        self.assertIsNone(detector.press(10.1))
        self.assertEqual(detector.flush(10.51), "word")

    def test_three_taps_resolve_to_phrase_immediately(self):
        detector = ShiftTapDetector(delay=0.4)
        detector.press(10.0)
        detector.press(10.1)
        self.assertEqual(detector.press(10.2), "phrase")

    def test_single_tap_does_not_trigger_correction(self):
        detector = ShiftTapDetector(delay=0.4)
        detector.press(10.0)
        self.assertIsNone(detector.flush(10.5))


if __name__ == "__main__":
    unittest.main()
