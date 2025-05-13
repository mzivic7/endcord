import curses
import sys

message = """ Press key combination, its code wil be printed in terminal.
 Use this code to set this key combination in config.ini keybinding section.
 Some key combinations are reserved by terminal: Ctrl+ C/I/J/M/Q/S/Z.
 Ctrl+Shift+Key combinations are not supported, but Alt+Shift+Key are.
 Ctrl+C to exit."""


def picker_internal(screen, keybindings):
    """Keybinding picker, prints last pressed key combination"""
    curses.use_default_colors()
    curses.curs_set(0)
    curses.init_pair(1, -1, -1)
    screen.bkgd(" ", curses.color_pair(1))
    screen.addstr(1, 0, message)
    keybindings = {key: (val,) if not isinstance(val, tuple) else val for key, val in keybindings.items()}
    while True:
        key_code = screen.getch()
        if key_code == 27:   # escape sequence, when ALT+KEY is pressed
            screen.nodelay(True)
            key_code_2 = screen.getch()   # key pressed with ALT
            screen.nodelay(False)
            if key_code_2 != -1:
                key_code = "ALT+" + str(key_code_2)

        text = f"Keybinding code: {str(key_code)}"
        warning = ""
        for key, value in keybindings.items():
            if key_code in value:
                warning = f'Warning: same keybinding as "{key}"'
                break
        _, w = screen.getmaxyx()
        screen.addstr(7, 1, text + " " * (w - len(text)))
        screen.addstr(8, 1, warning + " " * (w - len(warning)))
        screen.refresh()


def picker(keybindings):
    """Keybinding picker, prints last pressed key combination"""
    try:
        curses.wrapper(picker_internal, keybindings)
    except curses.error as e:
        if str(e) != "endwin() returned ERR":
            sys.exit("Curses error")
    sys.exit(0)
