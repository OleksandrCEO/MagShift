#!/usr/bin/env python3
"""
SkySwitcher v0.5
- Improved device filtering (blocks solaar).
- Smart clipboard waiting (no fixed sleeps).
- Switches system layout after correction (Meta+Space).
"""

import evdev
from evdev import UInput, ecodes as e
import subprocess
import time
import sys
import argparse

# --- Configuration ---
TRIGGER_KEY = e.KEY_RIGHTSHIFT
DOUBLE_PRESS_DELAY = 0.5

# Keys to switch system layout after correction
# Standard for KDE/Gnome/Win11 is Meta (Win) + Space
# If you use Alt+Shift, change to: [e.KEY_LEFTALT, e.KEY_LEFTSHIFT]
LAYOUT_SWITCH_COMBO = [e.KEY_LEFTMETA, e.KEY_SPACE]

# --- Layout Mappings ---
EN_LAYOUT = "`qwertyuiop[]\\asdfghjkl;'zxcvbnm,./~@#$^&QWERTYUIOP{}|ASDFGHJKL:\"ZXCVBNM<>?"
UA_LAYOUT = "'йцукенгшщзхїґфівапролджєячсмитьбю.₴\"№;%:?ЙЦУКЕНГШЩЗХЇҐФІВАПРОЛДЖЄЯЧСМИТЬБЮ,"
TRANS_MAP = str.maketrans(EN_LAYOUT + UA_LAYOUT, UA_LAYOUT + EN_LAYOUT)

# Blacklist for device names
IGNORED_KEYWORDS = [
    'mouse', 'webcam', 'audio', 'video', 'consumer',
    'control', 'headset', 'receiver', 'solaar', 'hotkeys'
]


def list_devices():
    """Prints all available input devices for debugging."""
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    devices.sort(key=lambda x: x.path)

    print(f"{'PATH':<20} | {'NAME'}")
    print("-" * 50)
    for dev in devices:
        print(f"{dev.path:<20} | {dev.name}")


def find_keyboard_device():
    """Auto-detects a physical keyboard, strictly filtering junk."""
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    possible_candidates = []

    for dev in devices:
        name = dev.name.lower()

        # 1. Strict Negative Filter
        if any(bad_word in name for bad_word in IGNORED_KEYWORDS):
            continue

        # 2. Capability Check
        cap = dev.capabilities()
        if e.EV_KEY not in cap:
            continue

        keys = cap[e.EV_KEY]
        required_keys = {e.KEY_SPACE, e.KEY_ENTER, e.KEY_A, e.KEY_Z}

        if required_keys.issubset(keys):
            # Priority match
            if 'keyboard' in name or 'kbd' in name:
                return dev.path, dev.name

            # Fallback match
            possible_candidates.append((dev.path, dev.name))

    if possible_candidates:
        return possible_candidates[0]

    return None, None


class SkySwitcher:
    def __init__(self, device_path, verbose=False):
        self.verbose = verbose

        try:
            self.dev = evdev.InputDevice(device_path)
            self.log(f"✅ Connected to: {self.dev.name} ({device_path})")
        except OSError as err:
            self.error(f"Failed to open device {device_path}: {err}")
            sys.exit(1)

        # Register keys for Virtual Keyboard
        # We must declare ALL keys we plan to press
        all_keys = [
                       e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_C, e.KEY_V,
                       e.KEY_LEFT, e.KEY_BACKSPACE, e.KEY_INSERT,
                       TRIGGER_KEY
                   ] + LAYOUT_SWITCH_COMBO

        try:
            self.ui = UInput({e.EV_KEY: all_keys}, name="SkySwitcher-Virtual")
        except Exception as err:
            self.error(f"Failed to create UInput device: {err}")
            sys.exit(1)

        self.last_press_time = 0

    def log(self, msg):
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def error(self, msg):
        print(f"❌ {msg}", file=sys.stderr)

    def get_clipboard(self):
        try:
            res = subprocess.run(['wl-paste', '-n'], capture_output=True, text=True)
            return res.stdout
        except Exception:
            return ""

    def set_clipboard(self, text):
        try:
            p = subprocess.Popen(['wl-copy', '-n'], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text)
        except Exception:
            pass

    def send_combo(self, *keys):
        """Simulate pressing a combination of keys."""
        for k in keys:
            self.ui.write(e.EV_KEY, k, 1)
        self.ui.syn()
        time.sleep(0.02)  # Tiny delay for OS to register KeyDown
        for k in reversed(keys):
            self.ui.write(e.EV_KEY, k, 0)
        self.ui.syn()
        time.sleep(0.02)  # Tiny delay after KeyUp

    def wait_for_clipboard_change(self, old_content, timeout=0.5):
        """Polls clipboard until it changes or timeout expires."""
        start = time.time()
        while time.time() - start < timeout:
            new_content = self.get_clipboard()
            if new_content != old_content:
                return new_content
            time.sleep(0.02)  # Check every 20ms
        return None

    def perform_switch(self):
        self.log("Double press detected. Switching...")

        # 0. Reset Trigger Key (logically release Shift)
        self.ui.write(e.EV_KEY, TRIGGER_KEY, 0)
        self.ui.syn()
        time.sleep(0.05)

        # 1. Capture current state (for smart wait)
        prev_clipboard = self.get_clipboard()

        # 2. Select last word & Copy
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_LEFT)
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_C)

        # 3. Smart Wait for Clipboard
        original = self.wait_for_clipboard_change(prev_clipboard)

        if not original:
            self.log("Clipboard didn't change (timeout or empty selection). Aborting.")
            # Optional: deselect text here if needed (Right Arrow)
            return

        # 4. Translate
        converted = original.translate(TRANS_MAP)
        if original == converted:
            self.log("No transliteration needed.")
            return

        self.log(f"Correcting: '{original}' -> '{converted}'")

        # 5. Write new text to clipboard
        self.set_clipboard(converted)
        # Give a moment for wl-copy to finish writing
        time.sleep(0.05)

        # 6. Replace text (Backspace -> Paste)
        self.send_combo(e.KEY_BACKSPACE)
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_V)

        # 7. Switch System Layout (Meta + Space)
        self.log("Switching system layout...")
        time.sleep(0.1)  # Small delay to ensure Paste is done
        self.send_combo(*LAYOUT_SWITCH_COMBO)

    def run(self):
        self.log(f"🚀 Running... Double tap [Right Shift] to switch.")

        try:
            self.dev.grab()
            self.dev.ungrab()
        except IOError:
            self.log("⚠️  Warning: Device grabbed by another process. Passive mode.")

        for event in self.dev.read_loop():
            if event.type == e.EV_KEY and event.code == TRIGGER_KEY:
                if event.value == 1:
                    now = time.time()
                    if now - self.last_press_time < DOUBLE_PRESS_DELAY:
                        self.perform_switch()
                        self.last_press_time = 0
                    else:
                        self.last_press_time = now


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", help="Path to input device")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable logging")
    parser.add_argument("--list", action="store_true", help="List devices")

    args = parser.parse_args()

    if args.list:
        list_devices()
        sys.exit(0)

    device_path = args.device
    if not device_path:
        found_path, found_name = find_keyboard_device()
        if found_path:
            device_path = found_path
        else:
            print("❌ No suitable keyboard found.", file=sys.stderr)
            print("   Use --list to check device names.", file=sys.stderr)
            sys.exit(1)

    app = SkySwitcher(device_path, verbose=args.verbose)
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nStopped.")