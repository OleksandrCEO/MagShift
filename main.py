#!/usr/bin/env python3
"""
SkySwitcher v0.3.0 (Architecture Rewrite)
Key-buffer based layout switcher. NO CLIPBOARD dependency.

Mechanism:
1. Passive recording of keystrokes + modifier states into a buffer.
2. On trigger: Delete text (Backspace * N) -> Switch Layout -> Replay keystrokes.
3. Result: The OS handles the character mapping logic naturally.

Benefits: Works in Terminals, Password fields, VIM, etc.
"""

import evdev
from evdev import UInput, ecodes as e
import time
import sys
import argparse
from collections import deque

# --- CONFIGURATION ---
TRIGGER_BTN = e.KEY_RIGHTSHIFT
DOUBLE_PRESS_DELAY = 0.5
LAYOUT_SWITCH_COMBO = [e.KEY_LEFTMETA, e.KEY_SPACE]

# Keys that constitute a "word" (letters, numbers, basic punctuation)
# We track these to know what to delete and replay.
PRINTABLE_KEYS = {
    e.KEY_1, e.KEY_2, e.KEY_3, e.KEY_4, e.KEY_5, e.KEY_6, e.KEY_7, e.KEY_8, e.KEY_9, e.KEY_0,
    e.KEY_MINUS, e.KEY_EQUAL, e.KEY_BACKSPACE,
    e.KEY_Q, e.KEY_W, e.KEY_E, e.KEY_R, e.KEY_T, e.KEY_Y, e.KEY_U, e.KEY_I, e.KEY_O, e.KEY_P,
    e.KEY_LEFTBRACE, e.KEY_RIGHTBRACE, e.KEY_BACKSLASH,
    e.KEY_A, e.KEY_S, e.KEY_D, e.KEY_F, e.KEY_G, e.KEY_H, e.KEY_J, e.KEY_K, e.KEY_L,
    e.KEY_SEMICOLON, e.KEY_APOSTROPHE,
    e.KEY_Z, e.KEY_X, e.KEY_C, e.KEY_V, e.KEY_B, e.KEY_N, e.KEY_M,
    e.KEY_COMMA, e.KEY_DOT, e.KEY_SLASH,
    e.KEY_GRAVE  # The `~ key
}

# Keys that should RESET the buffer (Word separators or navigation)
RESET_KEYS = {
    e.KEY_SPACE, e.KEY_ENTER, e.KEY_TAB, e.KEY_ESC,
    e.KEY_UP, e.KEY_DOWN, e.KEY_LEFT, e.KEY_RIGHT,
    e.KEY_HOME, e.KEY_END, e.KEY_PAGEUP, e.KEY_PAGEDOWN
}

IGNORED_KEYWORDS = [
    'mouse', 'webcam', 'audio', 'video', 'consumer',
    'control', 'headset', 'receiver', 'solaar', 'hotkeys'
]


def list_devices():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    devices.sort(key=lambda x: x.path)
    print(f"{'PATH':<20} | {'NAME'}")
    print("-" * 50)
    for dev in devices:
        print(f"{dev.path:<20} | {dev.name}")


def find_keyboard_device():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    possible_candidates = []

    for dev in devices:
        name = dev.name.lower()
        if any(bad in name for bad in IGNORED_KEYWORDS): continue
        if e.EV_KEY not in dev.capabilities(): continue

        keys = dev.capabilities()[e.EV_KEY]
        if {e.KEY_SPACE, e.KEY_ENTER, e.KEY_A, e.KEY_Z}.issubset(keys):
            if 'keyboard' in name or 'kbd' in name: return dev.path, dev.name
            possible_candidates.append((dev.path, dev.name))

    return possible_candidates[0] if possible_candidates else (None, None)


class SkySwitcher:
    def __init__(self, device_path, verbose=False):
        self.verbose = verbose

        # Buffer stores tuples: (key_code, is_shift_held)
        self.key_buffer = deque(maxlen=50)

        # State tracking
        self.last_press_time = 0
        self.shift_pressed = False

        # --- Device Setup ---
        try:
            self.dev = evdev.InputDevice(device_path)
            self.log(f"✅ Connected to: {self.dev.name}")
        except OSError as err:
            self.error(f"Failed to open device: {err}")
            sys.exit(1)

        # Virtual Keyboard for replaying
        try:
            self.ui = UInput(name="SkySwitcher-Virtual")
        except Exception as err:
            self.error(f"Failed to create UInput: {err}")
            sys.exit(1)

    def log(self, msg):
        if self.verbose: print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def error(self, msg):
        print(f"❌ {msg}", file=sys.stderr)

    def send_combo(self, *keys):
        """Simulate pressing a combination of keys."""
        for k in keys: self.ui.write(e.EV_KEY, k, 1)
        self.ui.syn()
        time.sleep(0.02)
        for k in reversed(keys): self.ui.write(e.EV_KEY, k, 0)
        self.ui.syn()
        time.sleep(0.02)

    def correct_last_word(self):
        """
        The Core Magic:
        1. Backspace existing word.
        2. Switch Layout.
        3. Replay keys from buffer.
        """
        if not self.key_buffer:
            self.log("Buffer empty, nothing to correct.")
            return

        word_len = len(self.key_buffer)
        self.log(f"⚡ Correcting word (length {word_len})...")

        # 1. Delete current text
        for _ in range(word_len):
            self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
            self.ui.syn()
            time.sleep(0.005)  # Super fast typing
            self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
            self.ui.syn()

        time.sleep(0.05)

        # 2. Switch System Layout
        self.send_combo(*LAYOUT_SWITCH_COMBO)
        time.sleep(0.1)  # Wait for OS to switch

        # 3. Replay Keys
        # We must replay them exactly as they were typed (preserving Shift state)
        for key_code, was_shifted in self.key_buffer:
            if was_shifted:
                self.ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
                self.ui.syn()

            self.ui.write(e.EV_KEY, key_code, 1)
            self.ui.syn()
            self.ui.write(e.EV_KEY, key_code, 0)
            self.ui.syn()

            if was_shifted:
                self.ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
                self.ui.syn()

            # Tiny delay to simulate natural typing flow (prevents missing chars)
            time.sleep(0.01)

        self.log("Done.")

    def run(self):
        self.log(f"🚀 SkySwitcher v0.3.0 (KeyBuffer Engine) running...")

        try:
            self.dev.grab()
            self.dev.ungrab()
        except IOError:
            self.log("⚠️  Device grabbed. Running passive.")

        for event in self.dev.read_loop():
            if event.type == e.EV_KEY:
                # --- 1. Track Shift State ---
                if event.code in [e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT]:
                    self.shift_pressed = (event.value == 1 or event.value == 2)
                    # Note: We don't return here, Right Shift also triggers logic below

                # --- 2. Logic for Key Down (value=1) ---
                if event.value == 1:

                    # A. Trigger Logic (Right Shift)
                    if event.code == TRIGGER_BTN:
                        now = time.time()
                        if now - self.last_press_time < DOUBLE_PRESS_DELAY:
                            # Double tap detected!
                            self.correct_last_word()
                            self.last_press_time = 0  # Reset timer

                            # Important: Clear buffer AFTER correction so we don't re-correct same thing
                            # Or strictly speaking, we just replayed it, so the buffer is technically valid
                            # for another layout switch?
                            # Let's clear it to be safe and avoid infinite loops or double types.
                            # Actually, Punto Switcher allows re-switching back.
                            # But for v0.3.0, let's clear to keep it simple.
                            # self.key_buffer.clear() -> No, let's keep it.
                            # If user double taps again, they might want to switch back!
                            # BUT: Replaying keys adds them to the OS buffer, but does it add to OUR listener?
                            # YES, uinput events usually feed back into /dev/input if not careful.
                            # However, we are reading from a SPECIFIC hardware device (self.dev).
                            # UInput writes to a Virtual Device.
                            # So our listener SHOULD NOT hear our own replayed keys.
                            # This is perfect. We can keep the buffer.
                            pass

                        else:
                            self.last_press_time = now

                    # B. Buffer Management
                    elif event.code in RESET_KEYS:
                        # User finished a word or moved cursor. Start fresh.
                        if self.verbose and len(self.key_buffer) > 0:
                            self.log("Buffer reset (Space/Nav).")
                        self.key_buffer.clear()
                        # Reset timer to prevent Shift + Space + Shift triggering
                        self.last_press_time = 0

                    elif event.code in PRINTABLE_KEYS:
                        if event.code == e.KEY_BACKSPACE:
                            if self.key_buffer:
                                self.key_buffer.pop()
                        else:
                            # Append (Key, ShiftState)
                            self.key_buffer.append((event.code, self.shift_pressed))

                        # Any typing invalidates the double-shift timer
                        self.last_press_time = 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SkySwitcher v0.3.0")
    parser.add_argument("-d", "--device", help="Path to input device")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--list", action="store_true", help="List available devices")

    args = parser.parse_args()

    if args.list:
        list_devices()
        sys.exit(0)

    path = args.device
    if not path:
        path, _ = find_keyboard_device()
        if not path:
            print("❌ Keyboard not found automatically. Use --list", file=sys.stderr)
            sys.exit(1)

    try:
        # Note: 'langs' argument removed as we rely on system layout switching now!
        SkySwitcher(path, args.verbose).run()
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
        sys.exit(0)