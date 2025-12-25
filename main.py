#!/usr/bin/env python3
"""
SkySwitcher - A minimal layout switcher for Linux/Wayland using evdev.
Detects double Right Shift presses to correct the last typed word.
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

# Layout mappings (QWERTY <-> JCUKEN)
# Row 1 to 4 mapping, ensuring 1:1 key correspondence
EN_LAYOUT = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./~@#$^&QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?"
UA_LAYOUT = "'йцукенгшщзхїфівапролджєячсмитьбю.₴\"№;%:?ЙЦУКЕНГШЩЗХЇФІВАПРОЛДЖЄЯЧСМИТЬБЮ,"
TRANS_MAP = str.maketrans(EN_LAYOUT + UA_LAYOUT, UA_LAYOUT + EN_LAYOUT)

IGNORED_DEVICE_NAMES = ['solaar', 'webcam', 'audio', 'video', 'mouse', 'consumer']


def find_keyboard_device():
    """
    Auto-detects a physical keyboard device.
    Filters out virtual devices, mice, and specific keywords like 'solaar'.
    """
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

    # Sort by path to ensure consistency
    devices.sort(key=lambda x: x.path)

    for dev in devices:
        name = dev.name.lower()

        # 1. Filter by name (ignore common non-keyboard devices)
        if any(ignore in name for ignore in IGNORED_DEVICE_NAMES):
            continue

        # 2. Check capabilities (must have EV_KEY)
        cap = dev.capabilities()
        if e.EV_KEY not in cap:
            continue

        keys = cap[e.EV_KEY]
        # 3. Must have specific keys (Space, Enter, A, Z) to be a typing keyboard
        required_keys = {e.KEY_SPACE, e.KEY_ENTER, e.KEY_A, e.KEY_Z}
        if required_keys.issubset(keys):
            return dev.path, dev.name

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

        # Initialize virtual keyboard for sending keystrokes
        try:
            self.ui = UInput({
                e.EV_KEY: [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_C, e.KEY_V,
                           e.KEY_LEFT, e.KEY_BACKSPACE, e.KEY_INSERT, TRIGGER_KEY]
            }, name="SkySwitcher-Virtual")
        except Exception as err:
            self.error(f"Failed to create UInput device: {err}")
            self.error("Ensure the user has permissions for /dev/uinput (check README).")
            sys.exit(1)

        self.last_press_time = 0

    def log(self, msg):
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def error(self, msg):
        print(f"❌ {msg}", file=sys.stderr)

    def clipboard_action(self, action, text=None):
        """Handles clipboard read/write using wl-clipboard"""
        try:
            if action == 'read':
                res = subprocess.run(['wl-paste', '-n'], capture_output=True, text=True)
                return res.stdout
            elif action == 'write' and text is not None:
                p = subprocess.Popen(['wl-copy', '-n'], stdin=subprocess.PIPE, text=True)
                p.communicate(input=text)
        except FileNotFoundError:
            self.error("wl-clipboard not found. Please install it.")
        except Exception as err:
            self.error(f"Clipboard error: {err}")
        return ""

    def send_combo(self, *keys):
        """Simulates a key combination"""
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

        # 1. Release the physical modifier logically to prevent interference
        self.ui.write(e.EV_KEY, TRIGGER_KEY, 0)
        self.ui.syn()
        time.sleep(0.05)

        # 2. Select last word (Ctrl + Shift + Left)
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_LEFT)

        # 3. Copy (Ctrl + C)
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_C)
        time.sleep(0.1)  # Wait for Wayland clipboard sync

        # 4. Process Text
        original = self.clipboard_action('read')
        if not original:
            self.log("Clipboard empty, aborting.")
            return

        converted = original.translate(TRANS_MAP)
        if original == converted:
            self.log("No layout changes detected.")
            return

        self.log(f"Correcting: '{original}' -> '{converted}'")
        self.clipboard_action('write', converted)
        time.sleep(0.1)

        # 5. Replace (Backspace -> Ctrl + V)
        self.send_combo(e.KEY_BACKSPACE)
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_V)

    def run(self):
        self.log(f"🚀 Running... Double tap [Right Shift] to switch.")

        for event in self.dev.read_loop():
            if event.type == e.EV_KEY and event.code == TRIGGER_KEY:
                if event.value == 1:  # Key Down
                    now = time.time()
                    if now - self.last_press_time < DOUBLE_PRESS_DELAY:
                        self.perform_switch()
                        self.last_press_time = 0  # Reset
                    else:
                        self.last_press_time = now


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SkySwitcher: Linux Wayland Layout Switcher")
    parser.add_argument("-d", "--device", help="Path to input device (e.g. /dev/input/event3)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    device_path = args.device
    if not device_path:
        found_path, found_name = find_keyboard_device()
        if found_path:
            device_path = found_path
        else:
            print("❌ No suitable keyboard found automatically.", file=sys.stderr)
            print("   Please use --device /dev/input/eventX", file=sys.stderr)
            sys.exit(1)

    app = SkySwitcher(device_path, verbose=args.verbose)
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nStopped.")