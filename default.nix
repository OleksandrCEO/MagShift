# default.nix

{ pkgs ? import <nixpkgs> {} }:

pkgs.writers.writePython3Bin "magshift" {
  libraries = [ pkgs.python3Packages.evdev ];
  # E265: main.py carries its own '#!/usr/bin/env python3' shebang (needed by the
  # install.sh path for traditional distros); writePython3Bin prepends its own on
  # line 1, pushing ours to line 2 where flake8 no longer treats it as a shebang.
  flakeIgnore = [ "E501" "E265" ];
} (builtins.readFile ./main.py)