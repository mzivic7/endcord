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
    print("Media support is enabled")
else:
    hidden_imports = ""
    print("Media support is disabled")

if sys.platform == "win32":
    command = f'pipenv run python -m PyInstaller {hidden_imports}--noconfirm --onefile --windowed --clean --name "endcord" "main.py"'
    os.system(command)
elif sys.platform == "linux":
    command = f'pipenv run python -m PyInstaller {hidden_imports}--noconfirm --onefile --windowed --clean --name "endcord" "main.py"'
    os.system(command)
elif sys.platform == "mac":
    command = f'pipenv run python -m PyInstaller {hidden_imports}--noconfirm --onefile --windowed --clean --name "endcord" "main.py"'
    os.system(command)
else:
    sys.exit(f"This platform is not supported: {sys.platform}")
