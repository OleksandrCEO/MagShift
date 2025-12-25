#!/usr/bin/env python3
"""
SkySwitcher v0.0.4
A minimalist layout switcher for Linux/Wayland using evdev.
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

# --- Layout Mappings (Updated) ---
# Added backslash (\) -> ґ and pipe (|) -> Ґ
# Note: '\\' represents a single backslash character
EN_LAYOUT = "`qwertyuiop[]\\asdfghjkl;'zxcvbnm,./~@#$^&QWERTYUIOP{}|ASDFGHJKL:\"ZXCVBNM<>?"
UA_LAYOUT = "'йцукенгшщзхїґфівапролджєячсмитьбю.₴\"№;%:?ЙЦУКЕНГШЩЗХЇҐФІВАПРОЛДЖЄЯЧСМИТЬБЮ,"

TRANS_MAP = str.maketrans(EN_LAYOUT + UA_LAYOUT, UA_LAYOUT + EN_LAYOUT)

# Words to ignore during auto-detection
IGNORED_KEYWORDS = ['mouse', 'webcam', 'audio', 'video', 'consumer', 'control', 'headset', 'receiver']


def list_devices():
    """Prints all available input devices for debugging."""
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    devices.sort(key=lambda x: x.path)

    print(f"{'PATH':<20} | {'NAME'}")
    print("-" * 50)
    for dev in devices:
        print(f"{dev.path:<20} | {dev.name}")


def find_keyboard_device():
    """
    Auto-detects a physical keyboard.
    """
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    possible_candidates = []

    for dev in devices:
        name = dev.name.lower()

        # Filter junk
        if any(bad_word in name for bad_word in IGNORED_KEYWORDS):
            continue

        # Check capabilities
        cap = dev.capabilities()
        if e.EV_KEY not in cap:
            continue

        keys = cap[e.EV_KEY]
        # Must have basic typing keys
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

        try:
            # Added KEY_BACKSLASH and KEY_LEFTSHIFT explicitly just in case needed for macros
            self.ui = UInput({
                e.EV_KEY: [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_C, e.KEY_V,
                           e.KEY_LEFT, e.KEY_BACKSPACE, e.KEY_INSERT, TRIGGER_KEY]
            }, name="SkySwitcher-Virtual")
        except Exception as err:
            self.error(f"Failed to create UInput device: {err}")
            sys.exit(1)

        self.last_press_time = 0

    def log(self, msg):
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def error(self, msg):
        print(f"❌ {msg}", file=sys.stderr)

    def clipboard_action(self, action, text=None):
        try:
            if action == 'read':
                res = subprocess.run(['wl-paste', '-n'], capture_output=True, text=True)
                return res.stdout
            elif action == 'write' and text is not None:
                p = subprocess.Popen(['wl-copy', '-n'], stdin=subprocess.PIPE, text=True)
                p.communicate(input=text)
        except Exception:
            pass
        return ""

    def send_combo(self, *keys):
        for k in keys:
            self.ui.write(e.EV_KEY, k, 1)
        self.ui.syn()
        time.sleep(0.02)
        for k in reversed(keys):
            self.ui.write(e.EV_KEY, k, 0)
        self.ui.syn()
        time.sleep(0.02)

    def perform_switch(self):
        self.log("Double press detected. Switching...")

        # Release logical trigger
        self.ui.write(e.EV_KEY, TRIGGER_KEY, 0)
        self.ui.syn()
        time.sleep(0.05)

        # Select last word
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_LEFT)
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_C)
        time.sleep(0.1)

        original = self.clipboard_action('read')
        if not original:
            return

        converted = original.translate(TRANS_MAP)
        if original == converted:
            return

        self.log(f"Correcting: '{original}' -> '{converted}'")
        self.clipboard_action('write', converted)
        time.sleep(0.1)

        self.send_combo(e.KEY_BACKSPACE)
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_V)

    def run(self):
        self.log(f"🚀 Running... Double tap [Right Shift] to switch.")

        try:
            self.dev.grab()
            self.dev.ungrab()
        except IOError:
            self.log("⚠️  Warning: Device is grabbed by another process (maybe X11/Wayland). Using passively.")

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
    parser = argparse.ArgumentParser(description="SkySwitcher: Linux Wayland Layout Switcher")
    parser.add_argument("-d", "--device", help="Path to input device (e.g. /dev/input/event3)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--list", action="store_true", help="List all detected input devices and exit")

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
            print("❌ No suitable keyboard found automatically.", file=sys.stderr)
            print("   Run with --list to see available devices.", file=sys.stderr)
            sys.exit(1)

    app = SkySwitcher(device_path, verbose=args.verbose)
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nStopped.")