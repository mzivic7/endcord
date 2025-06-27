import argparse
import importlib.metadata
import importlib.util
import os
import shutil
import sys

APP_NAME = "endcord"
VERSION = "0.9.0"


def check_media_support():
    """Check if media is supported"""
    return (
        importlib.util.find_spec("PIL") is not None and
        importlib.util.find_spec("av") is not None and
        importlib.util.find_spec("numpy") is not None
    )


def add_media():
    """Add media support"""
    if not check_media_support():
        command = "uv sync --all-groups"
        os.system(command)


def remove_media():
    """Remove media support"""
    if check_media_support():
        command = "uv pip uninstall pillow av"
        os.system(command)


def check_dev():
    """Check if its dev environment and set it up"""
    if importlib.util.find_spec("PyInstaller") is None or importlib.util.find_spec("nuitka") is None:
        command = "uv sync --group build"
        os.system(command)


def build_with_pyinstaller(onedir):
    """Build with pyinstaller"""
    if check_media_support():
        pkgname = APP_NAME
        print("ASCII media support is enabled")
    else:
        pkgname = f"{APP_NAME}-lite"
        print("ASCII media support is disabled")
    if onedir:
        onedir = "--onedir"
    else:
        onedir = "--onefile"
    hidden_imports = "--hidden-import uuid"

    if sys.platform == "linux":
        command = f'uv run python -m PyInstaller {onedir} {hidden_imports} --collect-data=emoji --noconfirm --clean --name {pkgname} "main.py"'
        os.system(command)
    elif sys.platform == "win32":
        command = f'uv run python -m PyInstaller {onedir} {hidden_imports} --collect-data=emoji --noconfirm --console --clean --name {pkgname} "main.py"'
        os.system(command)
    elif sys.platform == "darwin":
        command = f'uv run python -m PyInstaller {onedir} {hidden_imports} --collect-data=emoji --noconfirm --console --clean --name {pkgname} "main.py"'
        os.system(command)
    else:
        sys.exit(f"This platform is not supported: {sys.platform}")
    # cleanup
    try:
        os.remove(f"{pkgname}.spec")
        shutil.rmtree("build")
    except FileNotFoundError:
        pass


def build_with_nuitka(onedir, clang):
    """Build with nuitka"""
    if check_media_support():
        pkgname = APP_NAME
        print("ASCII media support is enabled")
    else:
        pkgname = f"{APP_NAME}-lite"
        print("ASCII media support is disabled")
    if onedir:
        onedir = "--standalone"
    else:
        onedir = "--onefile"
    if clang:
        clang = "--clang"
    else:
        clang = ""
    hidden_imports = "--include-module=uuid"
    include_package_data = "--include-package-data=emoji --include-package-data=soundcard"

    if sys.platform == "linux":
        command = f"uv run python -m nuitka {clang} {onedir} {hidden_imports} {include_package_data} --remove-output --output-dir=dist --output-filename={pkgname} main.py"
        os.system(command)
    elif sys.platform == "win32":
        command = f"uv run python -m nuitka {clang} {onedir} {hidden_imports} {include_package_data} --remove-output --output-dir=dist --output-filename={pkgname} --assume-yes-for-downloads main.py"
        os.system(command)
    elif sys.platform == "darwin":
        command = f'uv run python -m nuitka {clang} {onedir} {hidden_imports} {include_package_data} --remove-output --output-dir=dist --output-filename={pkgname} --macos-app-name={APP_NAME} --macos-app-version={VERSION} --macos-app-protected-resource="NSMicrophoneUsageDescription:Microphone access for recording voice message." main.py'
        os.system(command)
    else:
        sys.exit(f"This platform is not supported: {sys.platform}")


def parser():
    """Setup argument parser for CLI"""
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="setup and build script for endcord",
    )
    parser._positionals.title = "arguments"
    parser.add_argument(
        "--nuitka",
        action="store_true",
        help="build with nuitka, takes a long time, but more optimized executable",
    )
    parser.add_argument(
        "--clang",
        action="store_true",
        help="use clang when building with nuitka",
    )
    parser.add_argument(
        "--lite",
        action="store_true",
        help="change environment to build or run endcord-lite, by deleting media support depenencies",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="build into directory instead single executable",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parser()
    check_dev()
    if args.lite:
        remove_media()
    else:
        add_media()
    if args.nuitka:
        build_with_nuitka(args.onedir, args.clang)
        sys.exit()
    else:
        build_with_pyinstaller(args.onedir)
        sys.exit()
