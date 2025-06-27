import curses
import importlib.util
import logging
import os
import signal
import sys
import traceback

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"   # fix for https://github.com/Nuitka/Nuitka/issues/3442"

from endcord import arg, defaults, peripherals

APP_NAME = "endcord"
VERSION = "0.9.0"
default_config_path = peripherals.config_path
log_path = peripherals.log_path


if not os.path.exists(log_path):
    os.makedirs(os.path.expanduser(os.path.dirname(log_path)), exist_ok=True)
logger = logging
logging.basicConfig(
    level="INFO",
    filename=os.path.expanduser(f"{log_path}{APP_NAME}.log"),
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
    config_path = args.config
    theme_path = args.theme
    if config_path:
        config_path = os.path.expanduser(config_path)
    config, gen_config, error = peripherals.merge_configs(config_path, theme_path)
    if error:
        sys.exit(error)
    if sys.platform == "win32":
        defaults.keybindings.update(defaults.windows_override_keybindings)
    elif sys.platform == "darwin":
        defaults.keybindings.update(defaults.macos_override_keybindings)
    keybindings = peripherals.load_config(
        config_path,
        defaults.keybindings,
        section="keybindings",
        gen_config=gen_config,
    )
    keybindings = peripherals.convert_keybindings(keybindings)

    os.environ["ESCDELAY"] = "25"   # 25ms
    if os.environ.get("TERM", "") in ("xterm", "linux"):
        os.environ["TERM"] = "xterm-256color"
    if sys.platform == "linux":
        os.environ["SSL_CERT_FILE"] = "/etc/ssl/certs/ca-certificates.crt"

    if args.colors:
        # import here for faster startup
        from endcord import color
        curses.wrapper(color.color_palette)
        sys.exit(0)
    elif args.keybinding:
        from endcord import keybinding
        keybinding.picker(keybindings)
        sys.exit(0)
    elif args.media:
        if not (
            importlib.util.find_spec("PIL") is not None and
            importlib.util.find_spec("av") is not None and
            importlib.util.find_spec("numpy") is not None
        ):
            sys.exit("Ascii media player is not supported")
        from endcord import media
        curses.wrapper(media.ascii_runner, args.media, config, keybindings)
        sys.exit(0)

    if args.proxy:
        config["proxy"] = args.proxy

    from endcord import token_manager
    if args.remove_token:
        token_manager.remove_token()
        sys.exit("Token removed from keyring")
    token = args.token
    logger.info(f"Started endcord {VERSION}")
    if not token and not config["token"]:
        token = token_manager.get_token(force=args.update_token)
        if not token:
            sys.exit("Token not provided in config, as argument, nor in token manager")
    if token:
        config["token"] = token
    if args.debug or config["debug"]:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        from endcord import app
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
