#!/usr/bin/env python3
"""Self-check for the platform-neutral half of MagShift.

Runs on any platform: it never touches evdev or Quartz, it drives the state
machine through a recording fake backend.

    python3 test_magshift.py
"""

import time

import main
from main import (
    InputBuffer, MagShift, decode_keys,
    KEY_A, KEY_B, KEY_C, KEY_1, KEY_SPACE, KEY_ENTER, KEY_TAB,
    KEY_BACKSPACE, KEY_RIGHTSHIFT, KEY_LEFTCTRL,
)


class FakeBackend:
    """Records what the state machine asked the platform to do."""

    name = "fake"

    def __init__(self):
        self.log = []

    def reset_modifiers(self):
        self.log.append(('reset',))

    def send_backspace(self):
        self.log.append(('backspace',))

    def switch_layout(self):
        self.log.append(('switch',))

    def replay_keys(self, seq):
        self.log.append(('replay', list(seq)))

    def ensure_numlock_state(self):
        self.log.append(('numlock',))

    def run(self, on_event):
        raise AssertionError("FakeBackend.run should not be reached in tests")


def make_app():
    app = MagShift.__new__(MagShift)
    app.backend = FakeBackend()
    app.input_buffer = InputBuffer()
    app.last_press_time = 0
    app.trigger_released = True
    app.trigger_btn = (main.KEY_LEFTSHIFT, main.KEY_RIGHTSHIFT)
    app.shift_pressed = False
    app.ctrl_pressed = False
    app.meta_pressed = False
    app.alt_pressed = False
    app.pending_action = False
    return app


def tap(app, code):
    app.handle_event(code, 1)
    app.handle_event(code, 0)


def test_decode_keys():
    assert decode_keys([(KEY_A, False), (KEY_B, False)]) == "ab"
    assert decode_keys([(KEY_A, True), (KEY_B, False)]) == "Ab"
    assert decode_keys([(KEY_1, True)]) == "!"
    assert decode_keys([(KEY_SPACE, False)]) == " "


def test_buffer_basics():
    buf = InputBuffer()
    buf.add(KEY_A, False)
    buf.add(KEY_B, True)
    assert buf.get_last_phrase() == [(KEY_A, False), (KEY_B, True)]

    buf.add(KEY_BACKSPACE, False)
    assert buf.get_last_phrase() == [(KEY_A, False)]

    buf.add(KEY_ENTER, False)
    assert buf.get_last_phrase() == []


def test_buffer_clears_on_modifier_and_tab():
    buf = InputBuffer()
    buf.add(KEY_A, False)
    buf.add(KEY_C, False, modifier_pressed=True)  # Ctrl+C
    assert buf.get_last_phrase() == []

    buf.add(KEY_A, False)
    buf.add(KEY_TAB, False)
    assert buf.get_last_phrase() == []


def test_buffer_timeout_and_cap():
    buf = InputBuffer()
    buf.add(KEY_A, False)
    buf.last_key_time = time.time() - (main.TYPING_TIMEOUT + 1)
    buf.add(KEY_B, False)
    assert buf.get_last_phrase() == [(KEY_B, False)]

    buf = InputBuffer()
    for _ in range(main.MAX_BUFFER_SIZE + 5):
        buf.add(KEY_A, False)
    assert len(buf.get_last_phrase()) == main.MAX_BUFFER_SIZE


def test_double_press_triggers_correction():
    app = make_app()
    tap(app, KEY_A)
    tap(app, KEY_B)
    tap(app, KEY_RIGHTSHIFT)
    tap(app, KEY_RIGHTSHIFT)

    kinds = [entry[0] for entry in app.backend.log]
    assert kinds == ['reset', 'backspace', 'backspace', 'switch', 'replay'], kinds
    assert app.backend.log[-1][1] == [(KEY_A, False), (KEY_B, False)]


def test_single_press_does_nothing():
    app = make_app()
    tap(app, KEY_A)
    tap(app, KEY_RIGHTSHIFT)
    assert app.backend.log == []


def test_slow_double_press_does_nothing():
    app = make_app()
    tap(app, KEY_A)
    tap(app, KEY_RIGHTSHIFT)
    app.last_press_time -= (main.DOUBLE_PRESS_DELAY + 0.1)
    tap(app, KEY_RIGHTSHIFT)
    assert app.backend.log == []


def test_key_between_shifts_cancels():
    app = make_app()
    tap(app, KEY_A)
    tap(app, KEY_RIGHTSHIFT)
    tap(app, KEY_B)
    tap(app, KEY_RIGHTSHIFT)
    assert app.backend.log == []


def test_shift_state_is_recorded():
    app = make_app()
    app.handle_event(main.KEY_LEFTSHIFT, 1)
    tap(app, KEY_A)
    app.handle_event(main.KEY_LEFTSHIFT, 0)
    tap(app, KEY_B)
    assert app.input_buffer.get_last_phrase() == [(KEY_A, True), (KEY_B, False)]


def test_ctrl_combo_clears_buffer():
    app = make_app()
    tap(app, KEY_A)
    app.handle_event(KEY_LEFTCTRL, 1)
    tap(app, KEY_C)
    app.handle_event(KEY_LEFTCTRL, 0)
    assert app.input_buffer.get_last_phrase() == []


def test_empty_buffer_skips_correction():
    app = make_app()
    tap(app, KEY_RIGHTSHIFT)
    tap(app, KEY_RIGHTSHIFT)
    assert app.backend.log == []


# --- Linux backend, exercised against a stub evdev ---
# The refactor moved every evdev call into LinuxBackend; this check keeps the
# emitted uinput sequence identical without needing a Linux box.

class _StubEcodes:
    EV_KEY = 1
    LED_NUML = 0


class _StubUInput:
    def __init__(self, *args, **kwargs):
        self.writes = []

    def write(self, etype, code, value):
        self.writes.append((code, value))

    def syn(self):
        pass


class _StubInputDevice:
    def __init__(self, path):
        self.path = path
        self.name = "Stub Keyboard"

    def leds(self, verbose=False):
        return []


def _install_stub_evdev():
    import sys as _sys
    import types
    module = types.ModuleType('evdev')
    module.ecodes = _StubEcodes
    module.UInput = _StubUInput
    module.InputDevice = _StubInputDevice
    module.list_devices = lambda: ['/dev/input/event0']
    _sys.modules['evdev'] = module
    return module


def test_linux_backend_emits_expected_uinput_sequence():
    _install_stub_evdev()
    backend = main.LinuxBackend(device_path='/dev/input/event0',
                                switch_keys=main.HOTKEY_STYLES['alt'])

    backend.ui.writes.clear()
    backend.replay_keys([(KEY_A, False), (KEY_B, True)])
    assert backend.ui.writes == [
        (KEY_A, 1), (KEY_A, 0),
        (main.KEY_LEFTSHIFT, 1), (KEY_B, 1), (KEY_B, 0), (main.KEY_LEFTSHIFT, 0),
    ], backend.ui.writes

    backend.ui.writes.clear()
    backend.send_backspace()
    assert backend.ui.writes == [(KEY_BACKSPACE, 1), (KEY_BACKSPACE, 0)]

    # Modifier is released before the trigger key - see LinuxBackend.switch_layout
    backend.ui.writes.clear()
    backend.switch_layout()
    assert backend.ui.writes == [
        (main.KEY_LEFTALT, 1), (main.KEY_LEFTSHIFT, 1),
        (main.KEY_LEFTALT, 0), (main.KEY_LEFTSHIFT, 0),
    ], backend.ui.writes

    backend.ui.writes.clear()
    backend.ensure_numlock_state()
    assert backend.ui.writes == [(main.KEY_NUMLOCK, 1), (main.KEY_NUMLOCK, 0)]


def main_():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    main_()
