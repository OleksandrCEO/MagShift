#!/usr/bin/env python3
"""
SkySwitcher v0.4.0
Merged functionality:
- Core Logic: Robust v0.3.8 architecture (Reliable clipboard, no sudo hacks).
- CLI Features: Restored v0.2.1 arguments (--list, --device, --verbose).
"""

import sys
import time
import logging
import subprocess
import argparse
from evdev import InputDevice, UInput, ecodes as e, list_devices

# --- Configuration ---
VERSION = "0.4.0"
DOUBLE_PRESS_DELAY = 0.5
LAYOUT_SWITCH_COMBO = [e.KEY_LEFTMETA, e.KEY_SPACE]


# --- Logging Setup ---
class EmojiFormatter(logging.Formatter):
    def format(self, record):
        log_time = time.strftime("%H:%M:%S", time.localtime(record.created))
        return f"[{log_time}] {record.getMessage()}"


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(EmojiFormatter())
logger = logging.getLogger("SkySwitcher")
logger.addHandler(handler)
# Note: Level is set in __main__ based on arguments

# --- Layout Database ---
LAYOUT_US = "`qwertyuiop[]\\asdfghjkl;'zxcvbnm,./~@#$%^&QWERTYUIOP{}|ASDFGHJKL:\"ZXCVBNM<>?"
LAYOUT_UA = "'йцукенгшщзхїґфівапролджєячсмитьбю.₴\"№;%:?ЙЦУКЕНГШЩЗХЇҐФІВАПРОЛДЖЄЯЧСМИТЬБЮ,"
LAYOUTS_DB = {
    'us': LAYOUT_US,
    'ua': LAYOUT_UA,
}


class DeviceManager:
    IGNORED_KEYWORDS = [
        'mouse', 'webcam', 'audio', 'video', 'consumer',
        'control', 'headset', 'receiver', 'solaar', 'hotkeys',
        'button', 'switch', 'hda', 'dock'
    ]
    REQUIRED_KEYS = {e.KEY_SPACE, e.KEY_ENTER, e.KEY_A, e.KEY_Z}

    @staticmethod
    def list_available():
        """Prints all available input devices for debugging."""
        devices = []
        try:
            devices = [InputDevice(path) for path in list_devices()]
        except OSError:
            print("❌ Failed to list devices. Check permissions.", file=sys.stderr)
            return

        devices.sort(key=lambda x: x.path)
        print(f"{'PATH':<20} | {'NAME'}")
        print("-" * 60)
        for dev in devices:
            print(f"{dev.path:<20} | {dev.name}")

    @staticmethod
    def find_keyboard() -> InputDevice:
        devices = []
        try:
            devices = [InputDevice(path) for path in list_devices()]
        except OSError:
            logger.error(
                "❌ Failed to list devices. Do you have permission? (Try adding user to 'input' group or use sudo)")
            sys.exit(1)

        devices.sort(key=lambda x: x.path)
        possible_candidates = []

        for dev in devices:
            name_lower = dev.name.lower()
            if any(bad in name_lower for bad in DeviceManager.IGNORED_KEYWORDS): continue
            if e.EV_KEY not in dev.capabilities(): continue

            supported_keys = set(dev.capabilities()[e.EV_KEY])
            if DeviceManager.REQUIRED_KEYS.issubset(supported_keys):
                if 'keyboard' in name_lower or 'kbd' in name_lower:
                    logger.info(f"✅ Auto-detected: {dev.name}")
                    return dev
                possible_candidates.append(dev)

        if possible_candidates:
            logger.info(f"✅ Auto-detected (best guess): {possible_candidates[0].name}")
            return possible_candidates[0]

        logger.error("❌ No suitable keyboard found! Use --list to find it manually.")
        sys.exit(1)


class TextProcessor:
    def __init__(self):
        self.src_chars = LAYOUTS_DB['us']
        self.dst_chars = LAYOUTS_DB['ua']
        self.map_src_to_dst = str.maketrans(self.src_chars, self.dst_chars)
        self.map_dst_to_src = str.maketrans(self.dst_chars, self.src_chars)
        self.src_unique = set(self.src_chars) - set(self.dst_chars)
        self.dst_unique = set(self.dst_chars) - set(self.src_chars)
        logger.info(f"🌍 Languages: US <-> UA")

    def smart_translate(self, text):
        src_score = sum(1 for c in text if c in self.src_unique)
        dst_score = sum(1 for c in text if c in self.dst_unique)
        if src_score >= dst_score:
            return text.translate(self.map_src_to_dst)
        return text.translate(self.map_dst_to_src)


class SkySwitcher:
    def __init__(self, device_path=None):
        # Device Selection Logic
        if device_path:
            try:
                self.device = InputDevice(device_path)
                logger.info(f"✅ Manual Device: {self.device.name}")
            except OSError as err:
                logger.error(f"❌ Failed to open {device_path}: {err}")
                sys.exit(1)
        else:
            self.device = DeviceManager.find_keyboard()

        # Virtual Input Setup
        self.uinput_keys = [
            e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_RIGHTCTRL, e.KEY_RIGHTSHIFT,
            e.KEY_C, e.KEY_V, e.KEY_LEFT, e.KEY_RIGHT, e.KEY_BACKSPACE,
            e.KEY_HOME, e.KEY_LEFTMETA, e.KEY_SPACE, e.KEY_LEFTALT
        ]

        self.ui = None
        try:
            self.ui = UInput({e.EV_KEY: self.uinput_keys}, name="SkySwitcher-Virtual")
        except OSError:
            logger.error("❌ Failed to create UInput device. Check permissions for /dev/uinput.")
            sys.exit(1)

        self.processor = TextProcessor()
        self.last_press_time = 0
        self.modifier_down = False

        self.trigger_btn = e.KEY_RIGHTSHIFT
        self.mode2_modifier = e.KEY_RIGHTCTRL

    def send_combo(self, *keys):
        for k in keys: self.ui.write(e.EV_KEY, k, 1)
        self.ui.syn()
        time.sleep(0.02)
        for k in reversed(keys): self.ui.write(e.EV_KEY, k, 0)
        self.ui.syn()
        time.sleep(0.02)

    def release_all_modifiers(self):
        modifiers = [e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT, e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL, e.KEY_LEFTALT]
        for key in modifiers:
            self.ui.write(e.EV_KEY, key, 0)
        self.ui.syn()
        time.sleep(0.05)

    def get_clipboard(self):
        try:
            return subprocess.run(['wl-paste', '-n'], capture_output=True, text=True).stdout
        except:
            return ""

    def set_clipboard(self, text):
        try:
            p = subprocess.Popen(['wl-copy', '-n'], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text)
        except:
            pass

    def wait_for_new_content(self, timeout=0.5):
        start = time.time()
        while time.time() - start < timeout:
            content = self.get_clipboard()
            if content: return content
            time.sleep(0.02)
        return None

    def process_correction(self, mode="last_word"):
        self.release_all_modifiers()
        time.sleep(0.15)

        backup_clipboard = self.get_clipboard()
        subprocess.run(['wl-copy', '--clear'], check=False)

        if mode == "last_word":
            self.send_combo(e.KEY_LEFTSHIFT, e.KEY_HOME)
            self.release_all_modifiers()
            time.sleep(0.1)
            self.send_combo(e.KEY_LEFTCTRL, e.KEY_C)
        else:
            self.send_combo(e.KEY_LEFTCTRL, e.KEY_C)

        full_text = self.wait_for_new_content()

        if not full_text:
            logger.debug("⚠️ Copy failed/empty.")
            self.set_clipboard(backup_clipboard)
            if mode == "last_word": self.send_combo(e.KEY_RIGHT)
            return

        target_text = full_text
        if mode == "last_word":
            if not full_text.strip():
                self.set_clipboard(backup_clipboard)
                self.send_combo(e.KEY_RIGHT)
                return
            target_text = full_text.split()[-1]

        converted = self.processor.smart_translate(target_text)

        if target_text == converted:
            logger.debug("No change needed.")
            if mode == "last_word": self.send_combo(e.KEY_RIGHT)
            return

        logger.info(f"Correcting: '{target_text}' -> '{converted}'")
        self.set_clipboard(converted)
        time.sleep(0.1)

        if mode == "last_word":
            self.send_combo(e.KEY_RIGHT)
            for _ in range(len(target_text)):
                self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
                self.ui.syn()
                time.sleep(0.005)
                self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
                self.ui.syn()
        else:
            self.send_combo(e.KEY_BACKSPACE)

        self.release_all_modifiers()
        time.sleep(0.05)
        self.send_combo(e.KEY_LEFTCTRL, e.KEY_V)

        if mode == "last_word":
            logger.info("Switching system layout...")
            time.sleep(0.1)
            self.send_combo(*LAYOUT_SWITCH_COMBO)

    def run(self):
        logger.info(f"🚀 SkySwitcher v{VERSION} running...")

        try:
            self.device.grab()
            self.device.ungrab()
        except:
            logger.warning("⚠️ Device grabbed. Running passive.")

        try:
            for event in self.device.read_loop():
                if event.type == e.EV_KEY:

                    if event.code == self.mode2_modifier:
                        self.modifier_down = (event.value == 1 or event.value == 2)

                    if event.code == self.trigger_btn:
                        if event.value == 1:
                            if self.modifier_down:
                                logger.info("✨ Mode 2: Selection Fix")
                                self.process_correction(mode="selection")
                                self.last_press_time = 0
                            else:
                                now = time.time()
                                if now - self.last_press_time < DOUBLE_PRESS_DELAY:
                                    logger.info("⚡ Mode 1: Double Shift")
                                    self.process_correction(mode="last_word")
                                    self.last_press_time = 0
                                else:
                                    self.last_press_time = now

                        elif event.value == 1 and event.code != self.mode2_modifier:
                            if self.last_press_time > 0: self.last_press_time = 0

        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
        except OSError as err:
            logger.error(f"❌ Device error: {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SkySwitcher Layout Corrector")
    parser.add_argument("-d", "--device", help="Path to input device (e.g. /dev/input/eventX)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--list", action="store_true", help="List available devices")

    args = parser.parse_args()

    # 1. Handle --list
    if args.list:
        DeviceManager.list_available()
        sys.exit(0)

    # 2. Handle --verbose
    if args.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)  # Show only Warnings/Errors if not verbose

    # 3. Check Permissions / root
    # Note: On NixOS with user groups, geteuid check might be misleading,
    # but we'll leave it to OSError to catch permission denied.

    # 4. Run
    SkySwitcher(device_path=args.device).run()