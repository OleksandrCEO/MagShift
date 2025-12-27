{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    (pkgs.python3.withPackages (ps: [ ps.evdev ]))
    pkgs.evtest
  ];

  shellHook = ''
    echo "MagShift environment loaded."
    echo "Run: python3 main.py"
  '';
}