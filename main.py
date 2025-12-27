# main.py

# SkySwitcher v0.5.9 (fixed alt hotkey issue)
#
# Architecture:
# - Keyboard Device Detection
# - Switching Logic: Physical HotKey Emulation to bypass KDE's "Per-Window Layout" isolation.
# - Buffer: Simple "Backspace -> Switch -> Replay" loop.

import sys
import time
import logging
import argparse
from evdev import InputDevice, UInput, ecodes as e, list_devices

# Fixed configurations
VERSION = "0.5.3"
DOUBLE_PRESS_DELAY = 0.5
TYPING_TIMEOUT = 3.0

# Predefined switching styles
HOTKEY_STYLES = {
    "alt":  [e.KEY_LEFTALT, e.KEY_LEFTSHIFT],
    "meta": [e.KEY_LEFTMETA, e.KEY_SPACE],  # Default
    "caps": [e.KEY_CAPSLOCK],
    "ctrl": [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT],
}


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


# --- Device Detection (From v0.4.9) ---
class DeviceManager:
    IGNORED_KEYWORDS = [
        'mouse', 'webcam', 'audio', 'video', 'consumer',
        'control', 'headset', 'receiver', 'solaar', 'hotkeys',
        'button', 'switch', 'hda', 'dock'
    ]
    REQUIRED_KEYS = {e.KEY_SPACE, e.KEY_ENTER, e.KEY_A, e.KEY_Z}

    @staticmethod
    def list_available():
        print(f"{'PATH':<20} | {'NAME'}")
        print("-" * 60)
        try:
            for path in list_devices():
                dev = InputDevice(path)
                print(f"{dev.path:<20} | {dev.name}")
        except OSError as err:
            logger.error(f"❌ Failed to list devices: {err}")

    @staticmethod
    def find_keyboard() -> InputDevice:
        paths = []  # important for IDE linting

        try:
            paths = list_devices()
        except OSError:
            logger.error("❌ Failed to access input devices (Permission denied?).")
            sys.exit(1)

        possible_candidates = []
        for path in paths:
            try:
                dev = InputDevice(path)
            except OSError:
                continue

            name_lower = dev.name.lower()
            if any(bad in name_lower for bad in DeviceManager.IGNORED_KEYWORDS):
                continue

            caps = dev.capabilities()
            if e.EV_KEY not in caps:
                continue

            supported_keys = set(caps[e.EV_KEY])
            if DeviceManager.REQUIRED_KEYS.issubset(supported_keys):
                if 'keyboard' in name_lower or 'kbd' in name_lower:
                    logger.info(f"✅ Auto-detected keyboard: {dev.name} ({dev.path.split('/')[-1]})")
                    return dev
                possible_candidates.append(dev)

        if possible_candidates:
            best = possible_candidates[0]
            logger.info(f"✅ Auto-detected keyboard (best guess): {best.name} ({best.path.split('/')[-1]})")
            return best

        logger.error("❌ No keyboard found. Use --list.")
        sys.exit(1)


# --- Input Buffer (From v0.4.9) ---
class InputBuffer:
    def __init__(self):
        self.buffer = []
        self.last_key_time = 0
        self.trackable_range = range(e.KEY_1, e.KEY_SLASH + 1)

    def add(self, keycode, is_shifted):
        now = time.time()
        if (now - self.last_key_time) > TYPING_TIMEOUT:
            if self.buffer:
                self.buffer = []
        self.last_key_time = now

        if keycode == e.KEY_BACKSPACE:
            if self.buffer:
                self.buffer.pop()
            return

        if keycode == e.KEY_SPACE or keycode in self.trackable_range:
            self.buffer.append((keycode, is_shifted))
            if len(self.buffer) > 100:
                self.buffer.pop(0)

    def get_last_phrase(self):
        if not self.buffer: return []
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


# --- Main Application ---
class SkySwitcher:
    def __init__(self, device_path=None, switch_keys=None):
        # Default to Meta+Space if nothing passed (though argparse handles defaults)
        self.switch_keys = switch_keys if switch_keys else HOTKEY_STYLES['meta']

        if device_path:
            try:
                self.device = InputDevice(device_path)
                logger.info(f"✅ Manual Device: {self.device.name}")
            except OSError:
                sys.exit(1)
        else:
            self.device = DeviceManager.find_keyboard()

        self.uinput_keys = [
            e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_RIGHTCTRL, e.KEY_RIGHTSHIFT,
            e.KEY_LEFTMETA, e.KEY_LEFTALT, e.KEY_BACKSPACE, e.KEY_SPACE,
            e.KEY_CAPSLOCK, e.KEY_TAB,
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
        self.pending_action = False

    def perform_layout_switch(self):
        """
        Switches layout preventing 'Alt Menu' trigger.
        Strategy: Release Modifier (Alt) BEFORE releasing the Trigger (Shift).
        """
        logger.info(f"🔀 Switching Layout...")

        if not self.switch_keys:
            return

        # --- PRESS PHASE ---
        # Press all keys (Simultaneous press is fine/better for input systems)
        for k in self.switch_keys:
            self.ui.write(e.EV_KEY, k, 1)
        self.ui.syn()

        # Hold to register the combo
        time.sleep(0.05)

        # --- RELEASE PHASE (The Fix) ---
        # DO NOT use reversed() here.
        # We must release keys in the SAME order (or specifically Modifier first).
        # Example: [Alt, Shift] -> Release Alt first -> State becomes Shift (Safe!)
        # If we release Shift first -> State becomes Alt -> Release Alt -> Menu triggers.

        for k in self.switch_keys:
            self.ui.write(e.EV_KEY, k, 0)
        self.ui.syn()

        # Stabilize
        time.sleep(0.15)

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

    def reset_modifiers(self):
        """Force release all modifiers cleanly."""
        # Список розширено, щоб точно вбити все, що може залипнути
        modifiers = [
            e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT,
            e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL,
            e.KEY_LEFTALT, e.KEY_RIGHTALT,
            e.KEY_LEFTMETA, e.KEY_RIGHTMETA
        ]

        # 1. Release all modifiers
        for key in modifiers:
            self.ui.write(e.EV_KEY, key, 0)
        self.ui.syn()

        # 2. Critical Wait: Give OS time to update state before we type Backspace
        time.sleep(0.05)

    def fix_last_word(self):
        keys_to_replay = self.input_buffer.get_last_phrase()
        if not keys_to_replay:
            logger.info("⚠️ Buffer empty.")
            return

        # 1. Release Virtual Modifiers
        self.reset_modifiers()

        readable_text = decode_keys(keys_to_replay)
        logger.info(f"🔄 Correcting: '{readable_text}'")

        # 2. Delete
        for _ in range(len(keys_to_replay)):
            self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
            self.ui.syn()
            self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
            self.ui.syn()
            time.sleep(0.002)

        # 3. Switch (Physical)
        self.perform_layout_switch()

        # 4. Replay
        self.replay_keys(keys_to_replay)

    def run(self):
        logger.info(f"🚀 SkySwitcher v{VERSION}")

        # Grab check
        try:
            self.device.grab()
            self.device.ungrab()
        except Exception:
            pass

        try:
            for event in self.device.read_loop():
                if event.type == e.EV_KEY:
                    # Tracking Shift state for typing (upper/lower case)
                    if event.code in [e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT]:
                        self.shift_pressed = (event.value == 1 or event.value == 2)

                    # --- LOGIC START ---
                    if event.code == self.trigger_btn:

                        # === PRESS (value 1) ===
                        if event.value == 1:
                            now = time.time()
                            if (now - self.last_press_time < DOUBLE_PRESS_DELAY) and self.trigger_released:
                                self.pending_action = True
                                self.last_press_time = 0
                            else:
                                self.last_press_time = now
                                self.pending_action = False

                            self.trigger_released = False

                        # === RELEASE (value 0) ===
                        elif event.value == 0:
                            self.trigger_released = True

                            # Double Press detected
                            if self.pending_action:
                                logger.info("✨ Trigger confirmed (on release)")
                                self.fix_last_word()
                                self.pending_action = False

                    # Tracking other keys
                    elif event.value in [1, 2]:
                        if event.code != self.trigger_btn:
                            self.input_buffer.add(event.code, self.shift_pressed)
                        # Single Press detected
                        if self.last_press_time > 0:
                            self.last_press_time = 0

        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
        except OSError as err:
            logger.error(f"❌ Device error: {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SkySwitcher - Super simple keyboard layout corrector")

    # Device argument
    parser.add_argument("-d", "--device", help="Path to input device (optional)")

    # Logging argument
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    # List devices argument
    parser.add_argument("--list", action="store_true", help="List available devices")

    # Hotkey argument
    parser.add_argument(
        "-k", "--hotkey",
        choices=HOTKEY_STYLES.keys(),
        default="meta",
        help="Layout switching key combination (default: meta)"
    )

    args = parser.parse_args()

    if args.list:
        DeviceManager.list_available()
        sys.exit(0)

    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Resolve keys based on argument
    selected_keys = HOTKEY_STYLES[args.hotkey]
    logger.info(f"🔑 Using hotkey style: {args.hotkey} -> {selected_keys}")

    SkySwitcher(device_path=args.device, switch_keys=selected_keys).run()