import glob
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
from ast import literal_eval
from configparser import ConfigParser

import magic
import pexpect

logger = logging.getLogger(__name__)
match_first_non_alfanumeric = re.compile(r"^[^\w_]*")
APP_NAME = "endcord"


platform_release = str(platform.release())
if sys.platform == "win32":
    import win32clipboard
    if platform_release == "10":
        from win10toast import ToastNotifier
        toast = ToastNotifier()
    elif platform_release == "11":
        import win11toast



if sys.platform == "linux":
    path = os.environ.get("XDG_DATA_HOME", "")
    if path.strip():
        default_config_path = os.path.join(path, f"{APP_NAME}/")
        log_path = os.path.join(path, f"{APP_NAME}/")
    else:
        default_config_path = f"~/.config/{APP_NAME}/"
        log_path = f"~/.config/{APP_NAME}/"
    path = os.environ.get("XDG_RUNTIME_DIR", "")
    if path.strip():
        temp_path = os.path.join(path, f"{APP_NAME}/")
    else:
        # per-user temp dir
        temp_path = f"/run/user/{os.getuid()}/{APP_NAME}"
    path = os.environ.get("XDG_DOWNLOAD_DIR", "")
    if path.strip():
        downloads_path = os.path.join(path, f"{APP_NAME}/")
    else:
        downloads_path = "~/Downloads"
elif sys.platform == "win32":
    default_config_path = f"{os.environ["USERPROFILE"]}/AppData/Local/{APP_NAME}/"
    log_path = f"{os.environ["USERPROFILE"]}/AppData/Local/{APP_NAME}/"
    temp_path = f"{os.environ["USERPROFILE"]}/AppData/Local/Temp/{APP_NAME}/"
    downloads_path = f"{os.environ["USERPROFILE"]}/Downloads"
elif sys.platform == "mac":
    default_config_path = f"~/Library/Application Support/{APP_NAME}/"
    log_path = f"~/Library/Application Support/{APP_NAME}/"
    temp_path = f"~/Library/Caches/TemporaryItems{APP_NAME}"
    downloads_path = "~/Downloads"
else:
    sys.exit(f"Unsupported platform: {sys.platform}")


def load_config(path, default):
    """
    Load settings from config
    If some value is missing, it is replaced wih default value
    """
    config = ConfigParser(interpolation=None)
    path = os.path.expanduser(path)
    config.read(path)
    if not os.path.exists(path):
        os.makedirs(os.path.expanduser(os.path.dirname(log_path)), exist_ok=True)
        config.add_section("main")
        for key in default:
            if default[key] in (True, False, None) or isinstance(default[key], int):
                config.set("main", key, str(default[key]))
            else:
                config.set("main", key, f'"{str(default[key]).replace("\\", "\\\\")}"')
        with open(path, "w") as f:
            config.write(f)
            print(f"Default config generated at: {path}")
        config_data = default
    else:
        config_data_raw = config._sections["main"]
        config_data = dict.fromkeys(default)
        for key in default:
            if key in list(config["main"].keys()):
                try:
                    eval_value = literal_eval(config_data_raw[key])
                    config_data[key] = eval_value
                except ValueError:
                    config_data[key] = config_data_raw[key]
            else:
                config_data[key] = default[key]
    return config_data


def notify_send(title, message, sound="message"):
    """Send simple notification containing title and message. Cross platform."""
    if sys.platform == "linux":
        command = ["notify-send", "-p", "--app-name", APP_NAME, "-h", f"string:sound-name:{sound}", title, message]
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return int(proc.communicate()[0].decode().strip("\n"))   # return notification id
    if sys.platform == "win32":
        if platform_release == "10":
            toast.show_toast(title, message, threaded=True)
        elif platform_release == "11":
            win11toast.toast(title, message)
    elif sys.platform == "mac":
        cmd = f"osascript -e 'display notification \"{message}\" with title \"{title}\"'"
        subprocess.Popen(cmd, shell=True)
    return None


def notify_remove(notification_id):
    """Removes notification by its id. Linux only."""
    if sys.platform == "linux":
        cmd = f"gdbus call --session \
                           --dest org.freedesktop.Notifications \
                           --object-path /org/freedesktop/Notifications \
                           --method org.freedesktop.Notifications.CloseNotification \
                           {notification_id}"
        subprocess.Popen(cmd, shell=True)


def load_state():
    """Load saved states from same location where default config is saved"""
    path = os.path.expanduser(default_config_path + "state.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(state):
    """Save state to same location where default config is saved"""
    if not os.path.exists(default_config_path):
        os.makedirs(os.path.expanduser(default_config_path), exist_ok=True)
    path = path = os.path.expanduser(default_config_path + "state.json")
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def check_color_format(color_format):
    """Check if color format is valid, and repair it"""
    if color_format is None:
        color_format = [-1, -1]
    elif color_format[0] is None:
        color_format[0] = -1
    elif color_format[1] is None:
        color_format[1] = -1
    return color_format


def extract_colors(config):
    """Extract color format from config if any value is None, default is used"""
    return (
        check_color_format(config["color_format_default"]),
        check_color_format(config["color_format_mention"]),
        check_color_format(config["color_format_blocked"]),
        check_color_format(config["color_format_deleted"]),
    )

def copy_to_clipboard(text):
    """Copy text to clipboard. Cross-platform."""
    text = str(text)
    if sys.platform == "linux":
        if os.getenv("WAYLAND_DISPLAY"):
            proc = subprocess.Popen(
                ["wl-copy"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            proc.communicate(input=text.encode("utf-8"))
        else:
            proc = subprocess.Popen(
                ["xclip"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            proc.communicate(input=text.encode("utf-8"))
    elif sys.platform == "win32":
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboard(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
    elif sys.platform == "mac":
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
    return completions


class SpellCheck(object):
    """Sentence and word spellchecker. Linux only."""

    def __init__(self, aspell_mode, aspell_language):
        self.aspell_mode = aspell_mode
        self.aspell_language = aspell_language
        self.enable = True
        self.command = ["aspell", "-a", f"--sug-mode={aspell_mode}", f"--lang={aspell_language}"]
        if not aspell_mode or sys.platform != "linux" or not shutil.which("aspell"):
            self.enable = False
            logger.info("Spellchecking disabled")
        else:
            self.start_aspell()


    def start_aspell(self):
        """Start aspell with selected mode and language"""
        self.proc = pexpect.spawn(f"aspell -a --sug-mode={self.aspell_mode} --lang={self.aspell_language}", encoding="utf-8")
        self.proc.delaybeforesend = None
        try:
            self.proc.expect("Ispell", timeout=0.5)
            logger.info("Aspell initialised")
        except pexpect.exceptions.EOF:
            logger.info("Aspell initialization error")
            self.enable = False


    def check_word_pexpect(self, word):
        """Spellcheck single word with aspell"""
        try:
            self.proc.sendline(word)
            self.proc.expect(r"\*|\&|\#", timeout=0.01)
            after = self.proc.after
            if after in ("&", "#"):
                return True
            return False
        except pexpect.exceptions.TIMEOUT:
            return False
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
        Linux only.
        """
        misspelled = []
        if self.enable:
            for word in sentence.split(" "):
                if word == "":
                    misspelled.append(False)
                else:
                    misspelled.append(self.check_word_pexpect(word))
        return misspelled


    def check_list(self, words):
        """
        Spellcheck a a list of words with aspell.
        Return list of bools representing whether each word is misspelled or not.
        Linux only.
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
