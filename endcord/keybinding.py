import curses
import sys

message = """ Press key combination, its code wil be printed in terminal.
 Use this code to set this key combination in config.ini keybinding section.
 Some key combinations are reserved by terminal: Ctrl+ C/I/J/M/Q/S/Z"""

def picker_internal(screen):
    """Keybinding picker, prints last pressed key combination"""
    global key_code
    curses.use_default_colors()
    curses.init_pair(1, -1, -1)
    screen.bkgd(" ", curses.color_pair(1))
    screen.addstr(1, 0, message)
    key_code = screen.getch()

def picker():
    """Keybinding picker, prints last pressed key combination"""
    global key_code
    curses.wrapper(picker_internal)
    print(f"Keybinding code: {key_code}")
    sys.exit(0)
