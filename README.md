# MagShift 🪄

[![NixOS](https://img.shields.io/badge/NixOS-25.11+-5277C3?style=flat&logo=nixos&logoColor=white)](#%EF%B8%8F-nixos-installation-flake)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

**MagShift** - Advanced Keyboard Layout Switcher with Instant Correction Engine for Linux (Wayland & X11) and macOS. It fixes what you just typed without making you retype it.

Designed with **NixOS Flakes** in mind for reproducible and secure deployment. 

Also supports other Linux distros via a simple installer script. For example: 

[![Ubuntu](https://img.shields.io/badge/Ubuntu-Supported-E95420?style=flat&logo=ubuntu&logoColor=white)](#-installation-ubuntu--fedora--arch)
[![Fedora](https://img.shields.io/badge/Fedora-Supported-51A2DA?style=flat&logo=fedora&logoColor=white)](#-installation-ubuntu--fedora--arch)
[![Arch](https://img.shields.io/badge/Arch-Supported-1793D1?style=flat&logo=archlinux&logoColor=white)](#-installation-ubuntu--fedora--arch)

And on macOS:

[![macOS](https://img.shields.io/badge/macOS-12+-000000?style=flat&logo=apple&logoColor=white)](#-installation-macos)

## ✨ Features

* **⚡ Double Right Shift:** Tap `Right Shift` twice to switch layout (e.g., English ↔ Ukrainian).
* **🖋️ Auto-Correction:** It automatically corrects the **last typed phrase** when you switch.
* **🔒 Secure:** Runs with dynamic permissions (via Udev ACLs), no manual group configuration required.
* **❄️ Pure Nix:** Zero global dependencies. Builds cleanly from the Nix Store.
* **🍎 macOS Native:** Uses a Quartz event tap and the Text Input Source API - no hotkey emulation, no extra daemons.



## 📋 Clipboard Version

Old unsecure version with clipboard dependency and extra features (like handling selected text) available in extra branch: [SkySwitcher](https://github.com/OleksandrCEO/SkySwitcher)


---

## ❄️ NixOS Installation (Flake)

Since this project exports a NixOS module, installation is clean, but requires an overlay to make the package available to the system.

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
      # Enable MagShift
      services.magshift.enable = true;
    }

> **Note:** With the new udev-based approach, users **do not need** to be added to `input` or `uinput` groups. Permissions are granted dynamically to the active graphical session user.

### 3. Update MagShift (when script updates but Nix flake hasn't)

If you've made local changes or want to pull the latest version:

    cd /etc/nixos
    sudo nix flake update magshift
    sudo nixos-rebuild switch

If you track your NixOS config in git:

    cd /etc/nixos
    sudo git add .
    sudo git commit -m "Update MagShift to latest version"
    sudo nixos-rebuild switch

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
1. Install `python3-evdev` via your package manager (apt/dnf/pacman)
2. Copy `main.py` to `/usr/local/bin/magshift`
3. Create udev rules for dynamic device permissions
4. Reload udev to apply changes

### Update

To update to the latest version, simply download and run the installer again:

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
3. Register a LaunchAgent (`com.magwer.magshift`) that starts MagShift with your session

### Grant Permissions (required)

macOS will not let any process read or inject keystrokes until you allow it. Open
**System Settings → Privacy & Security** and add the Python binary the installer prints to **both** lists.
With a standalone Python that is the venv binary:

    ~/.local/share/magshift/venv/bin/python3

With a framework Python (python.org or Homebrew) the venv binary re-launches `Python.app`, and that is
what macOS checks, e.g.:

    /Library/Frameworks/Python.framework/Versions/3.x/Resources/Python.app

In that case the grant covers every script run by that Python.

1. **Input Monitoring** - lets MagShift see what you type
2. **Accessibility** - lets MagShift type the correction back

> In the file picker press `Cmd+Shift+G` and paste the path. The installer prints the exact
> absolute path at the end of its run.

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
| `-d / --device` | Ignored. The Quartz event tap is system-wide; there is no per-device capture. |
| `-n / --numlock`, `--auto-numlock` | Ignored. Mac keyboards have no NumLock. |
| `--list` | Lists the enabled keyboard layouts instead of input devices. |

MagShift switches to the layout you used before the current one, so a second double-Shift undoes the
correction. When no previous layout is known yet it takes the next one in `magshift --list` order.

---

## 🤖 Autostart (KDE Plasma)

Since this tool relies on the graphical session (Wayland/X11), the most reliable way to start it is via KDE settings.

1.  Open **System Settings** (Системні параметри) -> **Autostart** (Автозапуск).
2.  Click **+ Add New** (+ Додати нове) -> **Application...** (Програма...).
    * *Do not select "Login Script".*
3.  Type `magshift` in the search bar and select it.
4.  *(Optional)* If you want to use a different layout switching hotkey, click on the added entry, then click **Properties** and modify the command:
    * For Alt+Shift: `magshift -k alt`
    * For Ctrl+Shift: `magshift -k ctrl`
    * For CapsLock: `magshift -k caps`
    * For the Menu key: `magshift -k menu`
    * Default is Meta+Space (`-k meta`)
    * To also correct on a single `Pause` press (Punto Switcher style): add `-p`
5.  Click Apply (Гаразд).

That's it! MagShift will now start automatically with your user session.

## Autostart (as a Systemd User Service)

To ensure **MagShift** runs automatically and remains stable on systems like Ubuntu, follow these steps to configure it as a `systemd` user service.

## 1. Create the Service File
Create the service configuration file in your user directory:

    mkdir -p ~/.config/systemd/user
    nano ~/.config/systemd/user/magshift.service

Paste the following content into the file:

    [Unit]
    Description=MagShift Keyboard Layout Switcher
    After=graphical-session.target

    [Service]
    # Ensure the path points to your installed executable
    ExecStart=/usr/local/bin/magshift
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=default.target

## 2. Enable and Start the Service
Apply the changes and activate the service:

    # Reload the systemd user manager configuration
    systemctl --user daemon-reload

    # Enable the service to start automatically on login
    systemctl --user enable magshift.service

    # Start the service immediately
    systemctl --user start magshift.service

## 3. Verify Status and Logs
To check if the service is running correctly, use:

    systemctl --user status magshift.service

To view real-time logs for debugging purposes:

    journalctl --user -u magshift -f

---

## 🛠️ Manual Usage (Development)

If you want to run it manually for debugging or development:

    # Enter the development shell
    nix develop

    # Run with verbose logging to see key events
    python3 main.py --verbose

    # List available input devices (keyboards)
    python3 main.py --list

    # Run the platform-neutral self-check (works on Linux and macOS)
    python3 test_magshift.py

    # Use a different layout switching hotkey (Linux only)
    python3 main.py -k alt    # Alt+Shift (default in many Linux DEs)
    python3 main.py -k meta   # Meta+Space (default, KDE-style)
    python3 main.py -k ctrl   # Ctrl+Shift
    python3 main.py -k caps   # CapsLock
    python3 main.py -k menu   # Menu key

    # Also correct on a single Pause press, double Shift keeps working (Linux only)
    python3 main.py -p

Available hotkey styles (Linux only):
- `alt` - Left Alt + Left Shift (common on GNOME/XFCE)
- `meta` - Left Meta (Windows key) + Space (default, KDE standard)
- `ctrl` - Left Ctrl + Left Shift
- `caps` - CapsLock only
- `menu` - Menu key only (the context-menu key next to Right Ctrl)

## 📜 License

MIT License. Feel free to use and modify.
