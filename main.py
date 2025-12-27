# main.py

# MagShift
#
# Architecture Overview:
# MagShift monitors physical keyboard input and performs layout switching
# by emulating hotkeys (e.g., Meta+Space). This bypasses KDE's per-window
# layout isolation which would otherwise prevent system-wide switching.
#
# Components:
# - DeviceManager: Auto-detects keyboard devices
# - InputBuffer: Tracks typed characters for replay after layout switch
# - MagShift: Main event loop and correction logic

import sys
import time
import logging
import argparse
from evdev import InputDevice, UInput, ecodes as e, list_devices

# Configuration constants
VERSION = "1.0.1"
DOUBLE_PRESS_DELAY = 0.5  # seconds - max interval between double-press
TYPING_TIMEOUT = 3.0      # seconds - buffer reset after inactivity
MAX_BUFFER_SIZE = 100     # maximum tracked keystrokes

# Hardware timing delays (tuned for stability)
HOTKEY_PRESS_DURATION = 0.05      # Hold duration for combo recognition
LAYOUT_SWITCH_SETTLE_TIME = 0.15  # Wait for layout change to complete
KEY_REPLAY_DELAY = 0.005          # Delay between replayed keystrokes
BACKSPACE_DELAY = 0.002           # Delay between backspace events
MODIFIER_RESET_DELAY = 0.05       # OS state update time

# Predefined switching styles
HOTKEY_STYLES = {
    "alt": [e.KEY_LEFTALT, e.KEY_LEFTSHIFT],
    "meta": [e.KEY_LEFTMETA, e.KEY_SPACE],  # Default
    "caps": [e.KEY_CAPSLOCK],
    "ctrl": [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT],
}


# --- Logging Setup ---
def _format_log_record(record: logging.LogRecord) -> str:
    """Format log record with timestamp prefix.

    Args:
        record: Log record to format

    Returns:
        Formatted log message with timestamp
    """
    log_time = time.strftime("%H:%M:%S", time.localtime(record.created))
    return f"[{log_time}] {record.getMessage()}"


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(fmt='%(message)s'))
handler.format = _format_log_record

logger = logging.getLogger("MagShift")
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


def decode_keys(key_list: list[tuple[int, bool]]) -> str:
    """Decode key sequence to human-readable string.

    Args:
        key_list: List of (keycode, shift_pressed) tuples

    Returns:
        Human-readable string representation of the key sequence
    """
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
    """Utility class for keyboard device detection and management.

    This is a static utility class and should not be instantiated.
    """

    IGNORED_KEYWORDS = [
        'mouse', 'webcam', 'audio', 'video', 'consumer',
        'control', 'headset', 'receiver', 'solaar', 'hotkeys',
        'button', 'switch', 'hda', 'dock'
    ]
    REQUIRED_KEYS = {e.KEY_SPACE, e.KEY_ENTER, e.KEY_A, e.KEY_Z}

    def __init__(self):
        """Prevent instantiation of utility class."""
        raise TypeError("DeviceManager is a utility class and should not be instantiated")

    @staticmethod
    def list_available():
        print(f"{'PATH':<20} | {'NAME'}")
        print("-" * 60)
        try:
            for path in list_devices():
                dev = InputDevice(path)
                print(f"{dev.path:<20} | {dev.name}")
        except OSError as err:
            logger.error(f"[✗] Failed to list devices: {err}")

    @staticmethod
    def find_keyboard() -> InputDevice:
        """Auto-detect keyboard device from available input devices.

        Returns:
            InputDevice object for the detected keyboard

        Raises:
            SystemExit: If no keyboard is found or device access fails
        """
        # for correct IDE linting
        paths = []

        try:
            paths = list_devices()
        except OSError as err:
            logger.error(f"[✗] Failed to access input devices: {err}")
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
                    logger.info(f"[✓] Auto-detected keyboard: {dev.name} ({dev.path.split('/')[-1]})")
                    return dev
                possible_candidates.append(dev)

        if possible_candidates:
            best = possible_candidates[0]
            logger.info(f"[✓] Auto-detected keyboard (best guess): {best.name} ({best.path.split('/')[-1]})")
            return best

        logger.error("[✗] No keyboard found. Use --list.")
        sys.exit(1)


# --- Input Buffer (From v0.4.9) ---
class InputBuffer:
    def __init__(self):
        self.buffer = []
        self.last_key_time = 0
        self.trackable_range = range(e.KEY_1, e.KEY_SLASH + 1)

    def add(self, keycode: int, is_shifted: bool):
        """Add a keystroke to the buffer.

        Args:
            keycode: evdev key code
            is_shifted: Whether shift was pressed during keystroke
        """
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
            if len(self.buffer) > MAX_BUFFER_SIZE:
                self.buffer.pop(0)

    def get_last_phrase(self) -> list[tuple[int, bool]]:
        """Extract the last typed phrase from buffer.

        Returns a list of (keycode, shift_pressed) tuples representing
        the most recent word, including any leading spaces.

        Returns:
            List of key tuples, or empty list if buffer is empty
        """
        if not self.buffer:
            return []

        result = []
        found_char = False

        for item in reversed(self.buffer):
            code, shift = item
            if code == e.KEY_SPACE:
                if found_char:
                    break  # Stop at first space after finding characters
                else:
                    result.insert(0, item)  # Include leading spaces
            else:
                found_char = True
                result.insert(0, item)

        return result


# --- Main Application ---
class MagShift:
    def __init__(self, device_path=None, switch_keys=None):
        """Initialize MagShift with input/output devices and state.

        Args:
            device_path: Optional path to input device, auto-detects if None
            switch_keys: Optional list of key codes for layout switching hotkey
        """
        # Default to Meta+Space if nothing passed
        self.switch_keys = switch_keys if switch_keys else HOTKEY_STYLES['meta']

        # Initialize input device
        if device_path:
            try:
                self.device = InputDevice(device_path)
                logger.info(f"[i] Manual device: {self.device.name}")
            except OSError as err:
                logger.error(f"[✗] Failed to open device {device_path}: {err}")
                sys.exit(1)
        else:
            self.device = DeviceManager.find_keyboard()

        # Define virtual keyboard capabilities
        self.uinput_keys = [
            e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_RIGHTCTRL, e.KEY_RIGHTSHIFT,
            e.KEY_LEFTMETA, e.KEY_LEFTALT, e.KEY_BACKSPACE, e.KEY_SPACE,
            e.KEY_CAPSLOCK, e.KEY_TAB,
            *range(e.KEY_ESC, e.KEY_MICMUTE)
        ]

        # Create virtual output device
        try:
            self.ui = UInput({e.EV_KEY: self.uinput_keys}, name="MagShift-Virtual")
        except OSError as err:
            logger.error(f"[✗] Failed to create UInput device: {err}")
            sys.exit(1)

        # Initialize buffer and state
        self.input_buffer = InputBuffer()
        self.last_press_time = 0
        self.trigger_released = True
        self.trigger_btn = e.KEY_RIGHTSHIFT
        self.shift_pressed = False
        self.pending_action = False

    def perform_layout_switch(self):
        """Switch keyboard layout using configured hotkey combination.

        Prevents unintended menu activation (e.g., Alt menu in KDE) by
        releasing modifier keys before trigger keys.

        Strategy: Release Modifier (Alt) BEFORE releasing Trigger (Shift).
        Example: [Alt, Shift] -> Release Alt first -> State becomes Shift (Safe!)
        If we release Shift first -> State becomes Alt -> Release Alt -> Menu triggers.
        """
        if not self.switch_keys:
            return

        # Press all keys (simultaneous press for better input system recognition)
        for k in self.switch_keys:
            self.ui.write(e.EV_KEY, k, 1)
        self.ui.syn()

        # Hold to register the combo
        time.sleep(HOTKEY_PRESS_DURATION)

        # Release keys in same order (modifier first to prevent menu trigger)
        # DO NOT use reversed() here
        for k in self.switch_keys:
            self.ui.write(e.EV_KEY, k, 0)
        self.ui.syn()

        # Allow layout to stabilize
        time.sleep(LAYOUT_SWITCH_SETTLE_TIME)

    def replay_keys(self, key_sequence):
        """Replay a sequence of keystrokes with proper shift handling.

        Args:
            key_sequence: List of (keycode, shift_pressed) tuples to replay
        """
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
            time.sleep(KEY_REPLAY_DELAY)

    def reset_modifiers(self):
        """Force release all modifier keys to prevent stuck key states.

        Extended modifier list ensures clean state reset for all possible
        modifier keys that might interfere with subsequent operations.
        """
        modifiers = [
            e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT,
            e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL,
            e.KEY_LEFTALT, e.KEY_RIGHTALT,
            e.KEY_LEFTMETA, e.KEY_RIGHTMETA
        ]

        # Release all modifiers
        for key in modifiers:
            self.ui.write(e.EV_KEY, key, 0)
        self.ui.syn()

        # Allow OS time to update keyboard state before sending backspace
        time.sleep(MODIFIER_RESET_DELAY)

    def fix_last_word(self):
        """Correct the last typed phrase by switching layout.

        Process:
        1. Release all modifier keys to prevent interference
        2. Delete last phrase using backspace
        3. Switch keyboard layout
        4. Replay the phrase in new layout
        """
        keys_to_replay = self.input_buffer.get_last_phrase()
        if not keys_to_replay:
            logger.info("[!] Buffer empty.")
            return

        # Release virtual modifiers
        self.reset_modifiers()

        readable_text = decode_keys(keys_to_replay)
        logger.info(f"[>] Correcting: '{readable_text}'")

        # Delete the phrase
        for _ in range(len(keys_to_replay)):
            self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
            self.ui.syn()
            self.ui.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
            self.ui.syn()
            time.sleep(BACKSPACE_DELAY)

        # Switch layout
        self.perform_layout_switch()

        # Replay in new layout
        self.replay_keys(keys_to_replay)

    def run(self):
        """Main event loop for keyboard monitoring and correction.

        Monitors keyboard input events and triggers layout correction on
        double-press of the trigger key (Right Shift by default).

        The loop handles:
        - Shift key state tracking for proper case handling
        - Double-press detection with configurable delay
        - Keystroke buffering for correction replay
        - Graceful shutdown on Ctrl+C
        """
        logger.info(f"[>] MagShift v{VERSION}")

        # Test device grab capability
        try:
            self.device.grab()
            self.device.ungrab()
        except Exception:
            pass

        try:
            for event in self.device.read_loop():
                if event.type == e.EV_KEY:
                    # Track Shift state for proper case handling
                    if event.code in [e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT]:
                        self.shift_pressed = (event.value == 1 or event.value == 2)

                    # Handle trigger key (Right Shift)
                    if event.code == self.trigger_btn:

                        # Key press
                        if event.value == 1:
                            now = time.time()
                            if (now - self.last_press_time < DOUBLE_PRESS_DELAY) and self.trigger_released:
                                self.pending_action = True
                                self.last_press_time = 0
                            else:
                                self.last_press_time = now
                                self.pending_action = False

                            self.trigger_released = False

                        # Key release
                        elif event.value == 0:
                            self.trigger_released = True

                            # Execute correction on double-press
                            if self.pending_action:
                                self.fix_last_word()
                                self.pending_action = False

                    # Track other keys in buffer
                    elif event.value in [1, 2]:
                        if event.code != self.trigger_btn:
                            self.input_buffer.add(event.code, self.shift_pressed)
                        # Cancel pending action if other key pressed
                        if self.last_press_time > 0:
                            self.last_press_time = 0

        except KeyboardInterrupt:
            print("\n[✓] Stopped by user.")
        except OSError as err:
            logger.error(f"[✗] Device error: {err}")


def main():
    """Main entry point for MagShift application."""
    parser = argparse.ArgumentParser(description="MagShift - Advanced Keyboard Layout Switcher with Instant Correction Engine")

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
    logger.info(f"[i] Using hotkey style: {args.hotkey} -> {selected_keys}")

    MagShift(device_path=args.device, switch_keys=selected_keys).run()


if __name__ == "__main__":
    main()
