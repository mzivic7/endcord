import argparse
import glob
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib


def get_app_name():
    """Get app name from pyproject.toml"""
    if os.path.exists("pyproject.toml"):
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        if "project" in data and "version" in data["project"]:
            return str(data["project"]["name"])
        print("App name not specified in pyproject.toml")
        sys.exit()
    print("pyproject.toml file not found")
    sys.exit()


def get_version_number():
    """Get version number from pyproject.toml"""
    if os.path.exists("pyproject.toml"):
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        if "project" in data and "version" in data["project"]:
            return str(data["project"]["version"])
        print("Version not specified in pyproject.toml")
        sys.exit()
    print("pyproject.toml file not found")
    sys.exit()


def supports_color():
    """Return True if the running terminal supports ANSI colors."""
    if sys.platform == "win32":
        return (os.getenv("ANSICON") is not None or
            os.getenv("WT_SESSION") is not None or
            os.getenv("TERM_PROGRAM") == "vscode" or
            os.getenv("TERM") in ("xterm", "xterm-color", "xterm-256color")
        )
    if not sys.stdout.isatty():
        return False
    return os.getenv("TERM", "") != "dumb"


PKGNAME = get_app_name()
PKGVER = get_version_number()
USE_COLOR = supports_color()


def fprint(text, color_code="\033[1;35m", prepend=f"[{PKGNAME.capitalize()} Build Script]: "):
    """Print colored text prepended with text, default is light purple"""
    if USE_COLOR:
        print(f"{color_code}{prepend}{text}\033[0m")
    else:
        print(f"{prepend}{text}")


def check_media_support():
    """Check if media is supported"""
    return (
        importlib.util.find_spec("PIL") is not None and
        importlib.util.find_spec("av") is not None and
        importlib.util.find_spec("nacl") is not None
    )


def add_media():
    """Add media support"""
    if not check_media_support():
        fprint("Adding media support dependencies")
        subprocess.run(["uv", "sync", "--all-groups"], check=True)


def remove_media():
    """Remove media support"""
    if check_media_support():
        fprint("Removing media support dependencies")
        subprocess.run(["uv", "pip", "uninstall", "pillow" , "av", "pynacl"], check=True)


def check_dev():
    """Check if its dev environment and set it up"""
    if importlib.util.find_spec("PyInstaller") is None or importlib.util.find_spec("nuitka") is None:
        subprocess.run(["uv", "sync", "--group", "build"], check=True)


def build_third_party_licenses(exclude=[]):
    """Collect and build all lincenses found in venv into THIRD_PARTY_LICENSES.txt file"""
    fprint("Building list of third party licenses")
    subprocess.run(["uv", "pip", "install", "pip-licenses"], check=True)
    command = [
        "uv", "run", "pip-licenses",
        "--ignore-packages " + " ".joind(exclude),
        "--format=plain-vertical",
        "--no-license-path",
        "--output-file=THIRD_PARTY_LICENSES.txt",
    ]
    subprocess.run(command, check=True)
    subprocess.run(["uv", "pip", "uninstall", "pip-licenses", "prettytable", "wcwidth"], check=True)


def get_cython_bins(directory="endcord_cython", startswith=None):
    """Get list of all cython built binaries"""
    files = os.listdir(directory)
    bins = []
    for file in files:
        if (not startswith or file.startswith(startswith)) and (file.endswith(".pyd") or file.endswith(".so")):
            bins.append(file)
    return bins


def find_file_in_venv(lib_name, file_name):
    """Search for file in specified library in current venv"""
    if isinstance(file_name, list):
        file_name = os.path.join(*file_name)
    for root, dirs, files in os.walk(".venv"):
        if lib_name in dirs:
            lib_dir = os.path.join(root, lib_name)
            path = os.path.join(lib_dir, file_name)
            if os.path.isfile(path):
                return path
    else:
        print(f"{lib_name}/{file_name} not found")
        return


def patch_soundcard():
    """
    Search for soundcard/mediafoundation.py in .venv
    Prepend "if _ole32: " to "_ole32.CoUninitialize()" line while respecting indentation
    Search for soundcard/pulseaudio.py in .venv
    replace assert with proper exception
    """
    fprint("Patching soundcard")
    if not os.path.exists(".venv"):
        print(".venv dir not found")
        return

    # patch mediafoundation.py
    path = find_file_in_venv("soundcard", "mediafoundation.py")
    if not path:
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    pattern = re.compile(r"^(\s*)_ole32\.CoUninitialize\(\)")
    changed = False
    for num, line in enumerate(lines):
        match = re.match(pattern, line)
        if match:
            indent = match.group(1)
            lines[num] = f"{indent}if _ole32: _ole32.CoUninitialize()\n"
            changed = True
            break

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Patched file: {path}")
    else:
        print(f"Nothing to patch in file {path}")

    # patch pulseaudio.py
    path = find_file_in_venv("soundcard", "pulseaudio.py")
    if not path:
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    pattern = re.compile(r"^(\s*)assert self\._pa_context_get_state")
    changed = False
    for num, line in enumerate(lines):
        match = re.match(pattern, line)
        if match:
            indent = match.group(1)
            lines[num] = f"{indent}if self._pa_context_get_state(self.context) != _pa.PA_CONTEXT_READY:\n"
            lines.insert(num+1, f'{indent+"    "}raise RuntimeError("PulseAudio context not ready (no sound system?)")\n')
            changed = True
            break

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Patched file: {path}")
    else:
        print(f"Nothing to patch in file {path}")


def clean_emoji():
    """Clean emoji dict from unused emojis and data"""
    fprint("Cleaning emoji data")
    changed = False
    # find emoji file
    if not os.path.exists(".venv"):
        print(".venv dir not found")
        return
    path = find_file_in_venv("emoji", ["unicode_codes", "emoji.json"])

    # clean emoji
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cleaned = {}
    for key, value in data.items():
        if value.get("status", 0) <= 2:
            value.pop("E", None)
            cleaned[key] = value
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=None, separators=(",", ":"))

    # remove unused languages
    pattern = os.path.join(os.path.dirname(path), "emoji_*.json")
    for path in glob.glob(pattern):
        changed = True
        try:
            os.remove(path)
        except Exception:
            pass

    # remove example from py file
    path = find_file_in_venv("emoji", ["unicode_codes", "data_dict.py"])
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        if line.strip().startswith("EMOJI_DATA"):
            break
        new_lines.append(line)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    if not changed:
        print("Emoji data is already cleaned")


def toggle_experimental(check_only=False):
    """Toggle experimental mode"""
    file_list = []
    for path, subdirs, files in os.walk(os.getcwd()):
        subdirs[:] = [d for d in subdirs if not d.startswith(".")]
        for name in files:
            file_path = os.path.join(path, name)
            if not name.startswith(".") and (file_path.endswith(".py") or file_path.endswith(".pyx")):
                file_list.append(file_path)
    enable = False
    for path in file_list:
        # replace imports
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        changed = False
        for num, line in enumerate(lines):
            if line.startswith("import curses"):
                lines[num] = "from endcord import pgcurses as curses\n"
                changed = True
                enable = True
                break
            elif line.startswith("from endcord import pgcurses as curses"):
                lines[num] = "import curses\n"
                changed = True
                enable = False
                break
        if changed and not check_only:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
    if check_only:
        return not enable

    # backup cython binaries
    if enable:
        bins = get_cython_bins(directory="endcord_cython")
        if bins:
            for binary in bins:
                try:
                    importlib.import_module("endcord_cython." + binary.split(".")[0])
                except ImportError:
                    pass
            if "curses" in sys.modules:
                for file in bins:
                    old_name = os.path.join("endcord_cython", file)
                    new_name = os.path.join("endcord_cython", "bkp_" + file)
                    if os.path.exists(new_name):
                        os.remove(new_name)
                    os.rename(old_name, new_name)
    else:
        bins = get_cython_bins(directory="endcord_cython", startswith="bkp_")
        if bins:
            error = False
            for binary in bins:
                try:
                    importlib.import_module("endcord_cython." + binary.split(".")[0])
                except ImportError:
                    error = True
                    break
            if "curses" in sys.modules or error:
                for file in bins:
                    old_name = os.path.join("endcord_cython", file)
                    new_name = os.path.join("endcord_cython", file[4:])
                    if os.path.exists(new_name):
                        os.remove(new_name)
                    os.rename(old_name, new_name)

    # toggle dependencies
    experimental_dependencies = ["pygame-ce", "pyperclip", "pystray"]
    if sys.platform == "linux":
        experimental_dependencies += ["pygobject"]
    if enable:
        subprocess.run(["uv", "pip", "install"] + experimental_dependencies, check=True)
        fprint("Experimental windowed mode enabled!")
    else:
        subprocess.run(["uv", "pip", "uninstall"] + experimental_dependencies, check=True)
        fprint("Experimental windowed mode disabled!")
    return not enable



def build_numpy_lite(clang):
    """Build numpy without openblass to reduce final binary size"""
    if sys.platform != "linux":
        fprint("Skipping numpy lite (no openblas) building on non-linux platforms")
        return

    # check if numpy without blas is not already installed
    cmd = [
        "uv", "run", "python", "-c",
        "import numpy; print(int(numpy.__config__.show_config('dicts')['Build Dependencies']['blas'].get('found', False)))",
    ]
    fprint("Building numpy lite (no openblas)")
    if int(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()):
        if clang:
            os.environ["CC"] = "clang"
            os.environ["CXX"] = "clang++"
        subprocess.run(["uv", "pip", "install", "pip"], check=True)   # because uv wont work with --config-settings as intended
        try:
            if sys.platform == "win32":
                python_interpreter = r".venv\Scripts\python.exe"
            else:
                python_interpreter = ".venv/bin/python"
            subprocess.run([python_interpreter, "-m", "pip", "uninstall", "--yes", "numpy"], check=True)
            subprocess.run([
                python_interpreter, "-m", "pip", "install", "--no-cache-dir", "--no-binary=:all:", "numpy",
                "--config-settings=setup-args=-Dblas=None",
                "--config-settings=setup-args=-Dlapack=None",
            ], check=True)
        except subprocess.CalledProcessError:   # fallback
            print("Failed building numpy lite (no openblas), faling back to default numpy")
            subprocess.run(["uv", "pip", "install", "numpy"], check=True)
        subprocess.run(["uv", "pip", "uninstall", "pip"], check=True)
    else:
        print("Numpy lite (no openblas) is already built")


def build_cython(clang, mingw):
    """Build cython extensions"""
    fprint(f"Compiling cython code with {"clang" if clang else "gcc"}{("mingw") if mingw else ""}")
    cmd = ["uv", "run", "python", "setup.py", "build_ext", "--inplace"]
    if clang:
        os.environ["CC"] = "clang"
        os.environ["CXX"] = "clang++"
    elif mingw and sys.platform == "win32":
        cmd.append("--compiler=mingw32")   # covers mingw 32 and 64

    # run process with control of stdout
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in process.stdout:
        line_clean = line.rstrip("\n")
        if len(line_clean) < 100 and "Cythonizing" not in line_clean and "Compiling" not in line_clean and "creating" not in line_clean:
            print(line_clean)
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)

    files = [f for f in os.listdir("endcord_cython") if f.endswith(".c")]
    for f in files:
        os.remove(os.path.join("endcord_cython", f))
    shutil.rmtree("build")


def build_with_pyinstaller(onedir, nosoundcard):
    """Build with pyinstaller"""
    if check_media_support():
        pkgname = PKGNAME
        fprint("ASCII media support is enabled")
    else:
        pkgname = f"{PKGNAME}-lite"
        fprint("ASCII media support is disabled")

    mode = "--onedir" if onedir else "--onefile"
    hidden_imports = ["--hidden-import=uuid"]
    exclude_imports = [
        "--exclude-module=cython",
        "--exclude-module=zstandard",
    ]
    package_data = [
        "--collect-data=emoji",
        "--collect-data=soundcard",
    ]

    # options
    if nosoundcard:
        exclude_imports.append("--exclude-module=soundcard")
        package_data.remove("--collect-data=soundcard")

    # platform-specific
    if sys.platform == "linux":
        options = []
        hidden_imports += ["--hidden-import=soundcard.pulseaudio"]
    elif sys.platform == "win32":
        options = ["--console"]
        hidden_imports += ["--hidden-import=win32timezone"]
    elif sys.platform == "darwin":
        options = []

    # prepare command and run it
    cmd = [
        "uv", "run", "python", "-m", "PyInstaller",
        mode,
        *hidden_imports,
        *exclude_imports,
        *package_data,
        *options,
        "--noconfirm",
        "--clean",
        f"--name={pkgname}",
        "main.py",
    ]
    cmd = [arg for arg in cmd if arg != ""]
    fprint("Starting pyinstaller")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(e.returncode)

    # cleanup
    fprint("Cleaning up")
    try:
        os.remove(f"{pkgname}.spec")
        shutil.rmtree("build")
    except FileNotFoundError:
        pass
    fprint(f"Finished building {pkgname}")


def build_with_nuitka(onedir, clang, mingw, nosoundcard, experimental=False):
    """Build with nuitka"""
    if check_media_support():
        pkgname = PKGNAME
        fprint("ASCII media support is enabled")
    else:
        pkgname = f"{PKGNAME}-lite"
        fprint("ASCII media support is disabled")

    build_numpy_lite(clang)
    patch_soundcard()
    clean_emoji()

    mode = "--standalone" if onedir else "--onefile"
    compiler = ""
    if clang:
        compiler = "--clang"
    elif mingw:
        compiler = "--mingw64"
    python_flags = ["--python-flag=-OO"]
    hidden_imports = ["--include-module=uuid"]
    # excluding zstandard because its nuitka dependency bu also urllib3 optional dependency, and uses lots of space
    exclude_imports = [
        "--nofollow-import-to=cython",
        "--nofollow-import-to=zstandard",
        "--nofollow-import-to=google._upb",
    ]
    package_data = [
        "--include-package-data=emoji:unicode_codes/emoji.json",
        "--include-package-data=soundcard",
    ]

    # options
    if nosoundcard:
        exclude_imports.append("--nofollow-import-to=soundcard")
        package_data.remove("--include-package-data=soundcard")
    if clang:
        os.environ["CFLAGS"] = "-Wno-macro-redefined"

    # platform-specific
    if sys.platform == "linux":
        options = []
        if experimental:
            options.append("--include-package=gi._enum")
    elif sys.platform == "win32":
        options = ["--assume-yes-for-downloads"]
        hidden_imports += [
            "--include-package=winrt.windows.foundation",
            "--include-package=winrt.windows.ui.notifications",
            "--include-package=winrt.windows.data.xml.dom",
            "--include-package=win32timezone",
        ]
        package_data += ["--include-package-data=winrt"]
    elif sys.platform == "darwin":
        options = [
            f"--macos-app-name={PKGNAME}",
            f"--macos-app-version={get_version_number()}",
            '--macos-app-protected-resource="NSMicrophoneUsageDescription:Microphone access for recording voice message."',
        ]

    # prepare command and run it
    cmd = [
        "uv", "run", "python", "-m", "nuitka",
        mode,
        compiler,
        *python_flags,
        *hidden_imports,
        *exclude_imports,
        *package_data,
        *options,
        "--remove-output",
        "--output-dir=dist",
        f"--output-filename={pkgname}",
        "main.py",
    ]
    cmd = [arg for arg in cmd if arg != ""]
    fprint("Starting nuitka")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(e.returncode)

    # cleanup
    fprint("Cleaning up")
    try:
        os.remove(f"{pkgname}.spec")
        shutil.rmtree("build")
    except FileNotFoundError:
        pass
    fprint(f"Finished building {pkgname}")


def parser():
    """Setup argument parser for CLI"""
    parser = argparse.ArgumentParser(
        prog="build.py",
        description=f"build script for {PKGNAME}",
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
        help="change environment to build or run endcord-lite, by deleting voice call and media support depenencies",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="build into directory instead single executable",
    )
    parser.add_argument(
        "--nocython",
        action="store_true",
        help="build without compiling cython code",
    )
    parser.add_argument(
        "--nosoundcard",
        action="store_true",
        help="build without soundcard dependency, for super lightewight build, will enable lite mode, and notifications sound wont work unless pw-cat (pipewire) or paplay (pulseaudio) is installed on linux, and not at all on windows",
    )
    parser.add_argument(
        "--mingw",
        action="store_true",
        help="use mingw instead msvc on windows, has no effect on Linux and macOS, or with --clang flag",
    )
    parser.add_argument(
        "--toggle-experimental",
        action="store_true",
        help="toggle experimental mode and exit",
    )
    parser.add_argument(
        "--build-licenses",
        action="store_true",
        help="build file containing licenses from all used third party libraries",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parser()

    check_dev()
    if args.toggle_experimental:
        toggle_experimental()
        sys.exit()
    if args.lite or args.nosoundcard:
        remove_media()
    else:
        add_media()

    experimental = toggle_experimental(check_only=True)
    if experimental:
        experimental_dependencies = ["pygame-ce", "pyperclip", "pystray"]
        if sys.platform == "linux":
            experimental_dependencies += ["pygobject"]
        subprocess.run(["uv", "pip", "install"] + experimental_dependencies, check=True)
        fprint("Experimental windowed mode enabled!")

    if sys.platform not in ("linux", "win32", "darwin"):
        sys.exit(f"This platform is not supported: {sys.platform}")

    if not args.nocython:
        try:
            build_cython(args.clang, args.mingw)
        except Exception as e:
            fprint(f"Failed building cython extensions, error: {e}")

    if args.build_licenses:
        exclude = ["ordered-set", "zstandard", "altgraph", "packaging", "pyinstaller-hooks-contrib", "packaging", "setuptools"]
        build_third_party_licenses(exclude)

    if args.nuitka:
        build_with_nuitka(args.onedir, args.clang, args.mingw, args.nosoundcard, experimental)
        sys.exit()
    else:
        build_with_pyinstaller(args.onedir, args.nosoundcard)
        sys.exit()
