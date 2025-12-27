#!/bin/bash
# MagShift installer for standard Linux distros (Ubuntu/Fedora/Arch)
# This script installs MagShift to /usr/local/bin and configures udev rules

set -e

INSTALL_DIR="/usr/local/bin"
RULE_FILE="/etc/udev/rules.d/99-magshift.rules"
SCRIPT_NAME="magshift"

echo "=== MagShift Installer ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Detect package manager and install python3-evdev
echo "[1/4] Installing python3-evdev dependency..."
if command -v apt &> /dev/null; then
    apt update
    apt install -y python3-evdev
    echo "✓ Installed via apt"
elif command -v dnf &> /dev/null; then
    dnf install -y python3-evdev
    echo "✓ Installed via dnf"
elif command -v pacman &> /dev/null; then
    pacman -S --noconfirm python-evdev
    echo "✓ Installed via pacman"
else
    echo "Warning: Unknown package manager. Please install python3-evdev manually."
fi

# Copy main.py to /usr/local/bin/magshift
echo ""
echo "[2/4] Installing MagShift to $INSTALL_DIR/$SCRIPT_NAME..."
cp main.py "$INSTALL_DIR/$SCRIPT_NAME"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"
echo "✓ Installed"

# Create udev rules for dynamic permissions
echo ""
echo "[3/4] Installing udev rules to $RULE_FILE..."
cat > "$RULE_FILE" <<EOF
# MagShift udev rules - Grant access to input devices for active user
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess"
EOF
echo "✓ Created udev rules"

# Reload udev
echo ""
echo "[4/4] Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger
echo "✓ Reloaded"

echo ""
echo "=== Installation Complete! ==="
echo ""
echo "Next steps:"
echo "1. Reboot or log out/in for udev rules to take effect"
echo "2. Run 'magshift' to start the program"
echo "3. To autostart on login, add 'magshift' to your DE's autostart"
echo ""
echo "Options:"
echo "  magshift           # Start with default Meta+Space hotkey"
echo "  magshift -k alt    # Use Alt+Shift instead"
echo "  magshift --list    # List available keyboards"
echo ""