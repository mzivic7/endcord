import argparse
import importlib.metadata
import importlib.util
import os
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
        command = "pipenv install --dev"
        os.system(command)


def remove_media():
    """Remove media support"""
    if check_media_support():
        command = "pipenv run python -m pip uninstall -y pillow pyav numpy"
        os.system(command)


def prepare():
    """OS specific preparations for running and building"""
    if sys.platform == "linux":
        pass
    elif sys.platform == "win32":
        try:
            _ = importlib.metadata.distribution("windows-curses")
        except importlib.metadata.PackageNotFoundError:
            try:   # python-magic-bin contains required dll
                importlib.metadata.version("python-magic")
                uninstall_magic = "pipenv uninstall python-magic"
                os.system(uninstall_magic)
            except importlib.metadata.PackageNotFoundError:
                pass
            install_windows_dependencies = "pipenv install pywin32 pywin32-ctypes windows-toasts windows-curses python-magic-bin"
            os.system(install_windows_dependencies)
    elif sys.platform == "mac":
        pass
    else:
        sys.exit(f"This platform is not supported: {sys.platform}")


def build_with_pyinstaller(onedir):
    """Build with pyistaller"""
    prepare()
    if check_media_support():
        hidden_imports = "--hidden-import uuid "
        pkgname = APP_NAME
        print("ASCII media support is enabled")
    else:
        hidden_imports = ""
        pkgname = f"{APP_NAME}-lite"
        print("ASCII media support is disabled")
    if onedir:
        onedir = "--onedir"
    else:
        onedir = "--onefile"

    if sys.platform == "linux":
        command = f'pipenv run python -m PyInstaller {hidden_imports}--collect-data=emoji --noconfirm {onedir} --clean --name {pkgname} "main.py"'
        os.system(command)
    elif sys.platform == "win32":
        command = f'pipenv run python -m PyInstaller {hidden_imports}--collect-data=emoji --noconfirm {onedir} --console --clean --name {pkgname} "main.py"'
        os.system(command)
    elif sys.platform == "mac":
        command = f'pipenv run python -m PyInstaller {hidden_imports}--collect-data=emoji --noconfirm {onedir} --console --clean --name {pkgname} "main.py"'
        os.system(command)
    else:
        sys.exit(f"This platform is not supported: {sys.platform}")


def build_with_nuitka(onedir):
    """Build with nuitka"""
    sys.exit("Building with Nuitka is currently failing due to a bug: https://github.com/Nuitka/Nuitka/issues/3442")
    prepare()
    if check_media_support():
        pkgname = APP_NAME
        print("ASCII media support is enabled")
    else:
        pkgname = f"{APP_NAME}-lite"
        print("ASCII media support is disabled")
    if importlib.util.find_spec("nuitka") is None:
        command = "pipenv install nuitka"
        os.system(command)
    if onedir:
        onedir = "--standalone"
    else:
        onedir = "--onefile"

    if sys.platform == "linux":
        command = f"pipenv run python -m nuitka {onedir} --include-module=uuid --include-package-data=emoji --remove-output --output-dir=dist --output-filename={pkgname} main.py"
        os.system(command)
    elif sys.platform == "win32":
        command = f"pipenv run python -m nuitka {onedir} --include-module=uuid --include-package-data=emoji --remove-output --output-dir=dist --output-filename={pkgname} main.py"
        os.system(command)
    elif sys.platform == "mac":
        command = f'pipenv run python -m nuitka {onedir} --include-module=uuid --include-package-data=emoji --remove-output --output-dir=dist --output-filename={pkgname} --macos-app-name={APP_NAME} --macos-app-version={VERSION} --macos-app-protected-resource="NSMicrophoneUsageDescription:Microphone access for recording audio." main.py'
        os.system(command)
    else:
        sys.exit("Building with Nuitka is currently only supported on Linux")


def parser():
    """Setup argument parser for CLI"""
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="Setup and build script for endcord",
    )
    parser._positionals.title = "arguments"
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Prepare build and working environment, OS specific, main.py can be run after this",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build endcord, prepare should be ran atleast once before or or together with building",
    )
    parser.add_argument(
        "--nuitka",
        action="store_true",
        help="Try building with nuitka",
    )
    parser.add_argument(
        "--lite",
        action="store_true",
        help="Change environment to build or run endcord-lite, by deleting media support depenencies",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parser()
    if args.lite:
        remove_media()
    else:
        add_media()
    if args.prepare:
        prepare()
    onedir = False
    if args.onedir:
        onedir = True
    if args.nuitka:
        build_with_nuitka(onedir)
    if args.build:
        build_with_pyinstaller(onedir)
    if not (args.prepare or args.build or args.lite):
        sys.exit("No arguments provided")
