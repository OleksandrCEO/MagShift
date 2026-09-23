#!/bin/bash
# ==============================================================================
# MagShift Installer for macOS
# Description: Installs MagShift into a private virtualenv and registers a
#              LaunchAgent that starts it with the user session.
# Target Systems: macOS 12+ (Intel and Apple Silicon)
# Note: no sudo required - everything lives under the user's home directory.
# ==============================================================================

set -euo pipefail
IFS=$'\n\t'

# Constants
PREFIX="${MAGSHIFT_PREFIX:-$HOME/.local/share/magshift}"
BIN_DIR="$HOME/.local/bin"
LABEL="com.magwer.magshift"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SOURCE_FILE="main.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

fail() { log_error "$1"; exit 1; }

# ==============================================================================
# Uninstall
# ==============================================================================
if [ "${1:-}" = "--uninstall" ]; then
    log_info "Removing MagShift..."
    launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
    rm -f "$PLIST" "$BIN_DIR/magshift"
    rm -rf "$PREFIX"
    log_success "MagShift removed. Revoke its permissions manually in System Settings if you wish."
    exit 0
fi

# ==============================================================================
# Pre-flight Checks
# ==============================================================================
[ "$(uname -s)" = "Darwin" ] || fail "This installer is for macOS. On Linux use ./install.sh"
[ -f "$SOURCE_FILE" ] || fail "Source file '$SOURCE_FILE' not found in current directory."
[ "$EUID" -ne 0 ] || fail "Do NOT run this installer as root - permissions must belong to your user."
command -v python3 &> /dev/null || fail "python3 not found. Install it via Xcode Command Line Tools or Homebrew."

echo "=========================================="
echo "   MagShift Installer (macOS)"
echo "=========================================="

# ==============================================================================
# Virtualenv & Dependencies
# ==============================================================================
log_info "Creating virtualenv at $PREFIX/venv ..."

mkdir -p "$PREFIX" "$BIN_DIR"

# --copies gives the venv its own python binary. On a standalone Python that
# binary is what macOS grants permissions to; on a framework build (python.org,
# Homebrew) it re-execs Python.app, so the grant has to go there instead.
python3 -m venv --copies "$PREFIX/venv"

VENV_PY="$PREFIX/venv/bin/python3"
cp "$SOURCE_FILE" "$PREFIX/magshift.py"
# The binary that actually runs - and the one TCC checks.
TCC_BIN="$(cd "$PREFIX" && "$VENV_PY" -c 'import magshift; print(magshift._running_binary())')"
[ -x "$TCC_BIN" ] || TCC_BIN="$VENV_PY"
"$VENV_PY" -m pip install --upgrade --quiet pip
"$VENV_PY" -m pip install --quiet "pyobjc-framework-Quartz>=9.0"

log_success "Dependencies installed"

# ==============================================================================
# Installing Executable
# ==============================================================================
log_info "Installing MagShift..."

cat > "$BIN_DIR/magshift" <<WRAPPER
#!/bin/bash
exec "$VENV_PY" "$PREFIX/magshift.py" "\$@"
WRAPPER
chmod +x "$BIN_DIR/magshift"

log_success "Installed to $PREFIX (CLI wrapper: $BIN_DIR/magshift)"

# ==============================================================================
# LaunchAgent
# ==============================================================================
log_info "Registering LaunchAgent..."

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PY</string>
        <string>$PREFIX/magshift.py</string>
        <string>--verbose</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>$PREFIX/magshift.log</string>
    <key>StandardErrorPath</key>
    <string>$PREFIX/magshift.err.log</string>
</dict>
</plist>
PLISTEOF

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
# bootout returns before the old agent is gone; bootstrap then fails with EIO.
for _ in $(seq 50); do
    launchctl print "gui/$UID/$LABEL" &>/dev/null || break
    sleep 0.1
done
launchctl bootstrap "gui/$UID" "$PLIST"
launchctl enable "gui/$UID/$LABEL"

log_success "LaunchAgent registered ($LABEL)"

# ==============================================================================
# Done
# ==============================================================================
echo ""
echo "=========================================="
echo -e "${GREEN}Installation Complete!${NC}"
echo "=========================================="
echo ""
log_warn "One manual step is required: macOS permissions."
echo ""
echo "  Open System Settings -> Privacy & Security and add this binary to BOTH lists:"
echo ""
echo -e "      ${BLUE}$TCC_BIN${NC}"
echo ""
echo "    1. Input Monitoring   (to read your keystrokes)"
echo "    2. Accessibility      (to type the correction back)"
echo ""
echo "  In the file picker press Cmd+Shift+G and paste the path above."
if [ "$TCC_BIN" != "$VENV_PY" ]; then
    echo "  (Your Python is a framework build: the grant applies to every script it runs.)"
fi
echo "  Then restart the agent:"
echo ""
echo "      launchctl kickstart -k gui/$UID/$LABEL"
echo ""
echo "Usage:"
echo "  magshift --list             # List keyboard layouts"
echo "  magshift --verbose          # Run in the foreground with logs"
echo "  tail -f $PREFIX/magshift.log"
echo "  ./install-macos.sh --uninstall"
echo ""
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    log_warn "$BIN_DIR is not in your PATH - add it to use the 'magshift' command."
fi
