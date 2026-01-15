# module.nix

{ config, lib, pkgs, ... }:

let
  cfg = config.services.magshift;

  # Створюємо окремий пакет, який містить файл правил udev.
  # Ім'я файлу починається з '60-', щоб гарантувати виконання ДО системного '70-uaccess'.
  magshiftUdevRules = pkgs.writeTextDir "lib/udev/rules.d/60-magshift.rules" ''
    # 1. Virtual input device (uinput)
    KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0", OPTIONS+="static_node=uinput"

    # 2. Physical keyboards
    # Важливо: ми додаємо теги ДО того, як systemd-logind їх перевірятиме
    SUBSYSTEM=="input", KERNEL=="event*", IMPORT{builtin}="input_id", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess", TAG+="seat", ENV{ID_SEAT}="seat0", ENV{MAGSHIFT_ID}="1"
  '';
in
{
  options.services.magshift = {
    enable = lib.mkEnableOption "MagShift package and dynamic permissions";

    # auto num lock feature for cases when system does not supports it for some reason
    autoNumlock = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Automatically force NumLock on service start.";
    };
  };

  config = lib.mkIf cfg.enable {
    # 1. Install package
    environment.systemPackages = [ pkgs.magshift ];

    # 2. Enable kernel module
    hardware.uinput.enable = true;

    # 3. Inject rules
    services.udev.packages = [ magshiftUdevRules ];

    # 4. Systemd Service definition
    systemd.services.magshift = {
      description = "MagShift Keyboard Service";
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        ExecStart = "${pkgs.magshift}/bin/magshift" + (if cfg.autoNumlock then " --auto-numlock" else "");
        Restart = "always";
        RestartSec = "3";
      };
    };

    # use it like:
    # systemd.services.magshift.enable = true;
    # systemd.services.magshift.autoNumlock = false;
  };
}