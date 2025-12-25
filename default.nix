# default.nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.writers.writePython3Bin "skyswitcher" {
  libraries = [ pkgs.python3Packages.evdev ];
  flakeIgnore = [ "E501" ];
} (builtins.readFile ./main.py)