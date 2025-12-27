# SkySwitcher 🌌

![NixOS](https://img.shields.io/badge/NixOS-25.11+-5277C3?style=flat&logo=nixos&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

**SkySwitcher** is a minimalist, context-aware keyboard layout switcher for Linux (Wayland & X11). It fixes what you just typed without making you retype it.

Designed with **NixOS Flakes** in mind for reproducible and secure deployment.

## ✨ Features

* **⚡ Double Right Shift:** Tap `Right Shift` twice to switch layout (e.g., English ↔ Ukrainian).
* **🖋️ Auto-Correction:** It automatically corrects the **last typed phrase** when you switch.
* **🔒 Secure:** Runs with dynamic permissions (via Udev ACLs), no manual group configuration required.
* **❄️ Pure Nix:** Zero global dependencies. Builds cleanly from the Nix Store.


## 📝 Clipboard Version

Old version with clipboard dependency and extra features (like handling selected text) available in extra branch: [feature-clipboard](https://github.com/OleksandrCEO/SkySwitcher/tree/feature-clipboard)


## 🎮 Controls

| Action | Shortcut | Description |
| :--- | :--- | :--- |
| **Fix Last Word** | `Right Shift` (x2) | Selects last word, translates it, replaces text, and switches system layout. |
| **Fix Selection** | `R-Ctrl` + `R-Shift` | Converts the currently selected text (clipboard-based). |


---

## ❄️ NixOS Installation (Flake)

Since this project exports a NixOS module, installation is clean, but requires an overlay to make the package available to the system.

### 1. Add to `flake.nix`

Add the input, import the module, and **apply the overlay** in your system configuration:

    {
      inputs = {
        nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
        
        # Add SkySwitcher input
        skyswitcher.url = "github:OleksandrCEO/SkySwitcher";
        # skyswitcher.inputs.nixpkgs.follows = "nixpkgs"; 
      };

      outputs = { self, nixpkgs, skyswitcher, ... }: {
        nixosConfigurations.myhostname = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            ./configuration.nix
            
            # 1. Import the module
            skyswitcher.nixosModules.default

            # 2. Add Overlay (Required)
            ({ pkgs, ... }: {
              nixpkgs.overlays = [
                (final: prev: {
                  skyswitcher = skyswitcher.packages.${prev.stdenv.hostPlatform.system}.default;
                })
              ];
            })
          ];
        };
      };
    }

---

## 🤖 Autostart (KDE Plasma)

Since this tool relies on the graphical session (Wayland/X11), the most reliable way to start it is via KDE settings.

1.  Open **System Settings** (Системні параметри) -> **Autostart** (Автозапуск).
2.  Click **+ Add New** (+ Додати нове) -> **Application...** (Програма...).
    * *Do not select "Login Script".*
3.  Type `skyswitcher` in the search bar and select it.
4.  *(Optional)* If you want to use a different layout switching hotkey, click on the added entry, then click **Properties** and modify the command:
    * For Alt+Shift: `skyswitcher -k alt`
    * For Ctrl+Shift: `skyswitcher -k ctrl`
    * For CapsLock: `skyswitcher -k caps`
    * Default is Meta+Space (`-k meta`)
5.  Click Apply (Гаразд).

That's it! SkySwitcher will now start automatically with your user session.

---

## 🛠️ Manual Usage (Development)

If you want to run it manually for debugging or development:

    # Enter the development shell
    nix develop

    # Run with verbose logging to see key events
    python3 main.py --verbose

    # List available input devices (keyboards)
    python3 main.py --list

    # Use a different layout switching hotkey
    python3 main.py -k alt    # Alt+Shift (default in many Linux DEs)
    python3 main.py -k meta   # Meta+Space (default, KDE-style)
    python3 main.py -k ctrl   # Ctrl+Shift
    python3 main.py -k caps   # CapsLock

Available hotkey styles:
- `alt` - Left Alt + Left Shift (common on GNOME/XFCE)
- `meta` - Left Meta (Windows key) + Space (default, KDE standard)
- `ctrl` - Left Ctrl + Left Shift
- `caps` - CapsLock only

## 📜 License

MIT License. Feel free to use and modify.