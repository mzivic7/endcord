import os
import sys
import threading
from queue import Queue

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame
import pygame.freetype
import pyperclip
from pygame._sdl2 import Window as pg_Window

WINDOW_SIZE = (800, 500)
MAXIMIZED = True
FONT_SIZE = 12
FONT_NAME = "Source Code Pro"
APP_NAME = "Endcord"

REPEAT_DELAY = 400
REPEAT_INTERVAL = 25
DEFAULT_PAIR = ((255, 255, 255), (0, 0, 0))
SYSTEM_COLORS = (
    (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
    (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
    (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
)

PGCURSES = True
KEY_MOUSE = 409
KEY_BACKSPACE = 263
KEY_DOWN = 258
KEY_UP = 259
KEY_LEFT = 260
KEY_RIGHT = 261
KEY_RESIZE = 419
KEY_DC = 330
KEY_HOME = 262
KEY_END = 360
BUTTON1_PRESSED = 2
BUTTON2_PRESSED = 64
BUTTON3_PRESSED = 2048
BUTTON4_PRESSED = 65536
BUTTON5_PRESSED = 2097152
A_STANDOUT = 65536
A_UNDERLINE = 131072
A_BOLD = 2097152
A_ITALIC = 2147483648
ALL_MOUSE_EVENTS = 268435455
COLORS = 255
COLOR_PAIRS = 1000000

mouse_event = (0, 0, 0, 0, 0)
main_thread_queue = Queue()
color_map = [DEFAULT_PAIR] * (COLORS + 1)


def xterm_to_rgb(x):
    """Convert xterm256 color to RGB tuple"""
    if x < 16:
        return SYSTEM_COLORS[x]
    if 16 <= x <= 231:
        x -= 16
        r = (x // 36) % 6
        g = (x // 6) % 6
        b = x % 6
        return (r * 51, g * 51, b * 51)
    if 232 <= x <= 255:
        gray = 8 + (x - 232) * 10
        return (gray, gray, gray)
    return (0, 0, 0)


def is_emoji(ch):
    """Check if character is emoji"""
    code = ord(ch)
    return (
        0x1F300 <= code <= 0x1F9FF or
        0x2600 <= code <= 0x27BF or
        0x2300 <= code <= 0x23FF or
        0x2B00 <= code <= 0x2BFF
    )


def map_key(event):
    """Map pygame keys to curses codes"""
    key = event.key
    if event.mod & pygame.KMOD_CTRL:   # Ctrl+Key
        if key == pygame.K_DOWN:
            return 534
        if key == pygame.K_UP:
            return 575
        if key == pygame.K_LEFT:
            return 554
        if key == pygame.K_RIGHT:
            return 569
        if key == pygame.K_SPACE:
            return 0
    elif event.mod & pygame.KMOD_SHIFT:   # Shift+Key
        if key == pygame.K_DOWN:
            return 336
        if key == pygame.K_UP:
            return 337
        if key == pygame.K_LEFT:
            return 393
        if key == pygame.K_RIGHT:
            return 402
    elif event.mod & pygame.KMOD_ALT:   # Alt+Key
        if key == pygame.K_DOWN:
            return 532
        if key == pygame.K_UP:
            return 573
        if key == pygame.K_LEFT:
            return 552
        if key == pygame.K_RIGHT:
            return 567
    if key == pygame.K_BACKSPACE:
        return KEY_BACKSPACE
    if key == pygame.K_DOWN:
        return KEY_DOWN
    if key == pygame.K_UP:
        return KEY_UP
    if key == pygame.K_LEFT:
        return KEY_LEFT
    if key == pygame.K_RIGHT:
        return KEY_RIGHT
    if key == pygame.K_DELETE:
        return KEY_DC
    if key == pygame.K_RETURN:
        return 10
    return None


class Window:
    """Pygame-Curses window class"""

    def __init__(self, surface, begy, begx):
        self.surface = surface
        self.begy, self.begx = begy, begx
        self.bgcolor = pygame.Color((0, 0, 0))
        self.input_buffer = []
        self.clock = pygame.time.Clock()
        self.nodelay_state = False

        if sys.platform == "win32":
            emoji_font_name = "Segoe UI Emoji"
        elif sys.platform == "darwin":
            emoji_font_name = "Apple Color Emoji"
        else:
            emoji_font_name = "Noto Color Emoji"

        self.base_font_path = pygame.font.match_font(FONT_NAME)
        self.font = pygame.freetype.Font(self.base_font_path, FONT_SIZE)
        self.emoji_font = pygame.font.SysFont(emoji_font_name, FONT_SIZE)
        self.font.pad = True

        rect = self.font.get_rect(" ")
        self.char_width, self.char_height = rect.width, rect.height
        self.ncols = surface.get_width()  // self.char_width
        self.nlines = surface.get_height() // self.char_height

        self.held_key_event = None
        self.held_key_time = 0
        self.next_key_repeat_time = 0

        self.buffer = [[(" ", 0) for _ in range(self.ncols)]for _ in range(self.nlines)]
        self.dirty_lines = set()


    def derwin(self, nlines, ncols, begy, begx):
        """curses.derwin clone using pygame"""
        pixel_width = ncols * self.char_width
        pixel_height = nlines * self.char_height
        pixel_x = begx * self.char_width
        pixel_y = begy * self.char_height
        subsurface = self.surface.subsurface((pixel_x, pixel_y, pixel_width, pixel_height))
        return Window(subsurface, begy, begx)


    def getmaxyx(self):
        """curses.getmaxyx clone using pygame"""
        return (self.nlines, self.ncols)


    def getbegyx(self):
        """curses.getbegyx clone using pygame"""
        return (self.begy, self.begx)


    def render_emoji_scaled(self, ch):
        """Render emoji character to a scaled surface to fit character cell."""
        try:
            surf = self.emoji_font.render(ch, True, (255, 255, 255))
            return pygame.transform.smoothscale(surf, (self.char_height, self.char_height))
        except pygame.error:
            return None


    def insstr(self, y, x, text, attr=0):
        """curses.insstr clone using pygame"""
        lines = text.split("\n")
        len_lines = len(lines)
        for i, line in enumerate(lines):
            if i < len_lines - 1:
                line_len = self.ncols - x
                ready_line = (line[:line_len]).ljust(line_len)
            else:
                ready_line = line
            row = y + i
            if row >= self.nlines:
                break
            row_buffer = self.buffer[row]
            for j, ch in enumerate(ready_line[:self.ncols - x]):
                col = x + j
                row_buffer[col] = (ch, attr)
            self.dirty_lines.add(row)


    def insch(self, y, x, ch, color_id=0):
        """curses.insch clone using pygame, takes color id"""
        self.insstr(y, x, ch, color_id)


    def addstr(self, y, x, text, color_id=0):
        """curses.addstr clone using pygame, takes color id"""
        self.insstr(y, x, text, color_id)
        main_thread_queue.put(self.render)
        self.refresh()


    def addch(self, y, x, ch, color_id=0):
        """curses.addch clone using pygame, takes color id"""
        self.insstr(y, x, ch, color_id)


    def hline(self, y, x, ch, n, attr=0):
        """curses.hline clone using pygame, takes color id"""
        self.insstr(y, x, ch * n, attr)


    def vline(self, y, x, ch, n, attr=0):
        """curses.vline clone using pygame, takes color id"""
        for i in range(n):
            self.insch(y + i, x, ch, attr)


    def render(self):
        """Render buffer onto screen"""
        for y in self.dirty_lines:
            row = self.buffer[y]
            i = 0
            draw_x = 0
            while i < self.ncols:
                ch, attr = row[i]
                flags = attr & 0xFFFF0000

                if is_emoji(ch):
                    px_x = draw_x * self.char_width
                    px_y = y * self.char_height
                    fg, bg = color_map[attr & 0xFFFF]
                    if flags & A_STANDOUT:
                        fg, bg = bg, fg
                    self.surface.fill(bg, (px_x, px_y, 2 * self.char_width, self.char_height))
                    emoji = self.render_emoji_scaled(ch)
                    if emoji:
                        offset = px_x + (2 * self.char_width - self.char_height) // 2
                        self.surface.blit(emoji, (offset, px_y))
                    draw_x += 2   # emoji takes two cells visually
                    i += 1   # but only one buffer cell
                    continue

                span_draw_x = draw_x
                text_buffer = []
                while i < self.ncols:
                    ch, attr2 = row[i]
                    if attr2 != attr:
                        break
                    if is_emoji(ch):
                        break
                    text_buffer.append(ch)
                    i += 1
                    draw_x += 1
                if not text_buffer:
                    continue
                text = "".join(text_buffer)

                fg, bg = color_map[attr & 0xFFFF]
                if flags & A_STANDOUT:
                    fg, bg = bg, fg
                px_x = span_draw_x * self.char_width
                px_y = y * self.char_height
                self.surface.fill(bg, (px_x, px_y, len(text) * self.char_width, self.char_height))
                self.font.strong = bool(flags & A_BOLD)
                self.font.oblique = bool(flags & A_ITALIC)
                self.font.underline = bool(flags & A_UNDERLINE)
                self.font.render_to(self.surface, (px_x, px_y), text, fg)

        self.dirty_lines.clear()


    def clear(self):
        """curses.clear clone using pygame"""
        self.surface.fill(self.bgcolor)


    def refresh(self):
        """curses.refresh clone using pygame"""
        main_thread_queue.put(pygame.display.update)


    def redrawwin(self):
        """curses.redrawwin clone using pygame"""
        main_thread_queue.put(self.render)


    def noutrefresh(self):
        """curses.noutrefresh clone using pygame"""
        main_thread_queue.put(self.render)


    def bkgd(self, ch, color_id):
        """curses.bkgd clone using pygame"""
        ch = str(ch)[0]
        fg_color, bg_color = color_map[color_id]
        for y in range(self.nlines):
            for x in range(self.ncols):
                px_x = x * self.char_width
                px_y = y * self.char_height
                self.font.render_to(self.surface, (px_x, px_y), ch, fg_color, bg_color)


    def nodelay(self, flag: bool):
        """curses.nodelay clone using pygame"""
        self.nodelay_state = flag


    def do_key_press(self, event, mods):
        """Map pygame keys to curses codes"""
        key = event.key
        char = event.unicode or ""

        if event.mod & pygame.KMOD_SHIFT and key == pygame.K_RETURN:
            self.input_buffer.extend(b"\n")
            return 27
        if key == pygame.K_c and (event.mod & pygame.KMOD_CTRL):
            main_thread_queue.put(None)
            return -1
        if key == pygame.K_ESCAPE and not char:
            return 27

        if mods & pygame.KMOD_CTRL:
            if char and char.isalpha():
                return ord(char.lower()) - ord("a") + 1
            if char:
                return ord(char)

        if mods & pygame.KMOD_ALT and char:
            self.input_buffer.extend(char.encode("utf-8"))
            return 27

        if char:
            self.input_buffer.extend(char.encode("utf-8"))
            return None

        return None


    def getch(self):
        """curses.getch clone using pygame"""
        global mouse_event

        if self.input_buffer:
            return self.input_buffer.pop(0)

        while True:
            events = pygame.event.get()
            current_time = pygame.time.get_ticks()
            for event in events:
                if event.type == pygame.QUIT:
                    main_thread_queue.put(None)
                    return -1

                if event.type == pygame.KEYDOWN:
                    mods = pygame.key.get_mods()
                    if (
                        event.key == pygame.K_v and
                        (mods & pygame.KMOD_CTRL) and
                        (mods & pygame.KMOD_SHIFT)
                    ):
                        pasted = pyperclip.paste()
                        if pasted:   # bracket pasting
                            bracketed = "\x1b[200~" + pasted + "\x1b[201~"
                            self.input_buffer.extend(bracketed.encode("utf-8"))
                        return -1

                    self.held_key_event = event
                    self.held_key_time = current_time
                    self.next_key_repeat_time = current_time + REPEAT_DELAY
                    code = self.do_key_press(event, mods)
                    if code is not None:
                        return code

                elif event.type == pygame.KEYUP:
                    self.held_key_event = None

                elif event.type == pygame.VIDEORESIZE:
                    return KEY_RESIZE

                if event.type == pygame.MOUSEBUTTONDOWN:
                    btnstate = 0
                    if event.button == 1:
                        btnstate = BUTTON1_PRESSED
                    elif event.button == 2:
                        btnstate = BUTTON2_PRESSED
                    elif event.button == 3:
                        btnstate = BUTTON3_PRESSED
                    elif event.button == 4:
                        btnstate = BUTTON4_PRESSED
                    elif event.button == 5:
                        btnstate = BUTTON5_PRESSED
                    x_pixel, y_pixel = event.pos
                    mouse_event = (0, x_pixel // self.char_width, y_pixel // self.char_height, 0, btnstate)
                    return KEY_MOUSE

            if self.held_key_event is not None and current_time >= self.next_key_repeat_time:
                self.next_key_repeat_time += REPEAT_INTERVAL
                mods = pygame.key.get_mods()
                code = self.do_key_press(self.held_key_event, mods)
                if code is not None:
                    return code

            if self.input_buffer:
                return self.input_buffer.pop(0)

            if self.held_key_event is not None and current_time >= self.next_key_repeat_time:
                self.next_key_repeat_time += REPEAT_INTERVAL
                mods = pygame.key.get_mods()
                code = self.do_key_press(self.held_key_event, mods)
                if code is not None:
                    return code

            if self.nodelay_state:
                return -1

            self.clock.tick(60)



def getmouse():
    """curses.getmouse clone using pygame"""
    return mouse_event


def initscr():
    """curses.initscr clone using pygame"""
    pygame.display.init()
    pygame.font.init()
    pygame.freetype.init()
    pygame.display.set_caption(APP_NAME)
    screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
    if MAXIMIZED:
        win = pg_Window.from_display_module()
        win.maximize()
    return Window(screen, 0, 0)


def wrapper(func, *args, **kwargs):
    """curses.wrapper clone using pygame"""
    screen = initscr()

    def user_thread():
        func(screen, *args, **kwargs)
        main_thread_queue.put(None)
    threading.Thread(target=user_thread, daemon=True).start()

    run = True
    while run:
        task = main_thread_queue.get()
        if not task:
            break
        task()

    pygame.quit()


def doupdate():
    """curses.doupdate clone using pygame"""
    main_thread_queue.put(pygame.display.update)


def init_pair(pair_id, fg, bg):
    """curses.init_pair clone using pygame"""
    fg_rgb = DEFAULT_PAIR[0] if fg <= 0 else xterm_to_rgb(fg)
    bg_rgb = DEFAULT_PAIR[1] if bg <= 0 else xterm_to_rgb(bg)
    if pair_id >= len(color_map):
        missing = pair_id + 1 - len(color_map)
        color_map.extend([DEFAULT_PAIR] * missing)
    color_map[pair_id] = (fg_rgb, bg_rgb)



class error(Exception):   # noqa
    """curses.error clone using pygame, only inherits Exception class"""
    pass


def color_pair(color_id):
    """curses.color_pair clone using pygame, returns color id"""
    return color_id

def start_color():
    """curses.start_color clone using pygame, does nothing"""
    pass

def use_default_colors():
    """curses.use_default_colors clone using pygame, does nothing"""
    pass

def curs_set(x):
    """curses.curs_set clone using pygame, does nothing"""
    pass

def mousemask(x):
    """curses.mousemask clone using pygame, does nothing"""
    pass

def mouseinterval(x):
    """curses.mouseinterval clone using pygame, does nothing"""
    pass

def nocbreak():
    """curses.nocbreak clone using pygame, does nothing"""
    pass

def echo():
    """curses.echo clone using pygame, does nothing"""
    pass

def endwin():
    """curses.endwin clone using pygame"""
    pass

def def_prog_mode():
    """curses.def_prog_mode clone using pygame"""
    pass

def reset_prog_mode():
    """curses.reset_prog_mode clone using pygame"""
    pass


ACS_ULCORNER = "┌"
ACS_LLCORNER = "└"
ACS_URCORNER = "┐"
ACS_LRCORNER = "┘"
ACS_LTEE = "├"
ACS_RTEE = "┤"
ACS_BTEE = "┴"
ACS_TTEE = "┬"
ACS_HLINE = "─"
ACS_VLINE = "│"
ACS_PLUS = "┼"
ACS_S1 = "⎺"
ACS_S3 = "⎻"
ACS_S7 = "⎼"
ACS_S9 = "⎽"
ACS_DIAMOND = "◆"
ACS_DEGREE = "°"
ACS_PLMINUS = "±"
ACS_BULLET = "·"
ACS_LARROW = "←"
ACS_RARROW = "→"
ACS_DARROW = "↓"
ACS_UARROW = "↑"
ACS_BOARD = "▒"
ACS_LANTERN = "␋"
ACS_BLOCK = "▮"
ACS_LEQUAL = "≤"
ACS_GEQUAL = "≥"
ACS_PI = "π"
ACS_NEQUAL = "≠"
ACS_STERLING = "£"
