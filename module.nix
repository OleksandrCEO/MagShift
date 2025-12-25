# module.nix
{ config, lib, pkgs, ... }:

let
  cfg = config.services.skyswitcher;
in
{
  options.services.skyswitcher = {
    enable = lib.mkEnableOption "SkySwitcher service";
  };

  config = lib.mkIf cfg.enable {
    # 1. Пакет (ми очікуємо, що pkgs.skyswitcher ВЖЕ існує завдяки оверлею у flake.nix)
    environment.systemPackages = [
      pkgs.skyswitcher
      pkgs.wl-clipboard
    ];

    # 2. Права доступу
    hardware.uinput.enable = true;

    # 3. Systemd сервіс
    systemd.user.services.skyswitcher = {
      description = "SkySwitcher Layout Fixer";

      wantedBy = [ "default.target" ];
      partOf = [ "graphical-session.target" ];

      serviceConfig = {
        ExecStart = "${pkgs.skyswitcher}/bin/skyswitcher";
        Restart = "always";
        RestartSec = "3"; # Чекаємо трохи перед перезапуском, якщо впаде
      };
    };
  };
}