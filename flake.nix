# flake.nix
{
  description = "SkySwitcher";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      packages.${system}.default = import ./default.nix { inherit pkgs; };

      # Щоб працювало `nix develop` (середовище розробки)
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = with pkgs; [
          (python3.withPackages (ps: [ ps.evdev ]))
          wl-clipboard
          evtest
        ];
      };
    };
}