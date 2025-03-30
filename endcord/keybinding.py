import curses
import sys

message = """ Press key combination, its code wil be printed in terminal.
 Use this code to set this key combination in config.ini keybinding section.
 Some key combinations are reserved by terminal: Ctrl+ C/I/J/M/Q/S/Z.
 Ctrl+Shift+Key combinations are not supported, but Alt+Shift+Key are."""

def picker_internal(screen):
    """Keybinding picker, prints last pressed key combination"""
    global key_code
    curses.use_default_colors()
    curses.init_pair(1, -1, -1)
    screen.bkgd(" ", curses.color_pair(1))
    screen.addstr(1, 0, message)
    key_code = screen.getch()
    if key_code == 27:   # escape sequence, when ALT+KEY is pressed
        screen.nodelay(True)
        key_code_2 = screen.getch()   # key pressed with ALT
        screen.nodelay(False)
        if key_code_2 != -1:
            key_code = "ALT+" + str(key_code_2)

def picker():
    """Keybinding picker, prints last pressed key combination"""
    global key_code
    curses.wrapper(picker_internal)
    print(f"Keybinding code: {key_code}")
    sys.exit(0)
