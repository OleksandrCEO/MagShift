# SkySwitcher 🌌

![NixOS](https://img.shields.io/badge/NixOS-25.11+-5277C3?style=flat&logo=nixos&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

**SkySwitcher** is a minimalist, context-aware keyboard layout switcher for Linux (Wayland & X11). It fixes what you just typed without making you retype it.

Designed with **NixOS Flakes** in mind for reproducible and secure deployment.

## ✨ Features

* **⚡ Double Right Shift:** Tap `Right Shift` twice to switch layout (e.g., English ↔ Ukrainian).
* **📝 Auto-Correction:** It automatically corrects the **last typed word** when you switch.
    * *Typed `ghbdsn`? -> Double Shift -> Becomes `привіт`.*
* **🎯 Selection Fix:** Hold `Right Ctrl` + press `Right Shift` to fix the currently **selected text**.
* **🔒 Secure:** Runs with standard user permissions (via `uinput` group), no `sudo` required after setup.
* **❄️ Pure Nix:** Zero global dependencies. Builds cleanly from the Nix Store.

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

### 2. Enable in `configuration.nix`

You simply need to enable the service and grant your user permission to use input devices.

    { config, pkgs, ... }:

    {
      # 1. Enable SkySwitcher
      services.skyswitcher.enable = true;

      # 2. Grant Permissions (CRITICAL)
      # The user needs to be in 'input' (to read keys) and 'uinput' (to write keys).
      users.users.your_username = {
        isNormalUser = true;
        extraGroups = [ "wheel" "input" "uinput" ]; 
      };
    }

> **Note:** After rebuilding (`sudo nixos-rebuild switch`), you might need to **reboot** or log out/in for group permissions (`uinput`) to take effect.

---

## 🛠️ Manual Usage (Development)

If you want to run it manually for debugging or development:

    # Enter the development shell
    nix develop

    # Run with verbose logging to see key events
    python3 main.py --verbose

    # List available input devices
    python3 main.py --list

## 📜 License

MIT License. Feel free to use and modify.