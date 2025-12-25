# SkySwitcher 🌌

A minimalist keyboard layout switcher for Linux (Wayland/NixOS).
It detects a double press of `Right Shift`, corrects the last typed word, and switches its layout (e.g., English <-> Ukrainian).

Works by intercepting raw input events (`evdev`) and simulating keystrokes (`uinput`).

## 📋 Prerequisites

### NixOS Configuration
To allow Python to read input and simulate keys, you need to enable `uinput` and grant permissions.

Add this to your `configuration.nix`:

    { config, pkgs, userSettings, ... }: {
      
      # Enable uinput module
      hardware.uinput.enable = true;
    
      # Add user to groups (replace 'username' with your actual user)
      users.users.username.extraGroups = [ "input" "uinput" ];
    
      # Ensure wl-clipboard is installed
      environment.systemPackages = with pkgs; [ wl-clipboard ];
    }

> **Important:** Run `sudo nixos-rebuild switch` and **REBOOT** your system after applying these changes.

## 🚀 Installation & Usage

1. Clone the repository:

       mkdir -p ~/dev/system
       cd ~/dev/system
       git clone https://github.com/OleksandrCEO/SkySwitcher.git
       cd SkySwitcher

2. Enter the environment and run:

       nix-shell --run "python3 main.py --verbose"

### Arguments
- `--verbose` (`-v`): Show logs (detected keys, conversions).
- `--device` (`-d`): Manually specify input device path (if auto-detection fails).
- `--list`: List all detected input devices and exit.

## 🤖 Auto-start (Systemd)

To run SkySwitcher in the background automatically:

1. Create `nano ~/.config/systemd/user/skyswitcher.service`:

       [Unit]
       Description=SkySwitcher Layout Corrector
       After=graphical-session.target
       
       [Service]
       # Adjust the path if you cloned it elsewhere
       WorkingDirectory=%h/dev/system/SkySwitcher
       ExecStart=/usr/bin/env nix-shell shell.nix --run "python3 main.py"
       Restart=always
       RestartSec=5
       
       [Install]
       WantedBy=default.target

2. Enable and start:

       systemctl --user enable --now skyswitcher

3. Check status:

       systemctl --user status skyswitcher