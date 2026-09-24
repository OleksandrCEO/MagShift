#!/bin/bash
# ==============================================================================
# MagShift Installer
# Description: Installs MagShift utility, dependencies, and configures system permissions.
# Target Systems: Ubuntu, Debian, Fedora, Arch Linux (Systemd-based)
# ==============================================================================

# 1. Configuration & Safety
set -Eeuo pipefail
IFS=$'\n\t'

# Constants
INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="magshift"
SOURCE_FILE="main.py"
# Using 60- prefix to ensure rules run before systemd-logind (70-uaccess)
UDEV_RULE_FILE="/etc/udev/rules.d/60-magshift.rules"
MODULE_LOAD_FILE="/etc/modules-load.d/magshift.conf"
TARGET_USER="${SUDO_USER:-}"

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

# Show every command that changes the system before running it
run() { local IFS=' '; log_info "\$ $*"; "$@" || return; }

# set -e alone stops on the first failing command without saying which one
trap 'log_error "Installer stopped at line $LINENO (exit code $?): $(sed -n "${LINENO}p" "$0")"' ERR

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

# Printed first, so any failure below has the context on screen
# shellcheck source=/dev/null
os_name=$( (. /etc/os-release && echo "$PRETTY_NAME") 2>/dev/null || uname -s)
x_server=$(pgrep -x 'Xorg|X' >/dev/null && echo "X.Org running" || echo "no X.Org")
xkb_default=$(localectl status 2>/dev/null | sed -n 's/^ *X11 \(Layout\|Variant\|Options\): */\1=/p' \
    | paste -sd' ' || true)
log_info "System:   $os_name, kernel $(uname -r)"
log_info "Python:   $(python3 --version 2>&1 || echo 'python3 not found')"
log_info "User:     ${TARGET_USER:-unknown (not run via sudo)}"
sessions=$(loginctl list-sessions --no-legend 2>/dev/null | awk -v u="$TARGET_USER" '$3 == u {print $1}' || true)
for session in $sessions; do
    session_info=$(loginctl show-session "$session" -p Type -p Desktop -p State 2>/dev/null | paste -sd' ' || true)
    log_info "Session:  $session_info"
done
log_info "Display:  $x_server; default layout for new keyboards: ${xkb_default:-not set}"

# ==============================================================================
# 3. Dependency Installation
# ==============================================================================
log_info "Checking dependencies..."

if python3 -c 'import evdev' 2>/dev/null; then
    log_success "python3-evdev is already installed"
else
    if command -v apt-get &> /dev/null; then
        install_cmd=(apt-get install -y python3-evdev)
        refresh_cmd="sudo apt update"
    elif command -v dnf &> /dev/null; then
        install_cmd=(dnf install -y python3-evdev)
        refresh_cmd="sudo dnf makecache"
    elif command -v pacman &> /dev/null; then
        install_cmd=(pacman -S --needed --noconfirm python-evdev)
        refresh_cmd="sudo pacman -Syu"
    else
        fail "Unknown package manager. Install the evdev module for python3 (usually 'python3-evdev') and re-run."
    fi

    # No implicit package list refresh: that is the user's call, not the installer's
    run "${install_cmd[@]}" \
        || fail "Could not install python3-evdev. If package lists are outdated, run '$refresh_cmd' and re-run."
    python3 -c 'import evdev' || fail "python3-evdev was installed but python3 cannot import it."
    log_success "python3-evdev installed"
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
UDEV_RULES=$(cat <<EOF
# MagShift udev rules
# Grants R/W access to input devices ONLY to the user on the active physical seat.

# 1. Virtual input device (uinput) - allows creating virtual keyboard
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0", OPTIONS+="static_node=uinput"

# 2. Physical keyboards - allows reading key events
# We explicitly import input_id to ensure properties are populated
SUBSYSTEM=="input", KERNEL=="event*", IMPORT{builtin}="input_id", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0"
EOF
)

# Rewriting unchanged rules would re-trigger every keyboard on each update (see step 7)
if [ -f "$UDEV_RULE_FILE" ] && [ "$(cat "$UDEV_RULE_FILE")" = "$UDEV_RULES" ]; then
    rules_changed=false
    log_success "Rules at $UDEV_RULE_FILE are up to date"
else
    printf '%s\n' "$UDEV_RULES" > "$UDEV_RULE_FILE"
    rules_changed=true
    log_success "Created rules at $UDEV_RULE_FILE"
fi

# ==============================================================================
# 7. Apply Changes
# ==============================================================================
log_info "Applying changes..."

keyboards_deferred=false
if udevadm control --reload-rules; then
    # uinput is not an input device, so re-triggering it is invisible to X11 and Wayland
    run udevadm trigger --action=change --subsystem-match=misc --sysname-match=uinput
    if [ "$rules_changed" = true ]; then
        # X.Org re-creates every keyboard that gets a udev event, with the system default layout:
        # a layout set via setxkbmap would be lost. Wayland compositors ignore these events.
        if [ "$x_server" = "X.Org running" ]; then
            keyboards_deferred=true
        else
            run udevadm trigger --action=change --subsystem-match=input --sysname-match='event*' \
                --property-match=ID_INPUT_KEYBOARD=1
        fi
    fi
    udevadm settle || true
    log_success "Udev rules reloaded"
else
    log_warn "Could not reload udev rules automatically. A reboot might be required."
fi

# ==============================================================================
# 8. Verify Access
# ==============================================================================
log_info "Checking device access for ${TARGET_USER:-the desktop user}..."

access_ok=false
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
    log_warn "Skipped: run the installer via sudo from your desktop user to check access."
else
    uinput_ok=false
    if sudo -u "$TARGET_USER" test -w /dev/uinput; then
        uinput_ok=true
        log_success "/dev/uinput: writable"
    else
        log_warn "/dev/uinput: not writable"
    fi

    keyboards_ok=false
    for dev in /dev/input/event*; do
        props=$(udevadm info -q property -n "$dev" 2>/dev/null) || continue
        grep -qx 'ID_INPUT_KEYBOARD=1' <<< "$props" || continue
        name=$(cat "/sys/class/input/$(basename "$dev")/device/name" 2>/dev/null || echo "?")
        if sudo -u "$TARGET_USER" test -r "$dev"; then
            keyboards_ok=true
            log_success "$dev: readable   ($name)"
        else
            log_warn "$dev: no access  ($name)"
        fi
    done

    if [ "$uinput_ok" = true ] && [ "$keyboards_ok" = true ]; then
        access_ok=true
    fi
fi

echo ""
echo "=========================================="
echo -e "${GREEN}Installation Complete!${NC}"
echo "=========================================="
if [ "$keyboards_deferred" = true ]; then
    log_warn "Reboot to finish: keyboard access is applied on boot. Applying it now would reset the keyboard"
    log_warn "layout of the running X11 session to the system default (e.g. one set via setxkbmap)."
elif [ "$access_ok" = false ] && [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ]; then
    log_warn "Some devices are not accessible yet. Reboot, then run the installer again to re-check."
fi
echo "Usage:"
echo "  magshift            # Start MagShift"
echo "  magshift --verbose  # Start with debug logging"
echo "  magshift --list     # List input devices"
echo "  magshift -k alt     # Your desktop switches layouts with Alt+Shift (also: meta, ctrl, caps, menu)"
echo "  magshift -p         # Also correct on a single Pause press"
