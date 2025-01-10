import curses
import logging
import os
import signal
import sys

from endcord import app, arg, defaults, peripherals

APP_NAME = "endcord"
VERSION = "0.4.0"
default_config_path = peripherals.default_config_path
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
    token = args.token
    logger.info(f"Started endcord {VERSION}")
    if not config_path:
        if not os.path.exists(default_config_path + "config.ini"):
            logger.info("Using default config")
        config_path = default_config_path + "config.ini"
    config = peripherals.load_config(config_path, defaults.settings)
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
