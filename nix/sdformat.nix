{ pkgs }:
let
  inherit (pkgs) lib;
  python = pkgs.python3;
  # SDFormat 15 requires these Gazebo major versions. nixpkgs currently
  # packages newer, incompatible majors and excludes gz-cmake on Darwin.
  source =
    name: version: hash:
    pkgs.fetchurl {
      url = "https://osrf-distributions.s3.amazonaws.com/${name}/releases/${name}-${version}.tar.bz2";
      inherit hash;
    };
  common = {
    strictDeps = true;
    nativeBuildInputs = with pkgs; [
      cmake
      ninja
      pkg-config
      python3
    ];
    cmakeFlags = [
      "-DBUILD_TESTING=OFF"
      "-DBUILD_EXAMPLES=OFF"
      "-DCMAKE_INSTALL_LIBDIR=lib"
    ];
    meta = {
      license = lib.licenses.asl20;
      platforms = lib.platforms.unix;
    };
  };
  pythonBindings = {
    nativeBuildInputs = common.nativeBuildInputs ++ [ python.pkgs.pybind11 ];
    postInstall = ''
      mkdir -p "$out/${python.sitePackages}"
      mv "$out/lib/python/"* "$out/${python.sitePackages}/"
      rmdir "$out/lib/python"
    '';
  };
  gz-cmake = pkgs.stdenv.mkDerivation (
    common
    // {
      pname = "gz-cmake";
      version = "4.3.0";
      src = source "gz-cmake" "4.3.0" "sha256-Ef+K8mEZmODNG5shm4Sbt2U4zgvfSlAuXH7Llcc1rGk=";
      cmakeFlags = common.cmakeFlags ++ [ "-DBUILDSYSTEM_TESTING=OFF" ];
    }
  );
  gz-utils = pkgs.stdenv.mkDerivation (
    common
    // {
      pname = "gz-utils";
      version = "3.1.1";
      src = source "gz-utils" "3.1.1" "sha256-FhlCotAMggaDz4jkHEhUXo2kyVmq13yiIpAh5flhIB0=";
      buildInputs = [ gz-cmake ];
      propagatedBuildInputs = with pkgs; [
        cli11
        spdlog
      ];
      cmakeFlags = common.cmakeFlags ++ [ "-DGZ_UTILS_VENDOR_CLI11=OFF" ];
    }
  );
  gz-math = pkgs.stdenv.mkDerivation (
    common
    // pythonBindings
    // {
      pname = "gz-math";
      version = "8.4.0";
      src = source "gz-math" "8.4.0" "sha256-YkRbq5ZjYn92MaoP80vq2CUl2TUqQE0/boL87002GUo=";
      buildInputs = [ gz-cmake ];
      propagatedBuildInputs = [
        gz-utils
        pkgs.eigen
        python
      ];
      cmakeFlags = common.cmakeFlags ++ [
        "-DSKIP_SWIG=ON"
        "-DSKIP_PYBIND11=OFF"
      ];
    }
  );
  sdformat = pkgs.stdenv.mkDerivation (
    common
    // pythonBindings
    // {
      pname = "sdformat";
      version = "15.4.0";
      src = source "sdformat" "15.4.0" "sha256-IrmCUgG/18DH7MYJle/KkL8Frq3cwwiuUYB0agjNC5A=";
      nativeBuildInputs = pythonBindings.nativeBuildInputs ++ [
        pkgs.ruby
      ];
      propagatedBuildInputs = [
        gz-math
        gz-utils
        python
      ];
      buildInputs = with pkgs; [
        gz-cmake
        tinyxml-2
        urdfdom
      ];
      cmakeFlags = common.cmakeFlags ++ [
        "-DUSE_INTERNAL_URDF=OFF"
        "-DSKIP_PYBIND11=OFF"
      ];
    }
  );
in
{
  inherit sdformat gz-math;
}
