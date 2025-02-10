import curses
import logging
import os
import signal
import sys

from endcord import app, arg, peripherals

APP_NAME = "endcord"
VERSION = "0.7.0"
default_config_path = peripherals.config_path
log_path = peripherals.log_path


if not os.path.exists(log_path):
    os.makedirs(os.path.expanduser(os.path.dirname(log_path)), exist_ok=True)
logger = logging
logging.basicConfig(
    level="INFO",
    filename=os.path.expanduser(log_path + f"{APP_NAME}.log"),
    encoding="utf-8",
    filemode="w",
    format="{asctime} - {levelname}\n  [{module}]: {message}\n",
    style="{",
    datefmt="%Y-%m-%d-%H:%M:%S",
)


def sigint_handler(_signum, _frame):
    """Handling Ctrl-C event"""
    sys.exit(0)


def main(args):
    """Main function"""
    config_path = args.config
    theme_path = args.theme
    if config_path:
        config_path = os.path.expanduser(config_path)
    token = args.token
    logger.info(f"Started endcord {VERSION}")
    config = peripherals.merge_configs(config_path, theme_path)
    if not token and not config["token"]:
        sys.exit(f"Token not provided in config ({config_path}) nor as argument")
    if token:
        config["token"] = token
    if args.debug or config["debug"]:
        logging.getLogger().setLevel(logging.DEBUG)
    curses.wrapper(app.Endcord, config)

if __name__ == "__main__":
    args = arg.parser(APP_NAME, VERSION, default_config_path, log_path)
    signal.signal(signal.SIGINT, sigint_handler)
    main(args)
