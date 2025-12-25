# SkySwitcher 🌌

A minimalist keyboard layout switcher for Linux (Wayland/NixOS).
It detects a double press of `Right Shift`, corrects the last typed word, and switches its layout (e.g., English <-> Ukrainian).

**Security Focus:** This installation method compiles the script into the immutable Nix Store, preventing unauthorized modifications by user-level malware.

## 📋 Prerequisites

To allow Python to read input and simulate keys, you need to enable `uinput` and grant permissions.

**1. Clone the repository to a permanent location:**
   
       mkdir -p ~/dev/system
       cd ~/dev/system
       git clone https://github.com/OleksandrCEO/SkySwitcher.git
       
   *(Note the path: `/home/YOUR_USER/dev/system/SkySwitcher/main.py`)*

**2. Configure NixOS:**

Add the following to your `/etc/nixos/configuration.nix`. 
Replace `YOUR_USER` with your actual username!

    { config, pkgs, ... }: {
      
      # --- Hardware & Permissions ---
      hardware.uinput.enable = true;
      users.users.YOUR_USER.extraGroups = [ "input" "uinput" ];
    
      # --- Install SkySwitcher Securely ---
      environment.systemPackages = with pkgs; [ 
        wl-clipboard  # Required dependency
        
        # This creates an immutable binary in /nix/store
        (writers.writePython3Bin "skyswitcher" {
          libraries = [ python3Packages.evdev ];
        } (builtins.readFile /home/YOUR_USER/dev/system/SkySwitcher/main.py))
      ];
    }

> **Important:** Run `sudo nixos-rebuild switch` and **REBOOT** your system to apply group permissions.

## 🚀 Usage

Since SkySwitcher is now a system package, you can run it from anywhere in the terminal:

       skyswitcher --verbose

### Arguments
- `--verbose` (`-v`): Show logs (detected keys, conversions).
- `--device` (`-d`): Manually specify input device path.
- `--list`: List all detected input devices and exit.

## 🤖 Auto-start (Systemd)

To run SkySwitcher automatically in the background:

1. Create `~/.config/systemd/user/skyswitcher.service`:

       [Unit]
       Description=SkySwitcher Layout Corrector
       After=graphical-session.target
       
       [Service]
       # Now we just call the system command
       ExecStart=skyswitcher
       Restart=always
       RestartSec=5
       
       [Install]
       WantedBy=default.target

2. Enable and start:

       systemctl --user enable --now skyswitcher

3. Check status:

       systemctl --user status skyswitcher