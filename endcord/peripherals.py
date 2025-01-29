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

from endcord import defaults

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
        temp_path = f"/run/user/{os.getuid()}/{APP_NAME}"
    path = os.environ.get("XDG_DOWNLOAD_DIR", "")
    if path.strip():
        downloads_path = os.path.join(path, f"{APP_NAME}/")
    else:
        downloads_path = "~/Downloads"
elif sys.platform == "win32":
    config_path = f"{os.environ["USERPROFILE"]}/AppData/Local/{APP_NAME}/"
    log_path = f"{os.environ["USERPROFILE"]}/AppData/Local/{APP_NAME}/"
    temp_path = f"{os.environ["USERPROFILE"]}/AppData/Local/Temp/{APP_NAME}/"
    downloads_path = f"{os.environ["USERPROFILE"]}/Downloads"
elif sys.platform == "mac":
    config_path = f"~/Library/Application Support/{APP_NAME}/"
    log_path = f"~/Library/Application Support/{APP_NAME}/"
    temp_path = f"~/Library/Caches/TemporaryItems{APP_NAME}"
    downloads_path = "~/Downloads"
else:
    sys.exit(f"Unsupported platform: {sys.platform}")


def load_config(path, default, section="main", gen_config=False):
    """
    Load settings and theme from config
    If some value is missing, it is replaced wih default value
    """
    config = ConfigParser(interpolation=None)
    path = os.path.expanduser(path)
    config.read(path)
    if not os.path.exists(path) or gen_config:
        os.makedirs(os.path.expanduser(os.path.dirname(log_path)), exist_ok=True)
        config.add_section(section)
        for key in default:
            if default[key] in (True, False, None) or isinstance(default[key], (list, int, float)):
                config.set(section, key, str(default[key]))
            else:
                config.set(section, key, f'"{str(default[key]).replace("\\", "\\\\")}"')
        with open(path, "w") as f:
            config.write(f)
            if not gen_config:
                print(f"Default config generated at: {path}")
        config_data = default
    else:
        if not config.has_section(section):
            return default
        config_data_raw = config._sections[section]
        config_data = dict.fromkeys(default)
        for key in default:
            if key in list(config[section].keys()):
                try:
                    eval_value = literal_eval(config_data_raw[key])
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
    """Merge config and themes, from varios locations"""
    gen_config = False
    if not custom_config_path:
        if not os.path.exists(os.path.expanduser(config_path) + "config.ini"):
            logger.info("Using default config")
            gen_config = True
        custom_config_path = config_path + "config.ini"
    elif not os.path.exists(os.path.expanduser(custom_config_path)):
        gen_config = True
    config = load_config(custom_config_path, defaults.settings)
    if config["theme"]:
        theme_path = os.path.expanduser(config["theme"])
    saved_themes = get_themes()
    theme = load_config(custom_config_path, defaults.theme, section="theme", gen_config=gen_config)
    if theme_path:
        # if path is only file name without extension
        if os.path.splitext(os.path.basename(theme_path))[0] == theme_path:
            for saved_theme in saved_themes:
                if os.path.splitext(os.path.basename(saved_theme))[0] == theme_path:
                    theme_path = saved_theme
        theme_path = os.path.expanduser(theme_path)
        theme = load_config(theme_path, theme, section="theme")
    config.update(theme)
    return config


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
    path = os.path.expanduser(config_path + "state.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(state):
    """Save state to same location where default config is saved"""
    if not os.path.exists(config_path):
        os.makedirs(os.path.expanduser(config_path), exist_ok=True)
    path = path = os.path.expanduser(config_path + "state.json")
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def check_color(color):
    """Check if color format is valid and repair it"""
    if color is None:
        return [-1, -1]
    if color[0] is None:
        color[0] = -1
    elif color[1] is None:
        color[1] = -1
    return color


def extract_colors(config):
    """Extract simple colors from config if any value is None, default is used"""
    return (
        check_color(config["color_default"]),
        check_color(config["color_chat_mention"]),
        check_color(config["color_chat_blocked"]),
        check_color(config["color_chat_deleted"]),
    )


def check_color_formatted(color_format):
    """
    Check if color format is valid and repair it.
    Replace -2 values for non-default colors with default for this format.
    """
    if color_format is None:
        return [[-1, -1]]
    for color in color_format[1:]:
        if color[0] == -2:
            color[0] = color_format[0][0]
        if color[1] == -2:
            color[1] = color_format[0][1]
    return color_format


def extract_colors_formatted(config):
    """Extract complex formatted colors from config"""
    return (
        check_color_formatted(config["color_format_message"]),
        check_color_formatted(config["color_format_newline"]),
        check_color_formatted(config["color_format_reply"]),
        check_color_formatted(config["color_format_reactions"]),
        # not complex but is here so it can be initialized for alt bg color
        [check_color(config["color_chat_edited"])],
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
