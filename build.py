import os
import sys

if sys.platform == "win32":
    command = f'pipenv run python -m PyInstaller --noconfirm --onefile --windowed --clean --name "endcord" "main.py"'
    os.system(command)
elif sys.platform == "linux":
    command = f'pipenv run python -m PyInstaller --noconfirm --onefile --windowed --clean --name "endcord" "main.py"'
    os.system(command)
elif sys.platform == "mac":
    command = f'pipenv run python -m PyInstaller --noconfirm --onefile --windowed --clean --name "endcord" "main.py"'
    os.system(command)
else:
    sys.exit(f"This platform is not supported: {sys.platform}")
