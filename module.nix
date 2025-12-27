# module.nix

{ config, lib, pkgs, ... }:

let
  cfg = config.services.magshift;
in
{
  options.services.magshift = {
    enable = lib.mkEnableOption "MagShift package and dynamic permissions";
  };

  config = lib.mkIf cfg.enable {
    # 1. Install the package to system path
    environment.systemPackages = [ pkgs.magshift ];

    # 2. Enable uinput kernel module
    hardware.uinput.enable = true;

    # 3. Configure dynamic permissions via Udev rules.
    # We use 'uaccess' and 'seat' tags to grant R/W access
    # ONLY to the user currently logged into the active physical session.
    services.udev.extraRules = ''
      # Grant access to create virtual input devices (uinput) to the active user
      KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0", OPTIONS+="static_node=uinput"

      # Grant access to read physical keyboard events to the active user
      # IMPORT{builtin}="input_id" is often handled by default rules, but we ensure it's there
      SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0"
    '';
  };
}