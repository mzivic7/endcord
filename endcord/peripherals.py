import base64
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from ast import literal_eval
from configparser import ConfigParser

import magic
import numpy as np
import pexpect
import pexpect.popen_spawn
import soundcard
import soundfile

from endcord import defaults

logger = logging.getLogger(__name__)
match_first_non_alfanumeric = re.compile(r"^[^\w_]*")
match_split = re.compile(r"[^\w']")
APP_NAME = "endcord"
ASPELL_TIMEOUT = 0.1   # aspell limit for looking-up one word
NO_NOTIFY_SOUND_DE = ("kde", "plasma")   # linux desktops without notification sound

# get speaker
try:
    speaker = soundcard.default_speaker()
    have_sound = True
except Exception:
    have_sound = False

# platform specific code
if sys.platform == "win32":
    import win32clipboard
    from windows_toasts import Toast, WindowsToaster
    toaster = WindowsToaster(APP_NAME)
if sys.platform == "linux":
    have_gdbus = shutil.which("gdbus")
    have_notify_send = shutil.which("notify-send")
    # if this DE has no notification sound, try to get fallback sound
    no_notify_sound = False
    fallback_notification_sound = None
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "") or os.environ.get("DESKTOP_SESSION", "")
    if desktop.lower() in NO_NOTIFY_SOUND_DE:
        no_notify_sound = True
        path = "/usr/share/sounds/freedesktop/stereo"
        for keyword in ["message", "notification", "bell"]:
            for root, dirs, files in os.walk(path):
                for file in files:
                    if keyword in file.lower():
                        fallback_notification_sound = os.path.join(root, file)
                        break
                if fallback_notification_sound:
                    break
            if fallback_notification_sound:
                break

# get platform specific paths
if sys.platform == "linux":
    path = os.environ.get("XDG_DATA_HOME", "")
    if path.strip():
        config_path = os.path.join(path, f"{APP_NAME}/")
        log_path = os.path.join(path, f"{APP_NAME}/")
    else:
        config_path = f"~/.config/{APP_NAME}/"
        log_path = f"~/.config/{APP_NAME}/"
    path = os.environ.get("XDG_RUNTIME_DIR", "")
    if path.strip():
        temp_path = os.path.join(path, f"{APP_NAME}/")
    else:
        # per-user temp dir
        temp_path = f"/run/user/{os.getuid()}/{APP_NAME}/"
        # fallback to .cache
        if not os.access(f"/run/user/{os.getuid()}", os.W_OK):
            temp_path = f"~/.cache/{APP_NAME}"

    path = os.environ.get("XDG_DOWNLOAD_DIR", "")
    if path.strip():
        downloads_path = os.path.join(path, f"{APP_NAME}/")
    else:
        downloads_path = "~/Downloads/"
elif sys.platform == "win32":
    config_path = os.path.join(os.path.normpath(f"{os.environ["USERPROFILE"]}/AppData/Local/{APP_NAME}/"), "")
    log_path = os.path.join(os.path.normpath(f"{os.environ["USERPROFILE"]}/AppData/Local/{APP_NAME}/"), "")
    temp_path = os.path.join(os.path.normpath(f"{os.environ["USERPROFILE"]}/AppData/Local/Temp/{APP_NAME}/"), "")
    downloads_path = os.path.join(os.path.normpath(f"{os.environ["USERPROFILE"]}/Downloads/"), "")
elif sys.platform == "darwin":
    config_path = f"~/Library/Application Support/{APP_NAME}/"
    log_path = f"~/Library/Application Support/{APP_NAME}/"
    temp_path = f"~/Library/Caches/TemporaryItems{APP_NAME}/"
    downloads_path = "~/Downloads/"
else:
    sys.exit(f"Unsupported platform: {sys.platform}")


# ensure paths exists
for app_path in (config_path, log_path, temp_path, downloads_path):
    if not os.path.exists(os.path.expanduser(app_path)):
        os.makedirs(os.path.expanduser(app_path), exist_ok=True)


# platform specific commands
if sys.platform == "linux":
    runner = "xdg-open"
elif sys.platform == "win32":
    runner = "explorer"
elif sys.platform == "darwin":
    runner = "open"


def save_config(path, data, section):
    """Save config section"""
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    config = ConfigParser(interpolation=None)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            config.read_file(f)
    if not config.has_section(section):
        config.add_section(section)
    for key in data:
        if data[key] in (True, False, None) or isinstance(data[key], (list, tuple, int, float)):
            config.set(section, key, str(data[key]))
        else:
            config.set(section, key, f'"{str(data[key]).replace("\\", "\\\\")}"')
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)


def load_config(path, default, section="main", gen_config=False):
    """
    Load settings and theme from config
    If some value is missing, it is replaced with default value
    """
    if not path:
        path = config_path + "config.ini"
    path = os.path.expanduser(path)

    if not os.path.exists(path) or gen_config:
        save_config(path, default, section)
        if not gen_config:
            print(f"Default config generated at: {path}")
        config_data = default
    else:
        config = ConfigParser(interpolation=None)
        with open(path, "r", encoding="utf-8") as f:
            config.read_file(f)
        if not config.has_section(section):
            return default
        config_data_raw = config._sections[section]
        config_data = dict.fromkeys(default)
        for key in default:
            if key in list(config[section].keys()):
                try:
                    eval_value = literal_eval(config_data_raw[key].replace("\\", "\\\\"))
                    config_data[key] = eval_value
                except ValueError:
                    config_data[key] = config_data_raw[key]
            else:
                config_data[key] = default[key]
    return config_data


def get_themes():
    """Return list of all themes found in Themes directory"""
    themes_path = os.path.expanduser(os.path.join(config_path, "Themes"))
    if not os.path.exists(themes_path):
        os.makedirs(themes_path, exist_ok=True)
    themes = []
    for file in os.listdir(themes_path):
        if file.endswith(".ini"):
            themes.append(os.path.join(themes_path, file))
    return themes


def merge_configs(custom_config_path, theme_path):
    """Merge config and themes, from various locations"""
    gen_config = False
    error = None
    if not custom_config_path:
        if not os.path.exists(os.path.expanduser(config_path) + "config.ini"):
            logger.info("Using default config")
            gen_config = True
        custom_config_path = config_path + "config.ini"
    elif not os.path.exists(os.path.expanduser(custom_config_path)):
        gen_config = True
    config = load_config(custom_config_path, defaults.settings)
    config["config_path"] = custom_config_path
    if not theme_path and config["theme"]:
        theme_path = os.path.expanduser(config["theme"])
    saved_themes = get_themes()
    theme = load_config(custom_config_path, defaults.theme, section="theme", gen_config=gen_config)
    theme["theme_path"] = None
    if theme_path:
        # if path is only file name without extension
        if os.path.splitext(os.path.basename(theme_path))[0] == theme_path:
            for saved_theme in saved_themes:
                if os.path.splitext(os.path.basename(saved_theme))[0] == theme_path:
                    theme_path = saved_theme
                    break
            else:
                error = f"Theme {theme_path} not found in themes directory."
        if not error:
            theme_path = os.path.expanduser(theme_path)
            theme = load_config(theme_path, theme, section="theme")
            theme["theme_path"] = theme_path
    config.update(theme)
    return config, gen_config, error


def convert_keybindings(keybindings):
    """Convert keybinding codes to os-specific codes"""
    if sys.platform == "win32":   # windows has different codes for Alt+Key
        for key, value in keybindings.items():
            if isinstance(value, str):
                keybindings[key] = re.sub(r"ALT\+(\d+)", lambda m: str(int(m.group(1)) + 320), value)
    elif os.environ.get("TERM", "") == "xterm":   # xterm has different codes for Alt+Key
        # for ALT+Key it actually sends 195 then Key+64
        # but this is simpler since key should already be uniquely shifted
        for key, value in keybindings.items():
            if isinstance(value, str):
                val = re.sub(r"ALT\+(\d+)", lambda m: str(int(m.group(1)) + 64), value)
                try:
                    val = int(val)
                except ValueError:
                    pass
                keybindings[key] = val
    return keybindings


def update_config(config, key, value):
    """Update and save config"""
    if not value:
        value = ""
    else:
        try:
            value = literal_eval(value)
        except ValueError:
            pass
    config[key] = value
    config_path = config["config_path"]
    saved_config = ConfigParser(interpolation=None)
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            saved_config.read_file(f)
    new_config = {}
    new_theme = {}
    # split config and theme
    for key_all, value_all in config.items():
        if key_all in defaults.settings:
            new_config[key_all] = value_all
        elif key_all in defaults.theme:
            new_theme[key_all] = value_all
    save_config(config_path, new_config, "main")
    save_config(config_path, new_theme, "theme")
    return config


def collapseuser(path):
    """Opposite of os.path.expanduser()"""
    home = os.path.expanduser("~")
    abs_path = os.path.abspath(path)
    home = os.path.abspath(home)
    if abs_path.startswith(home):
        return "~" + abs_path[len(home):]
    return path


def detect_runtime():
    """Detect if code is running from source, pyinstaller or nuitka binary"""
    if hasattr(sys, "_MEIPASS"):
        return "pyinstaller"
    if "__compiled__" in globals():
        return "nuitka"
    if getattr(sys, "frozen", False):
        return "unknown"
    return "source"


def notify_send(title, message, sound="message", custom_sound=None):
    """Send simple notification containing title and message. Cross platform."""
    if sys.platform == "linux":
        if custom_sound:
            threading.Thread(target=play_audio, daemon=True, args=(custom_sound, )).start()
            include_sound = []
        elif no_notify_sound and fallback_notification_sound and have_notify_send:
            threading.Thread(target=play_audio, daemon=True, args=(fallback_notification_sound, )).start()
            include_sound = []
        else:
            include_sound = ["-h", f"string:sound-name:{sound}"]
        if have_notify_send:
            command = ["notify-send", "-p", "--app-name", APP_NAME, *include_sound, title, message]
            proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            return int(proc.communicate()[0].decode().strip("\n"))   # return notification id
        return None
    if sys.platform == "win32":
        if custom_sound:
            threading.Thread(target=play_audio, daemon=True, args=(custom_sound, )).start()
        notification = Toast()
        notification.text_fields = [message]
        toaster.show_toast(notification)
    elif sys.platform == "darwin":
        if custom_sound:
            threading.Thread(target=play_audio, daemon=True, args=(custom_sound, )).start()
        command = ["osascript", "-e", f"'display notification \"{message}\" with title \"{title}\"'"]
        _ = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return None


def notify_remove(notification_id):
    """Removes notification by its id. Linux only."""
    if sys.platform == "linux" and have_gdbus:
        command = ["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications", "--object-path", "/org/freedesktop/Notifications", "--method", "org.freedesktop.Notifications.CloseNotification", str(notification_id)]
        _ = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def load_json(file):
    """Load saved json from same location where default config is saved"""
    path = os.path.expanduser(config_path + file)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(data, file):
    """Save json to same location where default config is saved"""
    if not os.path.exists(config_path):
        os.makedirs(os.path.expanduser(config_path), exist_ok=True)
    path = os.path.expanduser(config_path + file)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def copy_to_clipboard(text):
    """Copy text to clipboard. Cross-platform."""
    text = str(text)
    if sys.platform == "linux":
        if os.getenv("WAYLAND_DISPLAY"):
            try:
                proc = subprocess.Popen(
                    ["wl-copy"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
                proc.communicate(input=text.encode("utf-8"))
            except FileNotFoundError:
                logger.warn("Cant copy: wl-copy not found on system")
        else:
            try:
                proc = subprocess.Popen(
                    ["xclip"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
                proc.communicate(input=text.encode("utf-8"))
            except FileNotFoundError:
                logger.warn("Cant copy: xclip not found on system")
    elif sys.platform == "win32":
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text)
        win32clipboard.CloseClipboard()
    elif sys.platform == "darwin":
        proc = subprocess.Popen(
            ["pbcopy", "w"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        proc.communicate(input=text.encode("utf-8"))


def get_file_size(path):
    """Get file size in bytes"""
    return os.stat(path).st_size


def get_is_clip(path):
    """Get whether file is video or not"""
    return magic.from_file(path, mime=True).split("/")[0] == "video"


def get_can_play(path):
    """Get wether file can be played as media"""
    return magic.from_file(path, mime=True).split("/")[0] in ("image", "video", "audio")


def complete_path(path, separator=True):
    """Get possible completions for path"""
    if not path:
        return []
    path = os.path.expanduser(path)
    completions = []
    for path in glob.glob(path + "*"):
        if separator and path and os.path.isdir(path) and path[-1] != "/":
            completions.append(path + "/")
        else:
            completions.append(path)
    return sorted(completions)


def play_audio(path):
    """Play audio file with soundcard"""
    if have_sound:
        data, samplerate = soundfile.read(path, dtype="float32")
        speaker.play(data, samplerate=samplerate)


def get_audio_waveform(path):
    """Get audio file waveform and length"""
    if not os.path.exists(path):
        return None, None
    with soundfile.SoundFile(path) as audio_file:
        data = audio_file.read()
        if data.ndim > 1:
            data = data[:, 0]   # select only one stream
        duration = len(data) / audio_file.samplerate
        chunk_num = min(max(int(duration * 10), 32), 256)
        chunk_size = int(len(data) / chunk_num)
        reshaped = data[:len(data) - len(data) % chunk_size].reshape(-1, chunk_size)
        rms_samples = np.sqrt(np.mean(reshaped**2, axis=1))
        normalized = (rms_samples / rms_samples.max()) * 255
        waveform = base64.b64encode(normalized.astype(np.uint8)).decode("utf-8")
    return waveform, duration


def native_open(path, mpv_path=""):
    """Open media file in native application, cross-system"""
    if not path:
        return
    if path.startswith("https://") and "youtu" in path:
        if mpv_path:
            current_runner = mpv_path
        else:
            webbrowser.open(path, new=0, autoraise=True)
    else:
        current_runner = runner
    _ = subprocess.Popen(
        [current_runner, path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def find_aspell():
    """Find aspell exe path on windows system"""
    if sys.platform == "linux":
        if shutil.which("aspell"):
            return "aspell"
        return None
    if sys.platform == "win32":
        aspell_path = None
        for name in os.listdir("C:\\Program Files (x86)\\"):
            if "Aspell" in name:
                aspell_path = os.path.join("C:\\Program Files (x86)\\", name, "bin\\aspell.exe")
                if not os.path.exists(aspell_path):
                    aspell_path = None
                break
        return aspell_path
    logger.info("Spellchecking not supported on this platform")


class SpellCheck():
    """Sentence and word spellchecker"""

    def __init__(self, aspell_mode, aspell_language):
        self.aspell_mode = aspell_mode
        self.aspell_language = aspell_language
        self.enable = False
        self.command = ["aspell", "-a", f"--sug-mode={aspell_mode}", f"--lang={aspell_language}"]
        if aspell_mode:
            aspell_path = find_aspell()
            if aspell_path:
                self.aspell_path = aspell_path
                self.enable = True
                self.start_aspell()
            else:
                logger.info("Spellchecking disabled: Aspell not found")
        else:
            logger.info("Spellchecking disabled in config")


    def start_aspell(self):
        """Start aspell with selected mode and language"""
        # cross platform replacement for pexpect.spawn() because aspell works with it
        self.proc = pexpect.popen_spawn.PopenSpawn(f"{self.aspell_path} -a --sug-mode={self.aspell_mode} --lang={self.aspell_language}", encoding="utf-8")
        self.proc.delaybeforesend = None
        try:
            self.proc.expect("Ispell", timeout=0.5)
            logger.info("Aspell initialized")
        except pexpect.exceptions.EOF:
            logger.info("Aspell initialization error")
            self.enable = False


    def check_word_pexpect(self, word):
        """Spellcheck single word with aspell"""
        try:
            self.proc.sendline(word)
            self.proc.expect(r"\*|\&|\#", timeout=ASPELL_TIMEOUT)
            after = self.proc.after
            if after in ("&", "#"):
                return True
            return False
        except pexpect.exceptions.TIMEOUT:
            return True   # if timed-out return it as correct
        except pexpect.exceptions.EOF as e:
            logger.info(e)
            if self.enable:
                self.start_aspell()
                return False


    def check_word_subprocess(self, word):
        """Spellcheck single word with aspell"""
        try:
            proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            output, error = proc.communicate(word.encode())
            check = output.decode().split("\n")[1]
            if check == "*":
                return False
            return True
        except FileNotFoundError:   # aspell not installed
            return False


    def check_sentence(self, sentence):
        """
        Spellcheck a sentence with aspell.
        Excluding last word if there is no space after it.
        Return list of bools representing whether each word is misspelled or not.
        """
        misspelled = []
        if self.enable:
            for word in re.split(match_split, sentence):
                if word == "":
                    misspelled.append(False)
                else:
                    misspelled.append(self.check_word_pexpect(word))
        return misspelled


    def check_list(self, words):
        """
        Spellcheck a a list of words with aspell.
        Return list of bools representing whether each word is misspelled or not.
        """
        misspelled = []
        if self.enable:
            for word in words:
                if word == "":
                    misspelled.append(False)
                else:
                    # regex here might cause troubles with non-latin characters
                    misspelled.append(self.check_word_pexpect(re.sub(match_first_non_alfanumeric, "", word)))
        else:
            return [False] * len(words)
        return misspelled


class Recorder():
    """Sound recorder"""

    def __init__(self):
        self.recording = False
        self.audio_data = []


    def record(self):
        """Continuously record audio"""
        timer = 0
        try:
            mic = soundcard.default_microphone()
        except Exception as e:
            logger.warn(f"No microphone found. Error: {e}")
            self.recording = False
            return
        with mic.recorder(samplerate=48000, channels=1) as rec:
            while self.recording:
                if timer >= 600:   # 10min limit
                    del self.audio_data
                    self.recording = False
                    break
                data = rec.record(numframes=48000)
                self.audio_data.append(data)
                timer += 1


    def start(self):
        """Start continuously recording audio"""
        if not self.recording:
            self.recording = True
            self.audio_data = []
            self.record_thread = threading.Thread(target=self.record, daemon=True)
            self.record_thread.start()


    def stop(self):
        """Stop recording audio and return file path"""
        if self.recording:
            self.recording = False
            self.record_thread.join()
            self.audio_data = np.concatenate(self.audio_data, axis=0)
            save_path = os.path.join(temp_path, "rec-audio-message.ogg")
            soundfile.write(save_path, self.audio_data, 48000, format="OGG", subtype="OPUS")
            del self.audio_data
            return save_path
