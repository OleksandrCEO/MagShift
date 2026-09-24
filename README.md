# MagShift 🪄

[![NixOS](https://img.shields.io/badge/NixOS-25.11+-5277C3?style=flat&logo=nixos&logoColor=white)](#%EF%B8%8F-nixos-installation-flake)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

**MagShift** - Advanced Keyboard Layout Switcher with Instant Correction Engine for Linux (Wayland & X11) and macOS.
It fixes what you just typed without making you retype it.

Typed `ghbdsn` instead of `привіт`? Tap **Shift** twice: MagShift deletes the phrase, switches the layout and types
it again correctly. Tap twice again to undo.

🇺🇦 [Коротка версія українською](./README.uk.md)

Designed with **NixOS Flakes** in mind for reproducible and secure deployment. Also supports other Linux distros via
a simple installer script, and macOS via a LaunchAgent:

[![Ubuntu](https://img.shields.io/badge/Ubuntu-Supported-E95420?style=flat&logo=ubuntu&logoColor=white)](#-installation-ubuntu--fedora--arch)
[![Fedora](https://img.shields.io/badge/Fedora-Supported-51A2DA?style=flat&logo=fedora&logoColor=white)](#-installation-ubuntu--fedora--arch)
[![Arch](https://img.shields.io/badge/Arch-Supported-1793D1?style=flat&logo=archlinux&logoColor=white)](#-installation-ubuntu--fedora--arch)
[![macOS](https://img.shields.io/badge/macOS-12+-000000?style=flat&logo=apple&logoColor=white)](#-installation-macos)

## Contents

- [Features](#-features)
- [How it works](#-how-it-works)
- [NixOS Installation (Flake)](#%EF%B8%8F-nixos-installation-flake)
- [Installation (Ubuntu / Fedora / Arch)](#-installation-ubuntu--fedora--arch)
- [Installation (macOS)](#-installation-macos)
- [Usage](#-usage)
- [Autostart (Linux)](#-autostart-linux)
- [Manual Usage (Development)](#%EF%B8%8F-manual-usage-development)
- [Related](#-related)

## ✨ Features

* **⚡ Double Shift:** Tap either `Shift` twice to switch layout (e.g., English ↔ Ukrainian). Tap twice again to undo.
* **🖋️ Auto-Correction:** Corrects the **last typed phrase** when you switch, not just the last word.
* **⏸️ Pause key (optional):** Punto Switcher style: a single `Pause` press corrects too. Off by default.
* **🎛️ Works with your hotkey:** On Linux it emulates the switch hotkey you already use: Meta+Space, Alt+Shift,
  Ctrl+Shift, CapsLock or the Menu key.
* **🔒 Secure:** Runs with dynamic permissions (via Udev ACLs), no manual group configuration required.
* **❄️ Pure Nix:** Zero global dependencies. Builds cleanly from the Nix Store.
* **🍎 macOS Native:** Uses a Quartz event tap and the Text Input Source API - no hotkey emulation, no extra daemons.

## 🧠 How it works

MagShift listens to the physical keyboard and remembers the last phrase you typed (up to 20 keystrokes, reset after
1 second of silence, on `Enter`/`Tab`/`Esc`, or when a shortcut like `Ctrl+C` is pressed). On a double `Shift` it:

1. sends `Backspace` for every remembered keystroke,
2. switches the layout (Linux: emulates your system hotkey; macOS: selects the input source directly),
3. replays the phrase, keeping the shift state of every key.

Nothing is stored beyond those 20 keystrokes, the clipboard is never touched, and no data leaves your machine.

---

## ❄️ NixOS Installation (Flake)

Since this project exports a NixOS module, installation is clean, but requires an overlay to make the package
available to the system.

### 1. Add to `flake.nix`

Add the input, import the module, and **apply the overlay** in your system configuration:

    {
      inputs = {
        nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";

        # Add MagShift input
        magshift.url = "github:OleksandrCEO/MagShift";
        # magshift.inputs.nixpkgs.follows = "nixpkgs";
      };

      outputs = { self, nixpkgs, magshift, ... }: {
        nixosConfigurations.myhostname = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            ./configuration.nix

            # 1. Import the module
            magshift.nixosModules.default

            # 2. Add Overlay (Required)
            ({ pkgs, ... }: {
              nixpkgs.overlays = [
                (final: prev: {
                  magshift = magshift.packages.${prev.stdenv.hostPlatform.system}.default;
                })
              ];
            })
          ];
        };
      };
    }

### 2. Enable in `configuration.nix`

    { config, pkgs, ... }:

    {
      services.magshift.enable = true;

      # Optional, defaults shown:
      # services.magshift.hotkey = "meta";     # meta | alt | ctrl | caps | menu (see Usage)
      # services.magshift.pause = false;       # also correct on a single Pause press
      # services.magshift.autoNumlock = true;  # force NumLock ON at start
    }

The module installs the package, loads `uinput`, adds the udev rules and runs MagShift as a system service.

> **Note:** With the udev-based approach, users **do not need** to be added to `input` or `uinput` groups.
> Permissions are granted dynamically to the active graphical session user.

### 3. Update MagShift

    cd /etc/nixos
    sudo nix flake update magshift
    sudo nixos-rebuild switch

If you track your NixOS config in git, commit the updated `flake.lock` before rebuilding.

---

## 🐧 Installation (Ubuntu / Fedora / Arch)

For non-NixOS systems, use the provided installer script:

### Quick Install

    # Download the latest release
    wget https://github.com/OleksandrCEO/MagShift/archive/refs/heads/master.zip
    unzip master.zip
    cd MagShift-master

    # Run installer (requires root)
    sudo ./install.sh

The installer will:
1. Print your system details (distro, session type, default keyboard layout) for troubleshooting
2. Install `python3-evdev` via your package manager (apt/dnf/pacman) if it is missing. The exact command is shown,
   and package lists are not refreshed: if it fails, run `sudo apt update` (or your distro's equivalent) yourself
3. Copy `main.py` to `/usr/local/bin/magshift`
4. Create udev rules for dynamic device permissions and apply them
5. Check that your user can access `/dev/uinput` and every keyboard

Then start it with `magshift` (or set up [autostart](#-autostart-linux)).

> **X11:** on the first install the installer asks for a reboot instead of applying keyboard access live. X.Org
> re-creates every keyboard that gets a udev event, with the system default layout, so applying it live would reset
> a layout set via `setxkbmap`. Wayland sessions get access immediately.

### Update

Download and run the installer again:

    wget https://github.com/OleksandrCEO/MagShift/archive/refs/heads/master.zip
    unzip -o master.zip
    cd MagShift-master
    sudo ./install.sh

---

## 🍎 Installation (macOS)

macOS 12 or newer, Intel or Apple Silicon. No `sudo` needed - everything is installed under your home directory.

### Quick Install

    git clone https://github.com/OleksandrCEO/MagShift.git
    cd MagShift
    ./install-macos.sh

The installer will:
1. Create a private virtualenv in `~/.local/share/magshift/venv` and install `pyobjc-framework-Quartz`
2. Copy `main.py` next to it and add a `magshift` wrapper to `~/.local/bin`
3. Register a LaunchAgent (`com.magwer.magshift`) that starts MagShift with your session, so no extra autostart
   setup is needed

### Grant Permissions (required)

macOS will not let any process read or inject keystrokes until you allow it. Open
**System Settings → Privacy & Security** and add the Python binary the installer prints to **both** lists:

1. **Input Monitoring** - lets MagShift see what you type
2. **Accessibility** - lets MagShift type the correction back

With a standalone Python that is the venv binary:

    ~/.local/share/magshift/venv/bin/python3

With a framework Python (python.org or Homebrew) the venv binary re-launches `Python.app`, and that is what macOS
checks, e.g.:

    /Library/Frameworks/Python.framework/Versions/3.x/Resources/Python.app

In that case the grant covers every script run by that Python.

> In the file picker press `Cmd+Shift+G` and paste the path. The installer prints the exact absolute path at the
> end of its run.

Then restart the agent:

    launchctl kickstart -k gui/$UID/com.magwer.magshift

### Verify

    tail -f ~/.local/share/magshift/magshift.log

Type a word in the wrong layout, tap **Shift** twice, and it should be retyped correctly.

### Update / Uninstall

    git pull && ./install-macos.sh      # update
    ./install-macos.sh --uninstall      # remove agent, venv and wrapper

### macOS differences

| Option | Behaviour on macOS |
|---|---|
| `-k / --hotkey` | Ignored. Layouts are switched directly through `TISSelectInputSource`, so no hotkey has to be configured or emulated. |
| `-p / --pause` | Has no effect: Mac keyboards have no Pause key. |
| `-d / --device` | Ignored. The Quartz event tap is system-wide; there is no per-device capture. |
| `-n / --numlock`, `--auto-numlock` | Ignored. Mac keyboards have no NumLock. |
| `--list` | Lists the enabled keyboard layouts instead of input devices. |

MagShift switches to the layout you used before the current one, so a second double-Shift undoes the correction.
When no previous layout is known yet it takes the next one in `magshift --list` order.

---

## 🚀 Usage

    magshift                 # start with defaults (Linux: emulates Meta+Space to switch)
    magshift -k alt          # your desktop switches layouts with Alt+Shift
    magshift -k menu -p      # switch with the Menu key, and also correct on a single Pause press
    magshift --list          # Linux: input devices, macOS: keyboard layouts
    magshift --verbose       # show what is being corrected

| Option | Description | Platform |
|---|---|---|
| `-k, --hotkey STYLE` | Which hotkey your desktop uses to switch layouts, so MagShift can emulate it. `meta` (Meta+Space, default), `alt` (Alt+Shift), `ctrl` (Ctrl+Shift), `caps` (CapsLock), `menu` (Menu key) | Linux |
| `-p, --pause` | Also correct on a single `Pause` press (Punto Switcher style). Double Shift keeps working. | Linux |
| `-d, --device PATH` | Read from a specific `/dev/input/event*` device instead of auto-detecting the keyboard | Linux |
| `--list` | List input devices (Linux) or enabled keyboard layouts (macOS) and exit | both |
| `-n, --numlock` | Force NumLock ON and exit | Linux |
| `--auto-numlock` | Force NumLock ON at start, then keep running (used by the NixOS service) | Linux |
| `-v, --verbose` | Log every correction | both |

**The hotkey style must match your desktop settings.** MagShift does not switch the layout itself on Linux: it
presses the same hotkey you would. Check System Settings → Keyboard → Layouts if corrections do nothing.

**X11:** MagShift types through the XTEST extension of your X session, so start it from inside that session (desktop
autostart, i3 `exec`, `.xinitrc`). Started without access to the display, it falls back to a virtual uinput keyboard,
and X.Org gives new keyboards the system default layout (`localectl status`), not one set via `setxkbmap`.

---

## 🤖 Autostart (Linux)

On macOS the installer already registers a LaunchAgent. On NixOS the module runs a system service. For other Linux
distros pick one of the two options below.

### KDE Plasma

Since this tool relies on the graphical session (Wayland/X11), the most reliable way to start it is via KDE settings.

1. Open **System Settings** (Системні параметри) -> **Autostart** (Автозапуск).
2. Click **+ Add New** (+ Додати нове) -> **Application...** (Програма...).
   * *Do not select "Login Script".*
3. Type `magshift` in the search bar and select it.
4. *(Optional)* To pass options, click on the added entry, then **Properties**, and change the command, e.g.
   `magshift -k alt` or `magshift -k menu -p` (see [Usage](#-usage)).
5. Click Apply (Гаразд).

That's it! MagShift will now start automatically with your user session.

### Systemd User Service

Works on any distro with systemd (Ubuntu, Fedora, Arch, ...).

1. Create the service file:

       mkdir -p ~/.config/systemd/user
       nano ~/.config/systemd/user/magshift.service

   Paste the following, adding your options after the executable path if needed (e.g. `magshift -k alt`):

       [Unit]
       Description=MagShift Keyboard Layout Switcher
       After=graphical-session.target

       [Service]
       ExecStart=/usr/local/bin/magshift
       Restart=always
       RestartSec=5

       [Install]
       WantedBy=default.target

2. Enable and start it:

       systemctl --user daemon-reload
       systemctl --user enable --now magshift.service

3. Check status and logs:

       systemctl --user status magshift.service
       journalctl --user -u magshift -f

---

## 🛠️ Manual Usage (Development)

    # Linux with Nix: enter the development shell (Python + evdev + evtest)
    nix develop

    # macOS: use the interpreter the installer created
    alias python3=~/.local/share/magshift/venv/bin/python3

    # Run with verbose logging to see key events
    python3 main.py --verbose

    # Run the platform-neutral self-check (works on Linux and macOS, no hardware needed)
    python3 test_magshift.py

`main.py` is a single file with three layers: platform-neutral key codes and the input buffer, a backend per platform
(`LinuxBackend` on evdev/uinput, `MacBackend` on Quartz + Carbon TIS), and the `MagShift` state machine that never
touches a platform API directly.

## 🔗 Related

* **Clipboard version:** the old, less secure version with a clipboard dependency and extra features (like handling
  selected text) lives in a separate repo: [SkySwitcher](https://github.com/OleksandrCEO/SkySwitcher).

## 📜 License

MIT License. Feel free to use and modify.
