import argparse


def parser(app_name, version, default_config_path, log_path):
    """Setup argument parser for CLI"""
    parser = argparse.ArgumentParser(
        prog=app_name,
        description="Feature rich Discord client in terminal using ncurses",
    )
    parser._positionals.title = "arguments"
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        action="store",
        help=f"\
        custom path to config file; If file does not exist, \
        config with defaults will be created; \
        Default config is in {default_config_path}",
    )
    parser.add_argument(
        "-e",
        "--theme",
        type=str,
        action="store",
        help=f"\
        custom path to theme file; If file does not exist, \
        theme from config with defaults will be created; \
        Default config is in {default_config_path}",
    )
    parser.add_argument(
        "-p",
        "--proxy",
        type=str,
        action="store",
        help="\
        proxy URL to use, it must be this format: 'protocol://host:port'; \
        Supported proxy protocols: http, socks5; \
        Be careful, using proxy might make you more suspicious to discord",
    )
    parser.add_argument(
        "-k",
        "--keybinding",
        action="store_true",
        help="activate keybinding mode, will print key combination number in terminal",
    )
    parser.add_argument(
        "-o",
        "--colors",
        action="store_true",
        help="show all available colors and their codes",
    )
    parser.add_argument(
        "-t",
        "--token",
        type=str,
        action="store",
        help="\
        Discord user authentication token, see readme for more info; \
        It is recommended to provide it in token manager that will show only when token is not found in config nor as argument",
    )
    parser.add_argument(
        "--remove-token",
        action="store_true",
        help="Remove token from keyring, if it is saved there",
    )
    parser.add_argument(
        "--update-token",
        action="store_true",
        help="Update token in keyring, works only if token is not provided in config nor as argument",
    )
    parser.add_argument(
        "-m",
        "--media",
        type=str,
        action="store",
        help="\
        local path to media file or youtube url; \
        if provided, will play it without starting endcord discord",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help=f"save extra debug entries in log file; Log is always overwritten and saved to {log_path}",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {version}",
    )
    return parser.parse_args()
