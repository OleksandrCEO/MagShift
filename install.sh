#!/bin/bash
# ==============================================================================
# MagShift Installer
# Description: Installs MagShift utility, dependencies, and configures system permissions.
# Target Systems: Ubuntu, Debian, Fedora, Arch Linux (Systemd-based)
# ==============================================================================

# 1. Configuration & Safety
set -euo pipefail
IFS=$'\n\t'

# Constants
INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="magshift"
SOURCE_FILE="main.py"
# Using 60- prefix to ensure rules run before systemd-logind (70-uaccess)
UDEV_RULE_FILE="/etc/udev/rules.d/60-magshift.rules"
MODULE_LOAD_FILE="/etc/modules-load.d/magshift.conf"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

fail() { log_error "$1"; exit 1; }

# ==============================================================================
# 2. Pre-flight Checks
# ==============================================================================

# Check for root
if [ "$EUID" -ne 0 ]; then
    fail "This script must be run as root. Please use: sudo $0"
fi

# Check if source file exists
if [ ! -f "$SOURCE_FILE" ]; then
    fail "Source file '$SOURCE_FILE' not found in current directory."
fi

echo "=========================================="
echo "   MagShift Installer (Production)"
echo "=========================================="

# ==============================================================================
# 3. Dependency Installation
# ==============================================================================
log_info "Checking dependencies..."

if command -v apt-get &> /dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3-evdev python3-pip
    log_success "Dependencies installed via apt"
elif command -v dnf &> /dev/null; then
    dnf install -y -q python3-evdev
    log_success "Dependencies installed via dnf"
elif command -v pacman &> /dev/null; then
    pacman -Sy --noconfirm --quiet python-evdev
    log_success "Dependencies installed via pacman"
else
    log_warn "Could not detect package manager. Attempting pip install..."
    if command -v pip3 &> /dev/null; then
        pip3 install evdev
        log_success "Dependencies installed via pip"
    else
        fail "Python pip not found. Please install 'python3-evdev' manually."
    fi
fi

# ==============================================================================
# 4. Kernel Module Configuration (uinput)
# ==============================================================================
log_info "Configuring uinput kernel module..."

# Load immediately
if ! modprobe uinput; then
    fail "Failed to load 'uinput' kernel module."
fi

# Ensure persistence across reboots
if [ ! -f "$MODULE_LOAD_FILE" ]; then
    echo "uinput" > "$MODULE_LOAD_FILE"
    log_success "Added uinput to load on boot ($MODULE_LOAD_FILE)"
else
    log_success "uinput persistence already configured"
fi

# ==============================================================================
# 5. Installing Executable
# ==============================================================================
log_info "Installing MagShift binary..."

cp "$SOURCE_FILE" "$INSTALL_DIR/$SCRIPT_NAME"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

log_success "Installed to $INSTALL_DIR/$SCRIPT_NAME"

# ==============================================================================
# 6. Configuring Permissions (Udev Rules)
# ==============================================================================
log_info "Configuring udev permissions..."

# We use uaccess + seat tags for secure, dynamic user access without groups
cat > "$UDEV_RULE_FILE" <<EOF
# MagShift udev rules
# Grants R/W access to input devices ONLY to the user on the active physical seat.

# 1. Virtual input device (uinput) - allows creating virtual keyboard
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0", OPTIONS+="static_node=uinput"

# 2. Physical keyboards - allows reading key events
# We explicitly import input_id to ensure properties are populated
SUBSYSTEM=="input", KERNEL=="event*", IMPORT{builtin}="input_id", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0"
EOF

log_success "Created rules at $UDEV_RULE_FILE"

# ==============================================================================
# 7. Apply Changes
# ==============================================================================
log_info "Applying changes..."

if udevadm control --reload-rules && udevadm trigger; then
    log_success "Udev rules reloaded and triggered"
else
    log_warn "Could not reload udev rules automatically. A reboot might be required."
fi

echo ""
echo "=========================================="
echo -e "${GREEN}Installation Complete!${NC}"
echo "=========================================="
echo "Usage:"
echo "  magshift --start    # Start the daemon"
echo "  magshift --list     # List input devices"
echo ""
echo "Note: If permissions don't work immediately, please log out and log back in."