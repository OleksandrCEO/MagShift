#!/usr/bin/env python3
# main.py

# MagShift v1.1.0 (Linux + macOS)
#
# Architecture Overview:
# MagShift monitors physical keyboard input and performs layout switching by
# emulating hotkeys (Linux) or calling the Text Input Source API (macOS).
# Can also force NumLock state (Linux only).
#
# The file is split into three layers:
#   1. Platform-neutral key codes, buffer and helpers.
#   2. Backends: LinuxBackend (evdev/uinput, XTEST on X11) and MacBackend (Quartz/Carbon).
#   3. MagShift - the state machine, which never touches a platform API directly.

import sys
import time
import logging
import argparse

# Configuration constants
VERSION = "1.1.0"
DOUBLE_PRESS_DELAY = 0.4  # seconds - max interval between double-press
TYPING_TIMEOUT = 1  # seconds - buffer reset after inactivity
MAX_BUFFER_SIZE = 20  # maximum tracked keystrokes

# Hardware timing delays (TUNED FOR STABILITY)
HOTKEY_PRESS_DURATION = 0.05
LAYOUT_SWITCH_SETTLE_TIME = 0.15
KEY_REPLAY_DELAY = 0.005
BACKSPACE_DELAY = 0.005
MODIFIER_RESET_DELAY = 0.05

# --- Internal key codes ---
# Values are the Linux input-event-codes numbers, used as the canonical
# representation on every platform. The Linux backend passes them through
# unchanged; the macOS backend translates to/from Carbon kVK_* virtual codes.
KEY_ESC = 1
KEY_1, KEY_2, KEY_3, KEY_4, KEY_5 = 2, 3, 4, 5, 6
KEY_6, KEY_7, KEY_8, KEY_9, KEY_0 = 7, 8, 9, 10, 11
KEY_MINUS, KEY_EQUAL, KEY_BACKSPACE, KEY_TAB = 12, 13, 14, 15
KEY_Q, KEY_W, KEY_E, KEY_R, KEY_T = 16, 17, 18, 19, 20
KEY_Y, KEY_U, KEY_I, KEY_O, KEY_P = 21, 22, 23, 24, 25
KEY_LEFTBRACE, KEY_RIGHTBRACE, KEY_ENTER, KEY_LEFTCTRL = 26, 27, 28, 29
KEY_A, KEY_S, KEY_D, KEY_F, KEY_G = 30, 31, 32, 33, 34
KEY_H, KEY_J, KEY_K, KEY_L = 35, 36, 37, 38
KEY_SEMICOLON, KEY_APOSTROPHE, KEY_GRAVE = 39, 40, 41
KEY_LEFTSHIFT, KEY_BACKSLASH = 42, 43
KEY_Z, KEY_X, KEY_C, KEY_V, KEY_B, KEY_N, KEY_M = 44, 45, 46, 47, 48, 49, 50
KEY_COMMA, KEY_DOT, KEY_SLASH, KEY_RIGHTSHIFT = 51, 52, 53, 54
KEY_LEFTALT, KEY_SPACE, KEY_CAPSLOCK = 56, 57, 58
KEY_NUMLOCK = 69
KEY_PAUSE, KEY_COMPOSE = 119, 127  # Pause/Break and the Menu key
KEY_KPENTER, KEY_RIGHTCTRL, KEY_RIGHTALT = 96, 97, 100
KEY_LEFTMETA, KEY_RIGHTMETA = 125, 126
KEY_MICMUTE = 248  # upper bound of the uinput key range on Linux

# Predefined switching styles (Linux only - macOS switches via the TIS API)
HOTKEY_STYLES = {
    "alt": [KEY_LEFTALT, KEY_LEFTSHIFT],
    "meta": [KEY_LEFTMETA, KEY_SPACE],  # Default
    "caps": [KEY_CAPSLOCK],
    "ctrl": [KEY_LEFTCTRL, KEY_LEFTSHIFT],
    "menu": [KEY_COMPOSE],
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
    KEY_Q: 'q', KEY_W: 'w', KEY_E: 'e', KEY_R: 'r', KEY_T: 't', KEY_Y: 'y', KEY_U: 'u', KEY_I: 'i',
    KEY_O: 'o', KEY_P: 'p',
    KEY_A: 'a', KEY_S: 's', KEY_D: 'd', KEY_F: 'f', KEY_G: 'g', KEY_H: 'h', KEY_J: 'j', KEY_K: 'k',
    KEY_L: 'l',
    KEY_Z: 'z', KEY_X: 'x', KEY_C: 'c', KEY_V: 'v', KEY_B: 'b', KEY_N: 'n', KEY_M: 'm',
    KEY_1: '1', KEY_2: '2', KEY_3: '3', KEY_4: '4', KEY_5: '5', KEY_6: '6', KEY_7: '7', KEY_8: '8',
    KEY_9: '9', KEY_0: '0',
    KEY_MINUS: '-', KEY_EQUAL: '=', KEY_LEFTBRACE: '[', KEY_RIGHTBRACE: ']', KEY_BACKSLASH: '\\',
    KEY_SEMICOLON: ';', KEY_APOSTROPHE: "'", KEY_COMMA: ',', KEY_DOT: '.', KEY_SLASH: '/', KEY_GRAVE: '`',
    KEY_SPACE: ' '
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


# --- Input Buffer ---
class InputBuffer:
    def __init__(self):
        self.buffer = []
        self.last_key_time = 0
        self.trackable_range = range(KEY_1, KEY_SLASH + 1)

    def add(self, keycode: int, is_shifted: bool, modifier_pressed: bool = False):
        """Add a keystroke to the buffer.

        Args:
            keycode: internal key code
            is_shifted: Whether shift was pressed during keystroke
            modifier_pressed: Whether any modifier (ctrl/meta/alt) was pressed
        """
        now = time.time()
        # Clear by Timeout
        if (now - self.last_key_time) > TYPING_TIMEOUT:
            if self.buffer:
                self.buffer = []
        self.last_key_time = now

        # Clear by Enter/Tab/Esc - end of phrase
        if keycode in [KEY_ENTER, KEY_KPENTER, KEY_TAB, KEY_ESC]:
            if self.buffer:
                self.buffer = []
            return

        if keycode == KEY_BACKSPACE:
            if self.buffer:
                self.buffer.pop()
            return

        # Clear buffer and ignore when hotkey is pressed (Ctrl+C, Alt+Tab, etc)
        if modifier_pressed:
            if self.buffer:
                self.buffer = []
            return

        # Use Spase as regular symbol
        if keycode == KEY_SPACE or keycode in self.trackable_range:
            self.buffer.append((keycode, is_shifted))
            if len(self.buffer) > MAX_BUFFER_SIZE:
                self.buffer.pop(0)

    def get_last_phrase(self) -> list[tuple[int, bool]]:
        """Extract the last typed phrase from buffer.

        Returns a list of (keycode, shift_pressed) tuples representing
        the entire buffer contents (all words and spaces).

        Returns:
            List of key tuples, or empty list if buffer is empty
        """
        return self.buffer.copy()


# ==============================================================================
# Backends
# ==============================================================================

class XTestKeyboard:
    """X11 output through the XTEST extension, with the write()/syn() calls of evdev's UInput.

    On X11 a uinput keyboard is a newly plugged device, and X.Org gives it the system default layout instead of the
    session one (set via setxkbmap, or by a desktop that does not re-apply it on hotplug): the emulated hotkey does
    not switch and the phrase is replayed in the wrong layout. The XTEST keyboard exists since server start and
    follows every layout change, so it types exactly like the physical keyboard.
    """

    def __init__(self):
        import ctypes
        import ctypes.util
        from ctypes import c_void_p, c_char_p, c_uint, c_int, c_ulong

        self.x11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library('X11') or 'libX11.so.6')
        self.xtst = ctypes.cdll.LoadLibrary(ctypes.util.find_library('Xtst') or 'libXtst.so.6')
        self.x11.XOpenDisplay.restype = c_void_p
        self.x11.XOpenDisplay.argtypes = [c_char_p]
        self.x11.XFlush.argtypes = [c_void_p]
        self.x11.XCloseDisplay.argtypes = [c_void_p]
        self.x11.XQueryExtension.argtypes = [c_void_p, c_char_p] + [ctypes.POINTER(c_int)] * 3
        self.xtst.XTestQueryExtension.argtypes = [c_void_p] + [ctypes.POINTER(c_int)] * 4
        self.xtst.XTestFakeKeyEvent.argtypes = [c_void_p, c_uint, c_int, c_ulong]

        self.display = self.x11.XOpenDisplay(None)
        if not self.display:
            raise OSError("cannot open the X display")
        unused = [ctypes.byref(c_int()) for _ in range(4)]
        reason = None
        if self.x11.XQueryExtension(self.display, b'XWAYLAND', *unused[:3]):
            reason = "the display is Xwayland, whose XTEST reaches X11 apps only"
        elif not self.xtst.XTestQueryExtension(self.display, *unused):
            reason = "the X server has no XTEST extension"
        if reason:
            self.x11.XCloseDisplay(self.display)
            raise OSError(reason)

    def write(self, _event_type, code, value):
        # X.Org keycodes are evdev codes shifted by 8
        self.xtst.XTestFakeKeyEvent(self.display, code + 8, value, 0)

    def syn(self):
        self.x11.XFlush(self.display)


class LinuxBackend:
    """evdev input; uinput output, or XTEST in an X11 session. Internal key codes are evdev codes, so no
    translation is needed in either direction."""

    name = "linux"
    supports_numlock = True
    supports_hotkey_styles = True

    IGNORED_KEYWORDS = [
        'mouse', 'webcam', 'audio', 'video', 'consumer',
        'control', 'headset', 'receiver', 'solaar', 'hotkeys',
        'button', 'switch', 'hda', 'dock'
    ]
    REQUIRED_KEYS = {KEY_SPACE, KEY_ENTER, KEY_A, KEY_Z}

    def __init__(self, device_path=None, switch_keys=None):
        from evdev import InputDevice, UInput, ecodes, list_devices
        self._ecodes = ecodes
        self._InputDevice = InputDevice
        self._list_devices = list_devices

        self.switch_keys = switch_keys if switch_keys else HOTKEY_STYLES['meta']

        if device_path:
            try:
                self.device = InputDevice(device_path)
                logger.info(f"[i] Manual device: {self.device.name}")
            except OSError as err:
                logger.error(f"[✗] Failed to open device {device_path}: {err}")
                sys.exit(1)
        else:
            self.device = self.find_keyboard()

        self.ui = self.xtest_keyboard()
        if self.ui:
            return

        uinput_keys = [
            KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_RIGHTCTRL, KEY_RIGHTSHIFT,
            KEY_LEFTMETA, KEY_LEFTALT, KEY_BACKSPACE, KEY_SPACE,
            KEY_CAPSLOCK, KEY_TAB, KEY_NUMLOCK,  # Explicitly added
            *range(KEY_ESC, KEY_MICMUTE)
        ]

        try:
            self.ui = UInput({ecodes.EV_KEY: uinput_keys}, name="MagShift-Virtual")
        except OSError as err:
            logger.error(f"[✗] Failed to create UInput: {err}")
            sys.exit(1)

    @staticmethod
    def xtest_keyboard():
        """XTestKeyboard in an X11 session; None on Wayland, a text console or as a system service."""
        import os
        if os.environ.get('WAYLAND_DISPLAY') or os.environ.get('XDG_SESSION_TYPE') == 'wayland':
            return None
        if not os.environ.get('DISPLAY'):
            return None
        try:
            keyboard = XTestKeyboard()
        except OSError as err:
            logger.warning(f"[!] Not typing through XTEST ({err}), using uinput. On X11, X.Org gives the uinput "
                           "keyboard the system default layout (see 'localectl status'), which must match yours.")
            return None
        logger.info("[i] X11 session: typing through XTEST")
        return keyboard

    # --- Device discovery ---

    @classmethod
    def list_available(cls):
        from evdev import InputDevice, list_devices
        print(f"{'PATH':<20} | {'NAME'}")
        print("-" * 60)
        try:
            for path in list_devices():
                dev = InputDevice(path)
                print(f"{dev.path:<20} | {dev.name}")
        except OSError as err:
            logger.error(f"[✗] Failed to list devices: {err}")

    def find_keyboard(self):
        """Auto-detect keyboard device from available input devices.

        Returns:
            InputDevice object for the detected keyboard

        Raises:
            SystemExit: If no keyboard is found or device access fails
        """
        ecodes = self._ecodes
        # for correct IDE linting
        paths = []

        try:
            paths = self._list_devices()
        except OSError as err:
            logger.error(f"[✗] Failed to access input devices: {err}")
            sys.exit(1)

        possible_candidates = []
        for path in paths:
            try:
                dev = self._InputDevice(path)
            except OSError:
                continue

            name_lower = dev.name.lower()
            if any(bad in name_lower for bad in self.IGNORED_KEYWORDS):
                continue

            caps = dev.capabilities()
            if ecodes.EV_KEY not in caps:
                continue

            supported_keys = set(caps[ecodes.EV_KEY])
            if self.REQUIRED_KEYS.issubset(supported_keys):
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

    # --- Output ---

    def _tap(self, code, use_shift=False):
        ecodes = self._ecodes
        if use_shift:
            self.ui.write(ecodes.EV_KEY, KEY_LEFTSHIFT, 1)
            self.ui.syn()
        self.ui.write(ecodes.EV_KEY, code, 1)
        self.ui.syn()
        self.ui.write(ecodes.EV_KEY, code, 0)
        self.ui.syn()
        if use_shift:
            self.ui.write(ecodes.EV_KEY, KEY_LEFTSHIFT, 0)
            self.ui.syn()

    def send_backspace(self):
        self._tap(KEY_BACKSPACE)
        time.sleep(BACKSPACE_DELAY)

    def replay_keys(self, key_sequence):
        """Replay a sequence of keystrokes with proper shift handling.

        Args:
            key_sequence: List of (keycode, shift_pressed) tuples to replay
        """
        for code, use_shift in key_sequence:
            self._tap(code, use_shift)
            time.sleep(KEY_REPLAY_DELAY)

    def reset_modifiers(self):
        """Force release all modifier keys to prevent stuck key states.

        Extended modifier list ensures clean state reset for all possible
        modifier keys that might interfere with subsequent operations.
        """
        ecodes = self._ecodes
        modifiers = [
            KEY_LEFTSHIFT, KEY_RIGHTSHIFT,
            KEY_LEFTCTRL, KEY_RIGHTCTRL,
            KEY_LEFTALT, KEY_RIGHTALT,
            KEY_LEFTMETA, KEY_RIGHTMETA
        ]

        # Release all modifiers
        for key in modifiers:
            self.ui.write(ecodes.EV_KEY, key, 0)
        self.ui.syn()

        # Allow OS time to update keyboard state before sending backspace
        time.sleep(MODIFIER_RESET_DELAY)

    def switch_layout(self):
        """Switch keyboard layout using configured hotkey combination.

        Prevents unintended menu activation (e.g., Alt menu in KDE) by
        releasing modifier keys before trigger keys.

        Strategy: Release Modifier (Alt) BEFORE releasing Trigger (Shift).
        Example: [Alt, Shift] -> Release Alt first -> State becomes Shift (Safe!)
        If we release Shift first -> State becomes Alt -> Release Alt -> Menu triggers.
        """
        if not self.switch_keys:
            return

        ecodes = self._ecodes

        # Press all keys (simultaneous press for better input system recognition)
        for k in self.switch_keys:
            self.ui.write(ecodes.EV_KEY, k, 1)
        self.ui.syn()

        # Hold to register the combo
        time.sleep(HOTKEY_PRESS_DURATION)

        # Release keys in same order (modifier first to prevent menu trigger)
        # DO NOT use reversed() here
        for k in self.switch_keys:
            self.ui.write(ecodes.EV_KEY, k, 0)
        self.ui.syn()

        # Allow layout to stabilize
        time.sleep(LAYOUT_SWITCH_SETTLE_TIME)

    def ensure_numlock_state(self):
        """Checks physical LED state and forces NumLock ON if currently OFF."""
        ecodes = self._ecodes
        try:
            # Active LEDs are returned as a list of integers
            active_leds = self.device.leds(verbose=False)

            # LED_NUML is the code for NumLock LED
            if ecodes.LED_NUML not in active_leds:
                logger.info("[i] NumLock is OFF. Forcing ON...")
                self._tap(KEY_NUMLOCK)
            else:
                logger.info("[✓] NumLock is already ON.")

        except Exception as err:
            logger.warning(f"[!] Could not check/set LEDs: {err}")

    # --- Input ---

    def run(self, on_event):
        """Feed (keycode, value) pairs from the physical keyboard to on_event."""
        ecodes = self._ecodes

        # Test device grab capability
        try:
            self.device.grab()
            self.device.ungrab()
        except Exception:
            pass

        try:
            for event in self.device.read_loop():
                if event.type == ecodes.EV_KEY:
                    on_event(event.code, event.value)
        except KeyboardInterrupt:
            sys.stderr.write("\n[✓] Stopped by user.\n")
        except OSError as err:
            logger.error(f"[✗] Device error: {err}")


# --- macOS: Carbon Text Input Source API (ctypes) ---
# PyObjC does not export the TIS* functions (checked against pyobjc 12.2.2),
# so the layout switcher talks to HIToolbox through ctypes directly.
class InputSourceSwitcher:
    """Cycles through the enabled keyboard layouts via TISSelectInputSource."""

    CARBON = '/System/Library/Frameworks/Carbon.framework/Carbon'
    COREFOUNDATION = '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
    UTF8 = 0x08000100  # kCFStringEncodingUTF8

    def __init__(self):
        import ctypes
        from ctypes import c_void_p, c_long, c_bool, c_char_p, c_int

        self._ctypes = ctypes
        self.carbon = ctypes.cdll.LoadLibrary(self.CARBON)
        self.cf = ctypes.cdll.LoadLibrary(self.COREFOUNDATION)

        self.cf.CFArrayGetCount.restype = c_long
        self.cf.CFArrayGetCount.argtypes = [c_void_p]
        self.cf.CFArrayGetValueAtIndex.restype = c_void_p
        self.cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
        self.cf.CFStringGetCString.restype = c_bool
        self.cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, c_int]
        self.cf.CFEqual.restype = c_bool
        self.cf.CFEqual.argtypes = [c_void_p, c_void_p]
        self.cf.CFRelease.argtypes = [c_void_p]

        self.carbon.TISCreateInputSourceList.restype = c_void_p
        self.carbon.TISCreateInputSourceList.argtypes = [c_void_p, c_bool]
        self.carbon.TISGetInputSourceProperty.restype = c_void_p
        self.carbon.TISGetInputSourceProperty.argtypes = [c_void_p, c_void_p]
        self.carbon.TISCopyCurrentKeyboardInputSource.restype = c_void_p
        self.carbon.TISSelectInputSource.restype = c_int
        self.carbon.TISSelectInputSource.argtypes = [c_void_p]

        self.prop_id = c_void_p.in_dll(self.carbon, 'kTISPropertyInputSourceID')
        self.prop_name = c_void_p.in_dll(self.carbon, 'kTISPropertyLocalizedName')
        self.prop_type = c_void_p.in_dll(self.carbon, 'kTISPropertyInputSourceType')
        self.type_layout = c_void_p.in_dll(self.carbon, 'kTISTypeKeyboardLayout')

        self._list = None
        self._seen = self.current_id()
        self._previous = None

    def _to_str(self, cfstring):
        if not cfstring:
            return None
        buf = self._ctypes.create_string_buffer(512)
        if self.cf.CFStringGetCString(cfstring, buf, 512, self.UTF8):
            return buf.value.decode('utf-8', 'replace')
        return None

    def _prop(self, source, prop):
        return self._to_str(self.carbon.TISGetInputSourceProperty(source, prop))

    def layouts(self):
        """Return the enabled keyboard layouts as (source_ptr, id, name) tuples.

        The returned CFArray is kept alive on the instance: the source pointers
        are borrowed from it and would dangle if it were released.
        """
        if self._list:
            self.cf.CFRelease(self._list)
        self._list = self.carbon.TISCreateInputSourceList(None, False)
        result = []
        if not self._list:
            return result
        for i in range(self.cf.CFArrayGetCount(self._list)):
            src = self.cf.CFArrayGetValueAtIndex(self._list, i)
            src_type = self.carbon.TISGetInputSourceProperty(src, self.prop_type)
            if not self.cf.CFEqual(src_type, self.type_layout):
                continue  # skip input methods (PressAndHold, CharacterPalette, ...)
            result.append((src, self._prop(src, self.prop_id), self._prop(src, self.prop_name)))
        return result

    def current_id(self):
        src = self.carbon.TISCopyCurrentKeyboardInputSource()
        if not src:
            return None
        source_id = self._prop(src, self.prop_id)
        self.cf.CFRelease(src)
        return source_id

    def note_current(self):
        """Remember the layout that was active before the current one.

        Called on every key press: a layout change made by the user (menu bar,
        Ctrl+Space, Fn) is only visible to us through polling.
        """
        current = self.current_id()
        if current != self._seen:
            self._previous, self._seen = self._seen, current

    def switch_next(self):
        """Select the layout used before the current one, falling back to the
        next enabled layout. Returns its id, or None.

        With three or more layouts, cycling would pick whatever happens to be
        next in the list; the previously used layout is the one the user most
        likely meant to type in.
        """
        layouts = self.layouts()
        if len(layouts) < 2:
            logger.warning("[!] Less than two keyboard layouts enabled - nothing to switch to.")
            return None

        current = self.current_id()
        index = next((i for i, (_, sid, _) in enumerate(layouts) if sid == current), -1)
        target, target_id, target_name = next(
            (layout for layout in layouts if layout[1] == self._previous and self._previous != current),
            layouts[(index + 1) % len(layouts)])

        status = self.carbon.TISSelectInputSource(target)
        if status != 0:
            logger.error(f"[✗] TISSelectInputSource failed (OSStatus {status})")
            return None
        logger.info(f"[i] Layout -> {target_name} ({target_id})")
        return target_id


def _running_binary():
    """Path macOS privacy checks apply to. A framework Python re-execs Python.app,
    so sys.executable (the venv path) would name the wrong binary."""
    import os
    import subprocess
    out = subprocess.run(["ps", "-o", "comm=", "-p", str(os.getpid())],
                         capture_output=True, text=True).stdout.strip()
    return out or sys.executable


class MacBackend:
    """Quartz event tap (input) + CGEventPost (output) + TIS (layout switch)."""

    name = "macos"
    supports_numlock = False
    supports_hotkey_styles = False

    # Marker written into kCGEventSourceUserData so the tap can tell our own
    # synthetic events apart from real keystrokes. Without it, every injected
    # backspace and replayed key would come straight back into the buffer.
    MAGIC = 0x4D475348  # 'MGSH'

    # Carbon kVK_* virtual key codes -> internal key codes
    MAC_TO_KEY = {
        0x00: KEY_A, 0x01: KEY_S, 0x02: KEY_D, 0x03: KEY_F, 0x04: KEY_H, 0x05: KEY_G,
        0x06: KEY_Z, 0x07: KEY_X, 0x08: KEY_C, 0x09: KEY_V, 0x0B: KEY_B,
        0x0C: KEY_Q, 0x0D: KEY_W, 0x0E: KEY_E, 0x0F: KEY_R, 0x10: KEY_Y, 0x11: KEY_T,
        0x12: KEY_1, 0x13: KEY_2, 0x14: KEY_3, 0x15: KEY_4, 0x16: KEY_6, 0x17: KEY_5,
        0x18: KEY_EQUAL, 0x19: KEY_9, 0x1A: KEY_7, 0x1B: KEY_MINUS, 0x1C: KEY_8, 0x1D: KEY_0,
        0x1E: KEY_RIGHTBRACE, 0x1F: KEY_O, 0x20: KEY_U, 0x21: KEY_LEFTBRACE,
        0x22: KEY_I, 0x23: KEY_P, 0x24: KEY_ENTER, 0x25: KEY_L, 0x26: KEY_J,
        0x27: KEY_APOSTROPHE, 0x28: KEY_K, 0x29: KEY_SEMICOLON, 0x2A: KEY_BACKSLASH,
        0x2B: KEY_COMMA, 0x2C: KEY_SLASH, 0x2D: KEY_N, 0x2E: KEY_M, 0x2F: KEY_DOT,
        0x30: KEY_TAB, 0x31: KEY_SPACE, 0x32: KEY_GRAVE, 0x33: KEY_BACKSPACE, 0x35: KEY_ESC,
        0x36: KEY_RIGHTMETA, 0x37: KEY_LEFTMETA, 0x38: KEY_LEFTSHIFT, 0x39: KEY_CAPSLOCK,
        0x3A: KEY_LEFTALT, 0x3B: KEY_LEFTCTRL, 0x3C: KEY_RIGHTSHIFT,
        0x3D: KEY_RIGHTALT, 0x3E: KEY_RIGHTCTRL, 0x4C: KEY_KPENTER,
    }
    KEY_TO_MAC = {v: k for k, v in MAC_TO_KEY.items()}

    # Device-dependent modifier bits (NX_DEVICE*KEYMASK), used to turn a
    # flagsChanged event into a press/release for one specific physical key.
    MODIFIER_BITS = {
        0x38: 0x00000002,  # left shift
        0x3C: 0x00000004,  # right shift
        0x3B: 0x00000001,  # left control
        0x3E: 0x00002000,  # right control
        0x3A: 0x00000020,  # left option
        0x3D: 0x00000040,  # right option
        0x37: 0x00000008,  # left command
        0x36: 0x00000010,  # right command
    }

    FLAG_SHIFT = 0x00020000  # kCGEventFlagMaskShift

    def __init__(self, device_path=None, switch_keys=None):
        if device_path:
            logger.warning("[!] --device is ignored on macOS: the event tap is system-wide.")
        if switch_keys:
            logger.info("[i] Hotkey style is ignored on macOS: layouts switch via the TIS API.")

        try:
            import Quartz
        except ImportError:
            logger.error("[✗] PyObjC is missing. Install it with: pip3 install pyobjc-framework-Quartz")
            sys.exit(1)

        self.q = Quartz
        self.switcher = InputSourceSwitcher()
        self.tap = None
        self._running = True
        self._on_event = None

    # --- Output ---

    def _post(self, mac_code, down, flags=0):
        q = self.q
        event = q.CGEventCreateKeyboardEvent(None, mac_code, bool(down))
        if event is None:
            return
        q.CGEventSetFlags(event, flags)
        q.CGEventSetIntegerValueField(event, q.kCGEventSourceUserData, self.MAGIC)
        q.CGEventPost(q.kCGHIDEventTap, event)

    def _tap_key(self, mac_code, flags=0):
        self._post(mac_code, True, flags)
        self._post(mac_code, False, flags)

    def send_backspace(self):
        self._tap_key(self.KEY_TO_MAC[KEY_BACKSPACE])
        time.sleep(BACKSPACE_DELAY)

    def replay_keys(self, key_sequence):
        """Replay a sequence of keystrokes, carrying the shift state in the
        event flags rather than as separate shift key events."""
        for code, use_shift in key_sequence:
            mac_code = self.KEY_TO_MAC.get(code)
            if mac_code is None:
                continue
            self._tap_key(mac_code, self.FLAG_SHIFT if use_shift else 0)
            time.sleep(KEY_REPLAY_DELAY)

    def reset_modifiers(self):
        """No-op on macOS: every event we post carries explicit flags, so a
        physically held modifier cannot leak into the injected keystrokes."""
        return

    def switch_layout(self):
        self.switcher.switch_next()
        time.sleep(LAYOUT_SWITCH_SETTLE_TIME)

    def ensure_numlock_state(self):
        logger.warning("[!] NumLock does not exist on macOS - option ignored.")

    @staticmethod
    def list_available():
        switcher = InputSourceSwitcher()
        current = switcher.current_id()
        print(f"{'ACTIVE':<7} | {'ID':<40} | NAME")
        print("-" * 80)
        for _, source_id, name in switcher.layouts():
            mark = '  *' if source_id == current else ''
            print(f"{mark:<7} | {source_id:<40} | {name}")

    # --- Input ---

    @staticmethod
    def accessibility_granted() -> bool:
        """True when the process may post synthetic keystrokes.

        Without Accessibility, CGEventPost fails silently: the tap still sees
        keys, but nothing gets typed back. Worth reporting explicitly.
        """
        import ctypes
        path = '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
        try:
            lib = ctypes.cdll.LoadLibrary(path)
            lib.AXIsProcessTrusted.restype = ctypes.c_bool
            return bool(lib.AXIsProcessTrusted())
        except Exception:
            return True  # cannot tell - assume fine rather than nag

    def _callback(self, proxy, event_type, event, refcon):
        q = self.q

        # The system disables a tap that takes too long; re-arm it.
        if event_type in (q.kCGEventTapDisabledByTimeout, q.kCGEventTapDisabledByUserInput):
            q.CGEventTapEnable(self.tap, True)
            return event

        # Skip the keystrokes we injected ourselves.
        if q.CGEventGetIntegerValueField(event, q.kCGEventSourceUserData) == self.MAGIC:
            return event

        mac_code = q.CGEventGetIntegerValueField(event, q.kCGKeyboardEventKeycode)
        code = self.MAC_TO_KEY.get(mac_code)
        if code is None:
            return event

        if event_type == q.kCGEventFlagsChanged:
            flags = q.CGEventGetFlags(event)
            bit = self.MODIFIER_BITS.get(mac_code)
            if bit is None:
                value = 1  # CapsLock and friends: report every toggle as a press
            else:
                value = 1 if (flags & bit) else 0
        elif event_type == q.kCGEventKeyDown:
            value = 2 if q.CGEventGetIntegerValueField(event, q.kCGKeyboardEventAutorepeat) else 1
            if value == 1:
                self.switcher.note_current()
        elif event_type == q.kCGEventKeyUp:
            value = 0
        else:
            return event

        self._on_event(code, value)
        return event

    def run(self, on_event):
        """Feed (keycode, value) pairs from the global event tap to on_event."""
        q = self.q
        self._on_event = on_event

        if not self.accessibility_granted():
            logger.warning("[!] Accessibility is not granted - corrections will be silently dropped.")
            logger.warning(f"    System Settings -> Privacy & Security -> Accessibility -> {_running_binary()}")

        mask = 0
        for event_type in (q.kCGEventKeyDown, q.kCGEventKeyUp, q.kCGEventFlagsChanged):
            mask |= q.CGEventMaskBit(event_type)

        self.tap = q.CGEventTapCreate(
            q.kCGSessionEventTap,
            q.kCGHeadInsertEventTap,
            q.kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )

        if self.tap is None:
            logger.error("[✗] Could not create the event tap.")
            logger.error("    Grant Input Monitoring and Accessibility to the binary running MagShift:")
            logger.error(f"    {_running_binary()}")
            logger.error("    System Settings -> Privacy & Security -> Input Monitoring / Accessibility")
            sys.exit(1)

        source = q.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        q.CFRunLoopAddSource(q.CFRunLoopGetCurrent(), source, q.kCFRunLoopCommonModes)
        q.CGEventTapEnable(self.tap, True)

        # ponytail: the correction runs inline in the tap callback, which blocks
        # the run loop for a few hundred milliseconds. Acceptable because the
        # user is not typing while their own correction plays back, and a tap
        # disabled by timeout is re-armed in _callback. Move the correction to a
        # worker thread if that ever proves too slow.
        try:
            while self._running:
                q.CFRunLoopRunInMode(q.kCFRunLoopDefaultMode, 0.5, False)
        except KeyboardInterrupt:
            sys.stderr.write("\n[✓] Stopped by user.\n")
        finally:
            q.CGEventTapEnable(self.tap, False)


def backend_class():
    """Return the backend class for the current platform."""
    if sys.platform == 'darwin':
        return MacBackend
    if sys.platform.startswith('linux'):
        return LinuxBackend
    logger.error(f"[✗] Unsupported platform: {sys.platform}")
    sys.exit(1)


# ==============================================================================
# Platform-neutral state machine
# ==============================================================================

class MagShift:
    def __init__(self, backend, pause_trigger=False):
        """Initialize MagShift with a platform backend and state.

        Args:
            backend: LinuxBackend, MacBackend or any object with the same methods
            pause_trigger: Also correct on a single Pause press (Punto Switcher style)
        """
        self.backend = backend
        self.pause_trigger = pause_trigger

        self.input_buffer = InputBuffer()
        self.last_press_time = 0
        self.trigger_released = True
        self.trigger_btn = (KEY_LEFTSHIFT, KEY_RIGHTSHIFT)
        self.shift_pressed = False
        self.ctrl_pressed = False
        self.meta_pressed = False
        self.alt_pressed = False
        self.pending_action = False

    def ensure_numlock_state(self):
        """Force NumLock ON where the platform supports it."""
        self.backend.ensure_numlock_state()

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
            logger.debug("[!] Buffer empty.")
            return

        # Buffer is intentionally kept, so a second double-press retypes the
        # same phrase back into the original layout.

        self.backend.reset_modifiers()

        readable_text = decode_keys(keys_to_replay)
        logger.info(f"[>] Correcting: '{readable_text}'")

        # Delete the phrase
        for _ in range(len(keys_to_replay)):
            self.backend.send_backspace()

        # Switch layout
        self.backend.switch_layout()

        # Replay in new layout
        self.backend.replay_keys(keys_to_replay)

    def handle_event(self, code, value):
        """Process one key event.

        Args:
            code: internal key code
            value: 0 = release, 1 = press, 2 = autorepeat
        """
        # Track modifier keys state
        if code in [KEY_LEFTMETA, KEY_RIGHTMETA]:
            self.meta_pressed = (value == 1 or value == 2)
            if value == 1:  # On press only
                self.input_buffer.buffer = []  # Clear buffer immediately

        elif code == KEY_CAPSLOCK:
            if value == 1:  # On press only
                self.input_buffer.buffer = []  # Clear buffer immediately

        elif code in [KEY_LEFTSHIFT, KEY_RIGHTSHIFT]:
            self.shift_pressed = (value == 1 or value == 2)
        elif code in [KEY_LEFTCTRL, KEY_RIGHTCTRL]:
            self.ctrl_pressed = (value == 1 or value == 2)
        elif code in [KEY_LEFTALT]:  # KEY_RIGHTALT is important for Ґ
            self.alt_pressed = (value == 1 or value == 2)

        # Optional instant trigger: a single Pause press
        if code == KEY_PAUSE:
            if value == 1 and self.pause_trigger:
                self.fix_last_word()
            return

        # Handle trigger key (Shift)
        if code in self.trigger_btn:

            # Key press
            if value == 1:
                now = time.time()
                if (now - self.last_press_time < DOUBLE_PRESS_DELAY) and self.trigger_released:
                    self.pending_action = True
                    self.last_press_time = 0
                else:
                    self.last_press_time = now
                    self.pending_action = False

                self.trigger_released = False

            # Key release
            elif value == 0:
                self.trigger_released = True

                # Execute correction on double-press
                if self.pending_action:
                    self.fix_last_word()
                    self.pending_action = False

        # Track other keys in buffer
        elif value in [1, 2]:
            modifier_pressed = self.ctrl_pressed or self.meta_pressed or self.alt_pressed
            self.input_buffer.add(code, self.shift_pressed, modifier_pressed)

            # Cancel pending action if other key pressed
            if self.last_press_time > 0:
                self.last_press_time = 0

    def run(self):
        """Main event loop: hand control to the backend and correct on demand.

        Triggers layout correction on double-press of Shift. The loop handles:
        - Shift key state tracking for proper case handling
        - Double-press detection with configurable delay
        - Keystroke buffering for correction replay
        - Graceful shutdown on Ctrl+C
        """
        logger.info(f"[>] MagShift v{VERSION} ({self.backend.name})")
        self.backend.run(self.handle_event)


def main():
    """Main entry point for MagShift application."""
    parser = argparse.ArgumentParser(description="MagShift - Advanced Keyboard Layout Switcher with Instant Correction Engine")

    parser.add_argument("-d", "--device", help="Path to input device (Linux only, optional)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--list", action="store_true", help="List available devices (Linux) or keyboard layouts (macOS)")
    parser.add_argument("-k", "--hotkey", choices=HOTKEY_STYLES.keys(), default="meta", help="Hotkey style (Linux only)")

    parser.add_argument("-n", "--numlock", action="store_true", help="Force NumLock ON and exit (Linux only)")
    parser.add_argument("--auto-numlock", action="store_true", help="Enable NumLock on start (Linux service mode)")
    parser.add_argument("-p", "--pause", action="store_true", help="Also correct on a single Pause press (Linux)")

    args = parser.parse_args()

    if args.list:
        backend_class().list_available()
        sys.exit(0)

    if args.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)

    # Resolve keys based on argument
    selected_keys = HOTKEY_STYLES[args.hotkey]
    if args.verbose:
        logger.info(f"[i] Using hotkey style: {args.hotkey} -> {selected_keys}")

    app = MagShift(backend_class()(device_path=args.device, switch_keys=selected_keys), pause_trigger=args.pause)

    # If --NumLock is passed, just do that and exit
    if args.auto_numlock or args.numlock:
        app.ensure_numlock_state()

    if args.numlock:
        sys.exit(0)

    # Otherwise run the full listener
    app.run()


if __name__ == "__main__":
    main()
