import importlib.util
import os
import sys

support_media = (
    importlib.util.find_spec("PIL") is not None and
    importlib.util.find_spec("av") is not None and
    importlib.util.find_spec("pyaudio") is not None
)

if support_media:
    hidden_imports = "--hidden-import uuid "
    pkgname = "endcord"
    print("Media support is enabled")
else:
    hidden_imports = ""
    pkgname = "endcord-lite"
    print("Media support is disabled")

if sys.platform == "win32":
    print("Installing additional dependencies")
    command = "pipenv install win10toast win11toast windows-curses"
    os.system(command)
    command = f'pipenv run python -m PyInstaller {hidden_imports}--noconfirm --onefile --windowed --clean --name {pkgname} "main.py"'
    os.system(command)
elif sys.platform == "linux":
    command = f'pipenv run python -m PyInstaller {hidden_imports}--noconfirm --onefile --windowed --clean --name {pkgname} "main.py"'
    os.system(command)
elif sys.platform == "mac":
    command = f'pipenv run python -m PyInstaller {hidden_imports}--noconfirm --onefile --windowed --clean --name {pkgname} "main.py"'
    os.system(command)
else:
    sys.exit(f"This platform is not supported: {sys.platform}")
