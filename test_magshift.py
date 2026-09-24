#!/usr/bin/env python3
"""Self-check for the platform-neutral half of MagShift.

Runs on any platform: it never touches evdev or Quartz, it drives the state
machine through a recording fake backend.

    python3 test_magshift.py
"""

import os
import sys
import time
import types
from unittest import mock

import main
from main import (
    InputBuffer, MagShift, decode_keys,
    KEY_A, KEY_B, KEY_C, KEY_1, KEY_SPACE, KEY_ENTER, KEY_TAB,
    KEY_BACKSPACE, KEY_RIGHTSHIFT, KEY_LEFTCTRL, KEY_PAUSE,
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
    return MagShift(FakeBackend())


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


def test_pause_is_ignored_by_default():
    app = make_app()
    tap(app, KEY_A)
    tap(app, KEY_PAUSE)
    assert app.backend.log == []


def test_pause_triggers_correction_when_enabled():
    app = MagShift(FakeBackend(), pause_trigger=True)
    tap(app, KEY_A)
    tap(app, KEY_PAUSE)
    kinds = [entry[0] for entry in app.backend.log]
    assert kinds == ['reset', 'backspace', 'switch', 'replay'], kinds


# --- Linux backend, exercised against a stub evdev ---
# The refactor moved every evdev call into LinuxBackend; this check keeps the
# emitted uinput sequence identical without needing a Linux box.

class _StubEcodes:
    EV_KEY = 1
    EV_LED = 17
    LED_NUML = 0


class _StubUInput:
    def __init__(self, *args, **kwargs):
        self.writes = []

    def write(self, etype, code, value):
        self.writes.append((code, value))

    def syn(self):
        pass


class _StubInputDevice:
    """Backed by a pipe, so the backend's selector waits on it like on a real /dev/input/event* node."""

    KEYBOARD = [KEY_A, main.KEY_Z, KEY_SPACE, KEY_ENTER]

    def __init__(self, path, name="Stub Keyboard", keys=KEYBOARD):
        self.path = path
        self.name = name
        self.keys = keys
        self.queue = []
        self.unplugged = False
        self.read_fd, self.write_fd = os.pipe()

    def fileno(self):
        return self.read_fd

    def capabilities(self):
        return {_StubEcodes.EV_KEY: self.keys, _StubEcodes.EV_LED: [_StubEcodes.LED_NUML]}

    def leds(self, verbose=False):
        return []

    def close(self):
        os.close(self.read_fd)
        os.close(self.write_fd)

    def press(self, code):
        self.queue.append(types.SimpleNamespace(type=_StubEcodes.EV_KEY, code=code, value=1))
        os.write(self.write_fd, b'.')

    def unplug(self):
        self.unplugged = True
        os.write(self.write_fd, b'.')

    def read(self):
        os.read(self.read_fd, 1)
        if self.unplugged:
            raise OSError(19, "No such device")
        return [self.queue.pop(0)]


def _install_stub_evdev(devices=None):
    """Stub evdev. With devices ({path: _StubInputDevice}) it lists and opens exactly those."""
    module = types.ModuleType('evdev')
    module.ecodes = _StubEcodes
    module.UInput = _StubUInput
    module.InputDevice = devices.__getitem__ if devices else _StubInputDevice
    module.list_devices = (lambda: list(devices)) if devices else (lambda: ['/dev/input/event0'])
    sys.modules['evdev'] = module
    return module


def test_linux_backend_emits_expected_uinput_sequence():
    _install_stub_evdev()
    with mock.patch.dict(os.environ, {}, clear=True):  # no X11 session: a real XTEST would type into it
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


class _StubXTest(_StubUInput):
    pass


def test_linux_backend_types_through_xtest_only_on_x11():
    _install_stub_evdev()
    sessions = [
        ({'DISPLAY': ':0'}, True),
        ({'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'}, False),  # Xwayland: X apps only
        ({'DISPLAY': ':0', 'XDG_SESSION_TYPE': 'wayland'}, False),
        ({}, False),  # console or system service
    ]
    for env, expect_xtest in sessions:
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(main, 'XTestKeyboard', _StubXTest):
            backend = main.LinuxBackend(device_path='/dev/input/event0')
        assert isinstance(backend.ui, _StubXTest) == expect_xtest, env


def test_xtest_layout_is_synced_before_the_first_keystroke():
    class RecordingXTest(_StubXTest):
        def sync_layout(self):
            self.writes.append('sync')

    _install_stub_evdev()
    with mock.patch.dict(os.environ, {'DISPLAY': ':0'}, clear=True), \
            mock.patch.object(main, 'XTestKeyboard', RecordingXTest):
        backend = main.LinuxBackend(device_path='/dev/input/event0')
        backend.reset_modifiers()
    assert backend.ui.writes[0] == 'sync', backend.ui.writes


class _Stop(Exception):
    pass


def _run_until(backend, received, count):
    """Run the backend loop until on_event has collected count key codes in total."""
    def on_event(code, value):
        received.append(code)
        if len(received) == count:
            raise _Stop
    try:
        backend.run(on_event)
    except _Stop:
        pass


def test_linux_backend_reads_every_keyboard_across_hotplug():
    laptop = _StubInputDevice('/dev/input/event0', "AT Translated Set 2 keyboard")
    external = _StubInputDevice('/dev/input/event1', "Keychron K2")
    devices = {
        laptop.path: laptop,
        external.path: external,
        '/dev/input/event2': _StubInputDevice('/dev/input/event2', "Power Button", keys=[116]),
        '/dev/input/event3': _StubInputDevice('/dev/input/event3', main.LinuxBackend.VIRTUAL_NAME),
    }
    _install_stub_evdev(devices)
    with mock.patch.dict(os.environ, {}, clear=True):
        backend = main.LinuxBackend()
    assert sorted(backend.devices) == [laptop.path, external.path], backend.devices

    received = []
    external.press(KEY_A)  # typing on the keyboard that is not found first
    _run_until(backend, received, 1)

    laptop.unplug()  # the other keyboards keep working
    del devices[laptop.path]
    external.press(KEY_B)
    _run_until(backend, received, 2)

    usb = _StubInputDevice(laptop.path, "USB Keyboard")  # plugged in while running, reusing the freed path
    devices[usb.path] = usb
    usb.press(KEY_C)
    backend.RESCAN_INTERVAL = 0
    _run_until(backend, received, 3)

    assert received == [KEY_A, KEY_B, KEY_C], received
    assert backend.devices == {usb.path: usb, external.path: external}, backend.devices


def test_linux_backend_keeps_the_keyboard_when_the_correction_fails():
    keyboard = _StubInputDevice('/dev/input/event0')
    _install_stub_evdev({keyboard.path: keyboard})
    with mock.patch.dict(os.environ, {}, clear=True):
        backend = main.LinuxBackend()

    def failing_correction(code, value):
        raise OSError(5, "uinput write failed")

    keyboard.press(KEY_A)
    try:
        backend.run(failing_correction)
    except OSError:
        pass
    assert keyboard.path in backend.devices, "an output error was taken for an unplugged keyboard"


def test_linux_backend_exits_when_the_manual_device_is_gone():
    keyboard = _StubInputDevice('/dev/input/event7')
    _install_stub_evdev({keyboard.path: keyboard})
    with mock.patch.dict(os.environ, {}, clear=True):
        backend = main.LinuxBackend(device_path=keyboard.path)
    keyboard.unplug()
    try:
        backend.run(lambda code, value: None)
    except SystemExit as exit_:
        assert exit_.code == 1
    else:
        raise AssertionError("run() kept going without its only device")


def test_running_binary_is_real_file():
    if sys.platform != 'darwin':
        return  # on Linux `ps -o comm=` prints a bare name, and the path is only used in macOS messages
    import os
    assert os.path.isfile(main._running_binary()), main._running_binary()


def test_switcher_prefers_previous_layout():
    class Carbon:
        selected = None
        def TISSelectInputSource(self, src):
            Carbon.selected = src
            return 0

    sw = object.__new__(main.InputSourceSwitcher)
    sw.carbon = Carbon()
    state = {'cur': 'uk'}
    sw.current_id = lambda: state['cur']
    sw.layouts = lambda: [('RU', 'ru', 'Russian'), ('UK', 'uk', 'Ukrainian'), ('US', 'us', 'U.S.')]
    sw._seen, sw._previous, sw._list = 'uk', None, None

    state['cur'] = 'us'
    sw.note_current()               # user switched Ukrainian -> U.S.
    assert sw.switch_next() == 'uk' and Carbon.selected == 'UK'

    sw._previous = None             # nothing known yet: fall back to next in list
    assert sw.switch_next() == 'ru'


def main_():
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    main_()
