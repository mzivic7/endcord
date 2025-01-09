import curses
import logging
import threading
import time

logger = logging.getLogger(__name__)
INPUT_LINE_JUMP = 20   # jump size when moving input line


def ctrl(x):
    """Convert character code to ctrl-modified"""
    return x - 96


class TUI():
    """Methods used to draw terminal user interface"""

    def __init__(self, screen, config):
        curses.use_default_colors()
        curses.curs_set(0)   # using custom cursor
        curses.init_pair(1, 255, -1)   # white on default
        curses.init_pair(2, 233, 255)   # black on white
        curses.init_pair(3, config["color_tree_default"][0], config["color_tree_default"][1])
        curses.init_pair(4, config["color_tree_selected"][0], config["color_tree_selected"][1])
        curses.init_pair(5, config["color_tree_muted"][0], config["color_tree_muted"][1])
        curses.init_pair(6, config["color_tree_active"][0], config["color_tree_active"][1])
        curses.init_pair(7, config["color_tree_unseen"][0], config["color_tree_unseen"][1])
        curses.init_pair(8, config["color_tree_mentioned"][0], config["color_tree_mentioned"][1])
        curses.init_pair(9, config["color_tree_active_mentioned"][0], config["color_tree_active_mentioned"][1])
        self.screen = screen
        self.have_title = bool(config["format_title_line_l"])
        self.have_title_tree = bool(config["format_title_tree"])
        self.vert_line = config["tree_vert_line"][0]
        self.tree_width = config["tree_width"]
        self.blink_cursor_on = config["cursor_on_time"]
        self.blink_cursor_off = config["cursor_off_time"]
        if not (self.blink_cursor_on and self.blink_cursor_off):
            self.enable_blink_cursor = False
        else:
            self.enable_blink_cursor = True
        self.prompt = "> "
        self.input_buffer = ""
        self.status_txt_l = ""
        self.status_txt_r = ""
        self.title_txt_l = ""
        self.title_txt_r = ""
        self.title_tree_txt = ""
        self.chat_buffer = []
        self.chat_format = []
        self.tree = []
        self.tree_format = []
        self.tree_clean_len = 0
        self.chat_selected = -1   # hidden selection by defaut
        self.tree_selected = -1
        self.dont_hide_chat_selection = False
        self.tree_selected_abs = -1
        self.chat_index = 0   # chat scroll index
        self.tree_index = 0
        self.tree_format_changed = False
        self.input_index = 0   # index of input cursor
        self.input_line_index = 0   # index of input line, when moving it
        self.cursor_pos = 0
        self.cursor_on = True
        self.deleting_msg = False
        self.replying_msg = False
        self.typing = time.time()
        chat_hwyx = (
            curses.LINES - 2 - int(self.have_title),
            curses.COLS - (self.tree_width + 1),
            int(self.have_title),
            self.tree_width + 1,
        )
        input_line_hwyx = (1, curses.COLS - (self.tree_width + 1), curses.LINES - 1, self.tree_width + 1)
        status_line_hwyx = (1, curses.COLS - (self.tree_width + 1), curses.LINES - 2, self.tree_width + 1)
        tree_hwyx = (
            curses.LINES - int(self.have_title_tree),
            self.tree_width,
            int(self.have_title),
            0,
        )
        self.win_chat = screen.derwin(*chat_hwyx)
        self.win_input_line = screen.derwin(*input_line_hwyx)
        self.win_status_line = screen.derwin(*status_line_hwyx)
        self.win_tree = screen.derwin(*tree_hwyx)
        if self.have_title:
            title_line_yx = (1, curses.COLS - (self.tree_width + 1), 0, self.tree_width + 1)
            self.win_title_line = screen.derwin(*title_line_yx)
            self.title_hw = self.win_title_line.getmaxyx()
        if self.have_title_tree:
            tree_title_line_hwyx = (1, self.tree_width, 0, 0)
            self.win_title_tree = screen.derwin(*tree_title_line_hwyx)
            self.tree_title_hw = self.win_title_tree.getmaxyx()
        self.screen_hw = self.screen.getmaxyx()
        self.chat_hw = self.win_chat.getmaxyx()
        self.status_hw = self.win_status_line.getmaxyx()
        self.input_hw = self.win_input_line.getmaxyx()
        self.tree_hw = self.win_tree.getmaxyx()
        self.redraw_ui()
        if self.enable_blink_cursor:
            self.run = True
            self.blink_cursor_thread = threading.Thread(target=self.blink_cursor, daemon=True, args=())
            self.blink_cursor_thread.start()


    def resize(self):
        """Resize screen area"""
        h, w = self.screen.getmaxyx()
        self.win_tree.mvwin(int(self.have_title), 0)
        self.win_tree.resize(h - int(self.have_title_tree), self.tree_width)
        self.win_input_line.mvwin(h - 1, self.tree_width + 1)
        self.win_input_line.resize(1, w - (self.tree_width + 1))
        self.win_status_line.mvwin(h - 2, self.tree_width + 1)
        self.win_status_line.resize(1, w - (self.tree_width + 1))
        if self.have_title:
            self.win_title_line.mvwin(0, self.tree_width + 1)
            self.win_title_line.resize(1, w - (self.tree_width + 1))
            self.title_hw = self.win_title_line.getmaxyx()
        if self.have_title_tree:
            self.win_title_tree.mvwin(0, 0)
            self.win_title_tree.resize(1, self.tree_width)
            self.tree_title_hw = self.win_title_tree.getmaxyx()
        self.win_chat.mvwin(int(self.have_title), self.tree_width + 1)
        self.win_chat.resize(h - 2 - int(self.have_title), w - (self.tree_width + 1))
        self.screen_hw = self.screen.getmaxyx()
        self.chat_hw = self.win_chat.getmaxyx()
        self.status_hw = self.win_status_line.getmaxyx()
        self.input_hw = self.win_input_line.getmaxyx()
        self.tree_hw = self.win_tree.getmaxyx()
        self.redraw_ui()


    def get_dimensions(self):
        """Return current dimensions for screen objects"""
        return (
            tuple(self.win_chat.getmaxyx()),
            tuple(self.win_tree.getmaxyx()),
        )

    def get_selected(self):
        """Return index of currently selected line and how much text has been scrolled"""
        return self.chat_selected, self.chat_index


    def get_my_typing(self):
        """Return wether it has been typied in past 3s"""
        if time.time() - self.typing > 3:
            return None
        return True


    def get_tree_format(self):
        """Return tree format if it has been changed"""
        if self.tree_format_changed:
            self.tree_format_changed = False
            return self.tree_format
        return None


    def set_selected(self, selected, change_amount=0):
        """Set selected line and text scrolling"""
        logger.info(f"{self.chat_selected}, {selected}")
        if self.chat_selected >= selected:
            up = True
        else:
            up = False
        self.chat_selected = selected
        if self.chat_selected == -1:
            self.chat_index = 0
        elif change_amount and self.chat_index:
            self.chat_index += change_amount
        elif up:
            self.chat_index = max(selected - self.chat_hw[0] + 3, 0)
        else:
            self.chat_index = max(selected - 3, 0)
        self.draw_chat()


    def allow_chat_selected_hide(self, allow):
        """Allow selected line in chat to be none, position -1"""
        self.dont_hide_chat_selection = not(allow)


    def set_tree_select_active(self):
        """Move tree selection to active channel"""
        skipped = 0
        drop_down_skip_guild = False
        drop_down_skip_category = False
        for num, code in enumerate(self.tree_format):
            if code == 1100:
                skipped += 1
                drop_down_skip_guild = False
                continue
            elif code == 1200:
                skipped += 1
                drop_down_skip_category = False
                continue
            elif drop_down_skip_guild or drop_down_skip_category:
                skipped += 1
                continue
            first_digit = code % 10
            if first_digit == 0 and code < 200:
                drop_down_skip_guild = True
            elif first_digit == 0 and code < 300:
                drop_down_skip_category = True
            if (code % 100) // 10 in (4, 5):
                self.tree_selected = num - skipped
                self.tree_index = max(self.tree_selected - self.tree_hw[0] + 3, 0)
                break
        self.draw_tree()


    def redraw_ui(self):
        """Redraw entire ui"""
        self.screen.vline(0, self.tree_hw[1], self.vert_line, self.screen_hw[0])
        if self.have_title and self.have_title_tree:
            self.screen.insch(0, self.tree_hw[1], self.vert_line, curses.color_pair(2))
        self.draw_status_line()
        self.draw_chat()
        self.draw_input_line()
        self.draw_tree()
        if self.have_title:
            self.draw_title_line()
        if self.have_title_tree:
            self.draw_title_tree()


    def draw_status_line(self):
        """Draw status line"""
        h, w = self.status_hw
        status_txt = self.status_txt_l[:w-1]   # limit status text size
        # if there is enough space for right text, add spaces and right text
        if self.status_txt_r and len(status_txt) + len(self.status_txt_r) + 4 < w:
            status_line = status_txt + " " * (w - len(status_txt) - len(self.status_txt_r)) + self.status_txt_r
        else:
            # add spaces to end of line
            status_line = status_txt + " " * (w - len(status_txt))
        self.win_status_line.insstr(0, 0, status_line + "\n", curses.color_pair(2))
        self.win_status_line.refresh()


    def draw_title_line(self):
        """Draw title line, works same as status line"""
        h, w = self.title_hw
        title_txt = self.title_txt_l[:w-1]
        if self.title_txt_r and len(title_txt) + len(self.title_txt_r) + 4 < w:
            title_line = title_txt + " " * (w - len(title_txt) - len(self.title_txt_r)) + self.title_txt_r
        else:
            title_line = title_txt + " " * (w - len(title_txt))
        self.win_title_line.insstr(0, 0, title_line + "\n", curses.color_pair(2))
        self.win_title_line.refresh()


    def draw_title_tree(self):
        """Draw tree title line, works same as status line, but without right text"""
        h, w = self.tree_title_hw
        title_txt = self.title_tree_txt[:w-1]
        title_line = title_txt + " " * (w - len(title_txt))
        self.win_title_tree.insstr(0, 0, title_line + "\n", curses.color_pair(2))
        self.win_title_tree.refresh()


    def draw_input_line(self):
        """Draw text input line"""
        _, w = self.input_hw
        # show only part of line when longer than screen
        start = max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
        end = start + w - 1
        line_text = self.input_buffer[start:end].replace("\n", "␤")
        # cursor
        character = " "
        self.win_input_line.insstr(0, 0, self.prompt)
        len_prompt = len(self.prompt)
        if self.cursor_pos < len(line_text):
            # cursor in the string
            character = line_text[self.cursor_pos]
            self.win_input_line.insstr(0, len_prompt, line_text[len_prompt:self.cursor_pos])
            self.win_input_line.insch(0, self.cursor_pos, character, curses.color_pair(2))
            self.win_input_line.insstr(0, self.cursor_pos+1, line_text[self.cursor_pos+1:] + "\n")
        else:
            # cursor at the end of string
            self.win_input_line.insstr(0, len_prompt, line_text[len_prompt:] + "\n")
            self.win_input_line.insch(0, self.cursor_pos, character, curses.color_pair(2))
        self.win_input_line.refresh()


    def draw_chat(self):
        """Draw text from linebuffer"""
        h, w = self.chat_hw
        # drawing from down to up
        y = h
        chat_format = self.chat_format[self.chat_index:]
        for num, line in enumerate(self.chat_buffer[self.chat_index:]):
            y = h - (num + 1)
            if y < 0 or y >= h:
                break
            if num == self.chat_selected - self.chat_index:
                color = curses.color_pair(2)
            else:
                color = curses.color_pair(chat_format[num][0])
            # filled with spaces so background is drawn all the way
            self.win_chat.insstr(y, 0, line + " " * (w - len(line)) + "\n", color)
        y -= 1
        while y >= 0:
            self.win_chat.insstr(y, 0, "\n", curses.color_pair(1))
            y -= 1
        self.win_chat.refresh()


    def draw_tree(self):
        """Draw channel tree"""
        h, w = self.tree_hw
        # drawinf from top to down
        skipped = 0   # skipping drop-down ends (code 1000)
        drop_down_skip_category = False
        drop_down_skip_guild = False
        drop_down_level = 0
        self.tree_clean_len = 0
        y = 0
        for num, line in enumerate(self.tree):
            code = self.tree_format[num]
            first_digit = (code % 10)
            if code == 1100:
                skipped += 1
                drop_down_level -= 1
                drop_down_skip_guild = False
                continue
            elif code == 1200:
                skipped += 1
                drop_down_level -= 1
                drop_down_skip_category = False
                continue
            text_start = drop_down_level * 3 + 1
            if code < 300:   # must be befre "if drop_down_skip..." and after "text_start = "
                drop_down_level += 1
            if drop_down_skip_guild or drop_down_skip_category:
                skipped += 1
                continue
            self.tree_clean_len += 1
            if first_digit == 0 and code < 200:
                drop_down_skip_guild = True
            elif first_digit == 0 and code < 300:
                drop_down_skip_category = True
            y = max(num - skipped - self.tree_index, 0)
            if y >= h:
                break
            second_digit = (code % 100) // 10
            color = curses.color_pair(3)
            color_line = curses.color_pair(3)
            if second_digit == 1:   # muted
                color = curses.color_pair(5)
            elif second_digit == 2:   # mentioned
                color = curses.color_pair(8)
            elif second_digit == 3:   # unread
                color = curses.color_pair(7) | curses.A_BOLD
            elif second_digit == 4:   # active
                color = curses.color_pair(6)
                color_line = curses.color_pair(6)
            elif second_digit == 5:   # active mentioned
                color = curses.color_pair(9)
                color_line = curses.color_pair(6)
            if y == self.tree_selected - self.tree_index:   # selected
                color = curses.color_pair(4)
                color_line = curses.color_pair(4)
                self.tree_selected_abs = self.tree_selected + skipped
            # filled with spaces so background is drawn all the way
            self.win_tree.insstr(y, 0, line[:text_start], color_line)
            self.win_tree.insstr(y, text_start, line[text_start:] + " " * (w - len(line)) + "\n", color)

        y += 1
        while y < h:
            self.win_tree.insstr(y, 0, "\n", curses.color_pair(1))
            y += 1
        self.win_tree.refresh()


    def set_cursor_color(self, color_id):
        """Changes cursor color"""
        _, w = self.input_hw
        start = max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
        end = start + w - 1
        line_text = self.input_buffer[start:end].replace("\n", "␤")
        character = " "
        if self.cursor_pos < len(line_text):
            character = line_text[self.cursor_pos]
        if self.cursor_pos == w - 1:
            self.win_input_line.insch(0, self.cursor_pos, character, curses.color_pair(color_id))
        else:
            self.win_input_line.addch(0, self.cursor_pos, character, curses.color_pair(color_id))
        self.win_input_line.refresh()


    def blink_cursor(self):
        """Thread that makes cursor blink, hibernates after some time"""
        self.hibernate_cursor = 0
        while self.run:
            while self.run and self.hibernate_cursor >= 10:
                time.sleep(self.blink_cursor_on)
            if self.cursor_on:
                color_id = 1
                sleep_time = self.blink_cursor_on
            else:
                color_id = 2
                sleep_time = self.blink_cursor_off
            self.set_cursor_color(color_id)
            time.sleep(sleep_time)
            self.hibernate_cursor += 1
            self.cursor_on = not self.cursor_on


    def show_cursor(self):
        """Force crsor to be shown on screen and reset blinking"""
        if self.enable_blink_cursor:
            self.set_cursor_color(2)
            self.cursor_on = True
            self.hibernate_cursor = 0


    def update_status_line(self, text_l, text_r=None):
        """Update status text"""
        redraw = False
        if text_l != self.status_txt_l:
            self.status_txt_l = text_l
            redraw = True
        if text_r != self.status_txt_r:
            self.status_txt_r = text_r
            redraw = True
        if redraw:
            self.draw_status_line()


    def update_title_line(self, text_l, text_r=None):
        """Update status text"""
        if self.have_title:
            redraw = False
            if text_l != self.title_txt_l:
                self.title_txt_l = text_l
                redraw = True
            if text_r != self.title_txt_r:
                self.title_txt_r = text_r
                redraw = True
            if redraw:
                self.draw_title_line()


    def update_title_tree(self, text):
        """Update status text"""
        if self.have_title_tree and text != self.title_tree_txt:
            self.title_tree_txt = text
            self.draw_title_tree()


    def init_colors(self, colors):
        """Initializes color pairs AOT"""
        color_codes = []
        for color in colors:
            found = False
            pair_id = 0
            while pair_id < curses.COLOR_PAIRS:
                try:
                    pair = list(curses.pair_content(pair_id))
                except curses.error:
                    break   # new color pair will be stored with this id
                if pair == [0, 0]:
                    break
                if pair == color[:2]:
                    found = True
                    color_codes.append(pair_id)
                    break
                pair_id += 1
            if not found:
                curses.init_pair(pair_id, color[0], color[1])
                color_codes.append(pair_id)
        return color_codes


    def update_chat(self, chat_text, chat_format):
        """Update text buffer"""
        self.chat_buffer = chat_text
        self.chat_format = chat_format
        self.draw_chat()
        self.draw_input_line()


    def update_tree(self, tree_text, tree_format):
        """Update channel tree"""
        self.tree = tree_text
        self.tree_format = tree_format
        self.draw_tree()


    def wait_input(self, prompt="", init_text=None, reset=True, keep_cursor=False, scroll_bot=False):
        """
        Take input from user, and show it on screen
        Return typed text, absolute_tree_position and wether channel is changed
        """
        if reset:
            self.prompt = prompt
            self.input_buffer = prompt
            self.input_index = len(prompt)
            self.cursor_pos = len(prompt)
        if init_text:
            self.prompt = prompt
            self.input_buffer = self.prompt + init_text
            if not keep_cursor:
                self.input_index = len(self.input_buffer)
                _, w = self.input_hw
                self.cursor_pos = self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
                self.cursor_pos = max(self.cursor_pos, 0)
                self.cursor_pos = min(w - 1, self.cursor_pos)
        if scroll_bot:
            self.chat_selected = -1
            self.chat_index = 0
            self.draw_chat()

        self.draw_input_line()
        last = -1
        while last != ord("\n"):
            last = self.screen.getch()
            h, _ = self.screen_hw
            _, w = self.input_hw

            if last == ord("\n"):   # ENTER
                tmp = self.input_buffer
                self.input_buffer = prompt
                self.input_index = len(prompt)
                self.cursor_pos = len(prompt)
                self.draw_input_line()
                self.win_input_line.cursyncup()
                self.input_line_index = 0
                self.set_cursor_color(2)
                self.cursor_on = True
                return tmp[len(prompt):], self.chat_selected, self.tree_selected_abs, 0

            if last == curses.KEY_BACKSPACE:   # BACKSPACE
                if self.input_index > len(prompt):
                    self.input_buffer = self.input_buffer[:self.input_index-1] + self.input_buffer[self.input_index:]
                    self.input_index -= 1
                    self.show_cursor()

            if last == curses.KEY_DC:   # DEL
                if self.input_index < len(self.input_buffer):
                    self.input_buffer = self.input_buffer[:self.input_index] + self.input_buffer[self.input_index+1:]
                    self.show_cursor()

            elif last == curses.KEY_LEFT:   # LEFT
                if self.input_index > len(prompt):
                    # if index hits left screen edge, but there is more text to left, move line right
                    if self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index + len(prompt)) == 0:
                        self.input_line_index += min(INPUT_LINE_JUMP, w - 3)
                    else:
                        self.input_index -= 1
                    self.show_cursor()

            elif last == curses.KEY_RIGHT:   # RIGHT
                if self.input_index < len(self.input_buffer):
                    # if index hits right screen edge, but there is more text to right, move line right
                    if self.input_index - max(0, len(self.input_buffer) - w - self.input_line_index) == w:
                        self.input_line_index -= min(INPUT_LINE_JUMP, w - 3)
                    else:
                        self.input_index += 1
                    self.show_cursor()

            elif last == curses.KEY_UP:   # UP
                if self.chat_selected + 1 < len(self.chat_buffer):
                    top_line = self.chat_index + self.chat_hw[0] - 3
                    if top_line + 3 < len(self.chat_buffer) and self.chat_selected >= top_line:
                        self.chat_index += 1   # move history down
                    self.chat_selected += 1   # move selection up
                    self.draw_chat()

            elif last == curses.KEY_DOWN:   # DOWN
                if self.chat_selected >= self.dont_hide_chat_selection:   # if it is -1, selection is hidden
                    if self.chat_index and self.chat_selected <= self.chat_index + 2:   # +2 from status and input lines
                        self.chat_index -= 1   # move history up
                    self.chat_selected -= 1   # move selection down
                    self.draw_chat()

            # opposite than above, because tree is drawn top down
            elif last == 575:   # CTRL+UP
                if self.tree_selected >= 0:
                    if self.tree_index and self.tree_selected <= self.tree_index + 2:
                        self.tree_index -= 1
                    self.tree_selected -= 1
                    self.draw_tree()

            elif last == 534:   # CTRL+DOWN
                if self.tree_selected + 1 < self.tree_clean_len:
                    top_line = self.tree_index + self.tree_hw[0] - 3
                    if top_line + 3 < self.tree_clean_len and self.tree_selected >= top_line:
                        self.tree_index += 1
                    self.tree_selected += 1
                    self.draw_tree()

            elif last == 0:   # CTRL+SPACE
                if 300 <= self.tree_format[self.tree_selected_abs] <= 399:
                    # if selected tree entry is channel
                    # stop wait_input and return so new prompt can be loaded
                    tmp = self.input_buffer
                    self.input_buffer = prompt
                    return tmp[len(prompt):], self.chat_selected, self.tree_selected_abs, 4
                # if selected tree entry is drop-down
                if (self.tree_format[self.tree_selected_abs] % 10):
                    self.tree_format[self.tree_selected_abs] -= 1
                else:
                    self.tree_format[self.tree_selected_abs] += 1
                self.draw_tree()
                self.tree_format_changed = 1

            elif last == ctrl(110):   # Ctrl+N
                self.input_buffer = self.input_buffer[:self.input_index] + "\n" + self.input_buffer[self.input_index:]
                self.input_index += 1
                self.show_cursor()

            elif last == ctrl(114):   # Ctrl+R
                if self.chat_selected != -1:
                    self.replying_msg = True
                    self.deleting_msg = False
                    tmp = self.input_buffer
                    self.input_buffer = prompt
                    return tmp[len(prompt):], self.chat_selected, self.tree_selected_abs, 1

            elif last == ctrl(101):   # Ctrl+E
                if self.chat_selected != -1:
                    self.deleting_msg = False
                    self.replying_msg = False
                    tmp = self.input_buffer
                    self.input_buffer = prompt
                    return tmp[len(prompt):], self.chat_selected, self.tree_selected_abs, 2

            elif last == ctrl(100):   # Ctrl+D
                if self.chat_selected != -1:
                    self.replying_msg = False
                    tmp = self.input_buffer
                    self.input_buffer = prompt
                    self.deleting_msg = True
                    return tmp[len(prompt):], self.chat_selected, self.tree_selected_abs, 3

            elif last == ctrl(98):   # Ctrl+B
                tmp = self.input_buffer
                self.input_buffer = prompt
                return tmp[len(prompt):], self.chat_selected, self.tree_selected_abs, 7

            elif last == ctrl(112):   # CTRL+P when replying
                tmp = self.input_buffer
                self.input_buffer = prompt
                return tmp[len(prompt):], self.chat_selected, self.tree_selected_abs, 6

            elif self.deleting_msg and last == 110:   # N when deleting
                self.deleting_msg = False
                tmp = self.input_buffer
                self.input_buffer = prompt
                return "n", self.chat_selected, self.tree_selected_abs, 5

            elif self.deleting_msg and last == 121:   # Y when deleting
                self.deleting_msg = False
                tmp = self.input_buffer
                self.input_buffer = prompt
                return "y", self.chat_selected, self.tree_selected_abs, 0

            elif last == 27:   # ESCAPE
                # terminal waits when Esc is pressed
                self.deleting_msg = False
                self.replying_msg = False
                tmp = self.input_buffer
                self.input_buffer = prompt
                return tmp[len(prompt):], self.chat_selected, self.tree_selected_abs, 5

            elif last == curses.KEY_RESIZE:
                self.resize()
                h, _ = self.screen_hw
                _, w = self.input_hw

            elif 32 <= last <= 126:   # all regular characters
                self.input_buffer = self.input_buffer[:self.input_index] + chr(last) + self.input_buffer[self.input_index:]
                self.input_index += 1
                self.typing = int(time.time())
                self.show_cursor()

            # keep index inside screen
            self.cursor_pos = self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
            self.cursor_pos = max(self.cursor_pos, 0)
            self.cursor_pos = min(w - 1, self.cursor_pos)
            self.draw_input_line()
        return None, None, None, None
