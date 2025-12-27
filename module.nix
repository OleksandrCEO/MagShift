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
      # 1. Virtual input device (uinput)
      # We add 'uaccess' and ensure it's processed properly
      KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0", OPTIONS+="static_node=uinput"

      # 2. Physical keyboards
      # We call 'input_id' explicitly to ensure ENV{ID_INPUT_KEYBOARD} is populated
      # We also add a debug variable ENV{MAGSHIFT_ID}="1"
      SUBSYSTEM=="input", KERNEL=="event*", IMPORT{builtin}="input_id", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0", ENV{MAGSHIFT_ID}="1"
    '';
  };
}