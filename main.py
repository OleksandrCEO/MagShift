# main.py

# SkySwitcher v0.4.5 (Time-based Reset)
# Features:
# - No-Clipboard Mode (Direct key replay via uinput).
# - Persistent Buffer: Replaying does NOT clear history (allows cycling layouts).
# - UX Improvement: Buffer resets automatically if typing stops for > 3 seconds.
#   (Replaces the old Enter/Esc reset logic).

import sys
import time
import logging
import argparse
from evdev import InputDevice, UInput, ecodes as e, list_devices

# --- Configuration ---
VERSION = "0.4.5"
DOUBLE_PRESS_DELAY = 0.5
TYPING_TIMEOUT = 3.0  # Seconds to wait before considering it a "new typing session"
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

# --- Helper for Logging ---
KEY_MAP = {
    e.KEY_Q: 'q', e.KEY_W: 'w', e.KEY_E: 'e', e.KEY_R: 'r', e.KEY_T: 't', e.KEY_Y: 'y', e.KEY_U: 'u', e.KEY_I: 'i',
    e.KEY_O: 'o', e.KEY_P: 'p',
    e.KEY_A: 'a', e.KEY_S: 's', e.KEY_D: 'd', e.KEY_F: 'f', e.KEY_G: 'g', e.KEY_H: 'h', e.KEY_J: 'j', e.KEY_K: 'k',
    e.KEY_L: 'l',
    e.KEY_Z: 'z', e.KEY_X: 'x', e.KEY_C: 'c', e.KEY_V: 'v', e.KEY_B: 'b', e.KEY_N: 'n', e.KEY_M: 'm',
    e.KEY_1: '1', e.KEY_2: '2', e.KEY_3: '3', e.KEY_4: '4', e.KEY_5: '5', e.KEY_6: '6', e.KEY_7: '7', e.KEY_8: '8',
    e.KEY_9: '9', e.KEY_0: '0',
    e.KEY_MINUS: '-', e.KEY_EQUAL: '=', e.KEY_LEFTBRACE: '[', e.KEY_RIGHTBRACE: ']', e.KEY_BACKSLASH: '\\',
    e.KEY_SEMICOLON: ';', e.KEY_APOSTROPHE: "'", e.KEY_COMMA: ',', e.KEY_DOT: '.', e.KEY_SLASH: '/', e.KEY_GRAVE: '`',
    e.KEY_SPACE: ' '
}


def decode_keys(key_list):
    """Converts a list of (keycode, shift) into a string for logging."""
    result = ""
    for code, shift in key_list:
        char = KEY_MAP.get(code, '?')
        if shift and char.isalpha():
            char = char.upper()
        elif shift:
            shift_map = {'1': '!', '2': '@', '3': '#', '4': '$', '5': '%', '6': '^', '7': '&', '8': '*', '9': '(',
                         '0': ')', '-': '_', '=': '+', '[': '{', ']': '}', '\\': '|', ';': ':', "'": '"', ',': '<',
                         '.': '>', '/': '?', '`': '~'}
            char = shift_map.get(char, char)
        result += char
    return result


class DeviceManager:
    IGNORED_KEYWORDS = [
        'mouse', 'webcam', 'audio', 'video', 'consumer',
        'control', 'headset', 'receiver', 'solaar', 'hotkeys',
        'button', 'switch', 'hda', 'dock'
    ]
    REQUIRED_KEYS = {e.KEY_SPACE, e.KEY_ENTER, e.KEY_A, e.KEY_Z}

    @staticmethod
    def list_available():
        devices = []
        try:
            devices = [InputDevice(path) for path in list_devices()]
        except OSError:
            print("❌ Failed to list devices.", file=sys.stderr)
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
            logger.error("❌ Failed to list devices. Check permissions.")
            sys.exit(1)

        devices.sort(key=lambda x: x.path)
        possible_candidates = []

        for dev in devices:
            name_lower = dev.name.lower()
            if any(bad in name_lower for bad in DeviceManager.IGNORED_KEYWORDS):
                continue
            if e.EV_KEY not in dev.capabilities():
                continue
            supported_keys = set(dev.capabilities()[e.EV_KEY])
            if DeviceManager.REQUIRED_KEYS.issubset(supported_keys):
                if 'keyboard' in name_lower or 'kbd' in name_lower:
                    logger.info(f"✅ Auto-detected: {dev.name}")
                    return dev
                possible_candidates.append(dev)

        if possible_candidates:
            logger.info(f"✅ Auto-detected (best guess): {possible_candidates[0].name}")
            return possible_candidates[0]

        logger.error("❌ No keyboard found. Use --list.")
        sys.exit(1)


class InputBuffer:
    """
    Tracks keys for replay with time-based reset logic.
    """

    def __init__(self):
        self.buffer = []
        self.last_key_time = 0  # Timestamp of the last added key
        self.trackable_range = range(e.KEY_1, e.KEY_SLASH + 1)

    def add(self, keycode, is_shifted):
        now = time.time()

        # --- Time-based Reset Logic ---
        # If too much time passed since last key, we assume a new thought/sentence started.
        if (now - self.last_key_time) > TYPING_TIMEOUT:
            if self.buffer:
                # logger.debug(f"⏳ Timeout ({TYPING_TIMEOUT}s) reached. Buffer cleared.")
                self.buffer = []

        self.last_key_time = now

        # Handle Backspace
        if keycode == e.KEY_BACKSPACE:
            if self.buffer:
                self.buffer.pop()
            return

        # Add regular keys
        if keycode == e.KEY_SPACE or keycode in self.trackable_range:
            self.buffer.append((keycode, is_shifted))
            if len(self.buffer) > 100:  # Safety cap
                self.buffer.pop(0)

    def get_last_phrase(self):
        if not self.buffer:
            return []

        result = []
        found_char = False

        for item in reversed(self.buffer):
            code, shift = item

            if code == e.KEY_SPACE:
                if found_char:
                    break
                else:
                    result.insert(0, item)
            else:
                found_char = True
                result.insert(0, item)

        return result


class SkySwitcher:
    def __init__(self, device_path=None):
        if device_path:
            try:
                self.device = InputDevice(device_path)
                logger.info(f"✅ Manual Device: {self.device.name}")
            except OSError:
                sys.exit(1)
        else:
            self.device = DeviceManager.find_keyboard()

        # Virtual Input Setup
        self.uinput_keys = [
            e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_RIGHTCTRL, e.KEY_RIGHTSHIFT,
            e.KEY_LEFTMETA, e.KEY_LEFTALT, e.KEY_BACKSPACE, e.KEY_SPACE,
            *range(e.KEY_ESC, e.KEY_MICMUTE)
        ]

        try:
            self.ui = UInput({e.EV_KEY: self.uinput_keys}, name="SkySwitcher-Virtual")
        except OSError:
            logger.error("❌ Failed to create UInput.")
            sys.exit(1)

        self.input_buffer = InputBuffer()
        self.last_press_time = 0
        self.trigger_released = True
        self.trigger_btn = e.KEY_RIGHTSHIFT
        self.shift_pressed = False

    def send_combo(self, *keys):
        for k in keys:
            self.ui.write(e.EV_KEY, k, 1)
        self.ui.syn()
        time.sleep(0.02)
        for k in reversed(keys):
            self.ui.write(e.EV_KEY, k, 0)
        self.ui.syn()
        time.sleep(0.02)

    def replay_keys(self, key_sequence):
        for code, use_shift in key_sequence:
            if use_shift:
                self.ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
                self.ui.syn()

            self.ui.write(e.EV_KEY, code, 1)
            self.ui.syn()
            self.ui.write(e.EV_KEY, code, 0)
            self.ui.syn()

            if use_shift:
                self.ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
                self.ui.syn()

            time.sleep(0.005)

    def fix_last_word(self):
        keys_to_replay = self.input_buffer.get_last_phrase()

        if not keys_to_replay:
            logger.info("⚠️ Buffer empty or no word found.")
            return

        readable_text = decode_keys(keys_to_replay)
        logger.info(f"Replaying: '{readable_text}' ({len(keys_to_replay)} keys)")

        count = len(keys_to_replay)
        for _ in range(count):
            self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
            self.ui.syn()
            self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
            self.ui.syn()
            time.sleep(0.002)

        self.send_combo(*LAYOUT_SWITCH_COMBO)
        time.sleep(0.1)

        self.replay_keys(keys_to_replay)

    def run(self):
        logger.info(f"🚀 SkySwitcher v{VERSION} (No-Clipboard Mode)")

        try:
            self.device.grab()
            self.device.ungrab()
        except Exception:
            logger.warning("⚠️ Device grabbed. Running passive.")

        try:
            for event in self.device.read_loop():
                if event.type == e.EV_KEY:

                    if event.code in [e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT]:
                        self.shift_pressed = (event.value == 1 or event.value == 2)

                    if event.code == self.trigger_btn:
                        if event.value == 0:
                            self.trigger_released = True
                        elif event.value == 1:
                            now = time.time()
                            if (now - self.last_press_time < DOUBLE_PRESS_DELAY) and self.trigger_released:
                                self.fix_last_word()
                                self.last_press_time = 0
                                self.trigger_released = False
                            else:
                                self.last_press_time = now
                                self.trigger_released = False

                    # Buffer Logic: Only add if key is pressed (1) or repeated (2)
                    elif event.value in [1, 2]:
                        if event.code != self.trigger_btn:
                            self.input_buffer.add(event.code, self.shift_pressed)

                        if self.last_press_time > 0:
                            self.last_press_time = 0

        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
        except OSError as err:
            logger.error(f"❌ Device error: {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", help="Path to input device")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--list", action="store_true", help="List available devices")
    args = parser.parse_args()

    if args.list:
        DeviceManager.list_available()
        sys.exit(0)

    if args.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)

    SkySwitcher(device_path=args.device).run()