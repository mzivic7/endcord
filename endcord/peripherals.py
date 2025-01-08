import json
import os
import platform
import subprocess
import sys
from ast import literal_eval
from configparser import ConfigParser

APP_NAME = "endcord"


platform_release = str(platform.release())
if sys.platform == "win32":
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
elif sys.platform == "win32":
    default_config_path = f"{os.environ["USERPROFILE"]}/AppData/Local/{APP_NAME}/"
    log_path = f"{os.environ["USERPROFILE"]}/AppData/Local/{APP_NAME}/"
elif sys.platform == "mac":
    default_config_path = f"~/Library/Application Support/{APP_NAME}/"
    log_path = f"~/Library/Application Support/{APP_NAME}/"
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
    """Send simple notification containing title and message. Supports Linux, Windows and Mac."""
    if sys.platform == "linux":
        cmd = f"notify-send -p --app-name '{APP_NAME}' -h 'string:sound-name:{sound}' '{title}' '{message}'"
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
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
    """Removes notification by its id. Linux only"""
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
    )
