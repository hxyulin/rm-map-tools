{
  description = "rm-map-tools native validation dependencies";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      packagesFor =
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        import ./nix/sdformat.nix { inherit pkgs; };
    in
    {
      packages = forAllSystems (system: {
        inherit (packagesFor system) sdformat;
      });
      checks = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          gazebo = packagesFor system;
          python = pkgs.python3.withPackages (ps: [
            ps.numpy
            ps.lxml
            (ps.toPythonModule gazebo.sdformat)
            (ps.toPythonModule gazebo.gz-math)
          ]);
        in
        {
          sdformat =
            pkgs.runCommand "sdformat-exporter-check"
              {
                nativeBuildInputs = [ python ];
                PYTHONPATH =
                  pkgs.lib.makeSearchPath pkgs.python3.sitePackages [
                    gazebo.sdformat
                    gazebo.gz-math
                  ]
                  + ":${./python}";
              }
              ''
                python3 - <<'PYTHON'
                from pathlib import Path
                import sdformat15
                from export_sim import sdformat_parse
                assert sdformat15.__file__.startswith("/nix/store/")
                Path("sample.sdf").write_text('<sdf version="1.12"><world name="test"><model name="box"><static>true</static><link name="body"><pose>1 2 3 0 0 0</pose></link></model></world></sdf>')
                parsed = sdformat_parse("sample.sdf")
                assert parsed is not None, "SDFormat validation must not silently skip"
                assert parsed["module"] == "sdformat15"
                assert parsed["world"] == "test" and parsed["static"]
                assert parsed["links"][0]["pose"] == [1, 2, 3, 0, 0, 0]
                PYTHON
                touch "$out"
              '';
        }
      );
      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          gazebo = packagesFor system;
          python = pkgs.python3.withPackages (ps: [
            ps.numpy
            ps.lxml
            (ps.toPythonModule gazebo.sdformat)
            (ps.toPythonModule gazebo.gz-math)
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              rustup
              cmake
              ninja
              pkg-config
              uv
              python
              urdfdom
            ];
            buildInputs = [ gazebo.sdformat ];
            # The CAD virtualenv uses Python 3.12. Run SDF validation with
            # its own matching interpreter even when called from that venv.
            SDFORMAT_PYTHON = "${python}/bin/python3";
            # The wrapped Python already carries its modules. Do not leak
            # Nix's Python 3.14 setup-hook paths into the Python 3.12 CAD venv.
            shellHook = ''
              unset PYTHONPATH
            '';
          };
        }
      );
    };
}
