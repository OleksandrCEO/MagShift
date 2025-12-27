{ config, lib, pkgs, ... }:

let
  cfg = config.services.magshift;
in
{
  options.services.magshift = {
    enable = lib.mkEnableOption "MagShift package and dynamic permissions";
  };

  config = lib.mkIf cfg.enable {
    # 1. Install the package to system path so it can be found by KDE Autostart
    environment.systemPackages = [ pkgs.magshift ];

    # 2. Enable uinput kernel module to ensure /dev/uinput device is created
    hardware.uinput.enable = true;

    # 3. Configure dynamic permissions via Udev rules.
    # Instead of adding the user to static 'input' or 'uinput' groups (which is a security risk),
    # we use the 'uaccess' tag. This grants read/write access to input devices
    # ONLY to the user currently logged into the active graphical session (via systemd-logind).
    services.udev.extraRules = ''
      # Grant access to create virtual input devices (uinput) to the active user
      KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"

      # Grant access to read physical keyboard events to the active user
      SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess"
    '';
  };
}