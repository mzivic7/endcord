import curses
import logging
import os
import signal
import sys
import traceback

from endcord import app, arg, color, defaults, keybinding, peripherals

APP_NAME = "endcord"
VERSION = "0.9.0"
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
    try:
        # in case curses.wrapper doesnt restore terminal
        curses.nocbreak()
        curses.echo()
        curses.endwin()
    except curses.error:
        pass
    sys.exit(0)


def main(args):
    """Main function"""
    os.environ["ESCDELAY"] = "25"   # 25ms
    config_path = args.config
    theme_path = args.theme
    if args.keybinding:
        keybinding.picker()
    elif args.colors:
        curses.wrapper(color.show_all_colors)
        sys.exit(0)
    if config_path:
        config_path = os.path.expanduser(config_path)
    token = args.token
    logger.info(f"Started endcord {VERSION}")
    config, gen_config = peripherals.merge_configs(config_path, theme_path)
    if sys.platform == "win32":
        defaults.keybindings.update(defaults.windows_override_keybindings)
    keybindings = peripherals.load_config(
        config_path,
        defaults.keybindings,
        section="keybindings",
        gen_config=gen_config,
    )
    if not token and not config["token"]:
        sys.exit("Token not provided in config nor as argument")
    if token:
        config["token"] = token
    if args.debug or config["debug"]:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        curses.wrapper(app.Endcord, config, keybindings)
    except curses.error as e:
        if str(e) != "endwin() returned ERR":
            logger.error(traceback.format_exc())
            sys.exit("Curses error, see log for more info")
    sys.exit(0)


if __name__ == "__main__":
    args = arg.parser(APP_NAME, VERSION, default_config_path, log_path)
    signal.signal(signal.SIGINT, sigint_handler)
    main(args)
