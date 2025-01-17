import curses
import logging
import os
import threading
import time

from endcord import peripherals

logger = logging.getLogger(__name__)
INPUT_LINE_JUMP = 20   # jump size when moving input line


def ctrl(x):
    """Convert character code to ctrl-modified"""
    return x - 96


class TUI():
    """Methods used to draw terminal user interface"""

    def __init__(self, screen, config):
        self.spellchecker = peripherals.SpellCheck(config["aspell_mode"], config["aspell_lang"])
        curses.use_default_colors()
        curses.curs_set(0)   # using custom cursor
        curses.init_pair(1, 255, -1)   # white on default
        curses.init_pair(2, 233, 255)   # black on white
        print("\x1b[?2004h")   # enable bracketed paste mode
        curses.init_pair(3, config["color_tree_default"][0], config["color_tree_default"][1])
        curses.init_pair(4, config["color_tree_selected"][0], config["color_tree_selected"][1])
        curses.init_pair(5, config["color_tree_muted"][0], config["color_tree_muted"][1])
        curses.init_pair(6, config["color_tree_active"][0], config["color_tree_active"][1])
        curses.init_pair(7, config["color_tree_unseen"][0], config["color_tree_unseen"][1])
        curses.init_pair(8, config["color_tree_mentioned"][0], config["color_tree_mentioned"][1])
        curses.init_pair(9, config["color_tree_active_mentioned"][0], config["color_tree_active_mentioned"][1])
        curses.init_pair(10, config["color_format_misspelled"][0], config["color_format_misspelled"][1])
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
        self.input_line_index = 0   # index of input line, when moving it to left
        self.cursor_pos = 0   # on-screen position of cursor
        self.cursor_on = True
        self.deleting_msg = False
        self.replying_msg = False
        self.asking_num = False
        self.enable_autocomplete = False
        self.spelling_range = [0, 0]
        self.misspelled = []
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
        prompt_hwyx = (1, len(self.prompt), curses.LINES - 1, self.tree_width + 1)
        self.win_prompt = self.screen.derwin(*prompt_hwyx)
        input_line_hwyx = (
            1,
            curses.COLS - (self.tree_width + 1) - len(self.prompt),
            curses.LINES - 1,
            self.tree_width + len(self.prompt) + 1,
        )
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
        self.win_input_line.resize(1, w - (self.tree_width + 1) - len(self.prompt))
        self.win_input_line.mvwin(h - 1, self.tree_width + len(self.prompt) + 1)
        self.win_prompt.mvwin(h - 1, self.tree_width + 1)
        self.win_prompt.resize(1, len(self.prompt))
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
        """Return whether it has been typied in past 3s"""
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
        if self.chat_selected >= selected:
            up = True
        else:
            up = False
        self.chat_selected = selected
        if self.chat_selected == -1:
            self.chat_index = 0
        elif change_amount and self.chat_index:
            self.chat_index += change_amount
        on_screen_h = selected - self.chat_index
        if on_screen_h > self.chat_hw[0] - 3 or on_screen_h < 3:
            if up:
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
        self.update_prompt(self.prompt)   # draw_input_line() is called in here
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
        title_txt = self.title_tree_txt[:w]
        title_line = title_txt + " " * (w - len(title_txt))
        self.win_title_tree.insstr(0, 0, title_line + "\n", curses.color_pair(2))
        self.win_title_tree.refresh()


    def draw_input_line(self):
        """Draw text input line and prompt"""
        w = self.input_hw[1]
        # show only part of line when longer than screen
        start = max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
        end = start + w - 1
        line_text = self.input_buffer[start:end].replace("\n", "␤")
        character = " "
        pos = 0
        cursor_drawn = False
        for pos, character in enumerate(line_text):
            # cursor in the string
            if not cursor_drawn and self.cursor_pos == pos:
                self.win_input_line.insch(0, self.cursor_pos, character, curses.color_pair(2))
                cursor_drawn = True
            else:
                bad = False
                for bad_range in self.misspelled:
                    if bad_range[0] <= pos < sum(bad_range) and (bad_range[0] > self.cursor_pos or self.cursor_pos >= sum(bad_range)):
                        try:
                            # cant insch weird characters, still faster than always calling insstr
                            self.win_input_line.insch(0, pos, character, curses.color_pair(10))
                        except OverflowError:
                            self.win_input_line.insstr(0, pos, character, curses.color_pair(10))
                        bad = True
                        break
                if not bad:
                    try:
                        self.win_input_line.insch(0, pos, character, curses.color_pair(0))
                    except OverflowError:
                        self.win_input_line.insstr(0, pos, character, curses.color_pair(0))
        self.win_input_line.insch(0, pos + 1, "\n", curses.color_pair(0))
        # cursor at the end of string
        if not cursor_drawn and self.cursor_pos >= len(line_text):
            self.show_cursor()
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
        w = self.input_hw[1]
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
        """Force cursor to be shown on screen and reset blinking"""
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


    def update_tree(self, tree_text, tree_format):
        """Update channel tree"""
        self.tree = tree_text
        self.tree_format = tree_format
        self.draw_tree()


    def update_prompt(self, prompt):
        """Draw prompt line and resize input line"""
        h, w = self.screen.getmaxyx()
        self.prompt = prompt
        self.win_input_line.resize(1, w - (self.tree_width + 1) - len(self.prompt))
        self.win_input_line.mvwin(h - 1, self.tree_width + len(self.prompt) + 1)
        self.input_hw = self.win_input_line.getmaxyx()
        self.spellcheck()
        self.draw_input_line()
        self.win_prompt.mvwin(h - 1, self.tree_width + 1)
        self.win_prompt.resize(1, len(self.prompt))
        self.win_prompt.refresh()
        self.win_prompt.insstr(0, 0, self.prompt, curses.color_pair(0))
        self.win_prompt.refresh()


    def spellcheck(self):
        """Spellcheck words visible on screen"""
        w = self.input_hw[1]
        input_buffer = self.input_buffer
        line_start = max(0, len(input_buffer) - w + 1 - self.input_line_index)
        # first space before line_start in input_buffer
        if " " in input_buffer[:line_start]:
            range_word_start = len(input_buffer[:line_start].rsplit(" ", 1)[0]) + bool(line_start)
        else:
            range_word_start = 0
        # when input buffer cant fit on screen
        if len(input_buffer) > w:
            # first space after line_start + input_line_w in input_buffer
            range_word_end = line_start + w + len(input_buffer[line_start+w:].split(" ")[0])
        else:
            # first space before last word
            range_word_end = len(input_buffer) - len(input_buffer.split(" ")[-1]) - 1
        # indexes of words visible on screen
        spelling_range = [range_word_start, range_word_end]
        if spelling_range != self.spelling_range:
            words_on_screen = input_buffer[range_word_start:range_word_end].split(" ")
            misspelled_words_on_screen = self.spellchecker.check_list(words_on_screen)
            misspelled_words_on_screen.append(False)
            # loop over all words visible on screen
            self.misspelled = []
            index = 0
            for num, word in enumerate(input_buffer[line_start:line_start+w].split(" ")):
                word_len = len(word)
                if misspelled_words_on_screen[num]:
                    self.misspelled.append([index, word_len])
                index += word_len + 1
            # self.misspelled format: [start_index_on_screen, word_len] for all misspelled words on screen
        self.spelling_range = spelling_range


    def wait_input(self, prompt="", init_text=None, reset=True, keep_cursor=False, scroll_bot=False, autocomplete=False):
        """
        Take input from user, and show it on screen
        Return typed text, absolute_tree_position and whether channel is changed
        """
        if reset:
            self.input_buffer = ""
            self.input_index = 0
            self.cursor_pos = 0
            self.enable_autocomplete = autocomplete
        if init_text:
            self.input_buffer = init_text
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
        self.spellcheck()
        self.update_prompt(prompt)   # draw_input_line() is called in heren
        bracket_paste = False
        sequence = []   # for detecting bracket paste sequences
        selected_completion = 0
        key = -1
        while self.run:
            key = self.screen.getch()
            h = self.screen_hw[0]
            w = self.input_hw[1]

            if key == ord("\n"):   # ENTER
                # wehen pasting, dont return, but insert newline character
                if bracket_paste:
                    self.input_buffer = self.input_buffer[:self.input_index] + "\n" + self.input_buffer[self.input_index:]
                    self.input_index += 1
                    pass
                else:
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    self.input_index = 0
                    self.cursor_pos = 0
                    self.draw_input_line()
                    self.win_input_line.cursyncup()
                    self.input_line_index = 0
                    self.set_cursor_color(2)
                    self.cursor_on = True
                    return tmp, self.chat_selected, self.tree_selected_abs, 0

            elif 32 <= key <= 126:   # all regular characters
                self.input_buffer = self.input_buffer[:self.input_index] + chr(key) + self.input_buffer[self.input_index:]
                self.input_index += 1
                self.typing = int(time.time())
                if self.enable_autocomplete:
                    completion_base = self.input_buffer
                    selected_completion = 0
                self.show_cursor()

            elif key == 27:   # ESCAPE
                # terminal waits when Esc is pressed, but not when sending escape sequence
                self.screen.nodelay(True)
                key = self.screen.getch()
                if key == -1:
                    # escape key
                    self.deleting_msg = False
                    self.replying_msg = False
                    self.asking_num = False
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    self.screen.nodelay(False)
                    return tmp, self.chat_selected, self.tree_selected_abs, 5
                # sequence (bracketed paste or Alt+KEY)
                sequence = [27, key]
                # -1 means no key is pressed, 126 is end of escape sequence
                while key != -1:
                    key = self.screen.getch()
                    sequence.append(key)
                    if key == 126:
                        break
                self.screen.nodelay(False)
                # match sequences
                if sequence == [27, 91, 50, 48, 48, 126]:
                    bracket_paste = True
                elif sequence == [27, 91, 50, 48, 49, 126]:
                    bracket_paste = False

            elif key == curses.KEY_BACKSPACE:   # BACKSPACE
                if self.input_index > 0:
                    self.input_buffer = self.input_buffer[:self.input_index-1] + self.input_buffer[self.input_index:]
                    self.input_index -= 1
                    if self.enable_autocomplete:
                        completion_base = self.input_buffer
                        selected_completion = 0
                    self.show_cursor()

            elif key == curses.KEY_DC:   # DEL
                if self.input_index < len(self.input_buffer):
                    self.input_buffer = self.input_buffer[:self.input_index] + self.input_buffer[self.input_index+1:]
                    self.show_cursor()

            elif key == curses.KEY_LEFT:   # LEFT
                if self.input_index > 0:
                    # if index hits left screen edge, but there is more text to left, move line right
                    if self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index) == 0:
                        self.input_line_index += min(INPUT_LINE_JUMP, w - 3)
                    else:
                        self.input_index -= 1
                    self.show_cursor()

            elif key == curses.KEY_RIGHT:   # RIGHT
                if self.input_index < len(self.input_buffer):
                    # if index hits right screen edge, but there is more text to right, move line right
                    if self.input_index - max(0, len(self.input_buffer) - w - self.input_line_index) == w:
                        self.input_line_index -= min(INPUT_LINE_JUMP, w - 3)
                    else:
                        self.input_index += 1
                    self.show_cursor()

            elif key == curses.KEY_UP:   # UP
                if self.chat_selected + 1 < len(self.chat_buffer):
                    top_line = self.chat_index + self.chat_hw[0] - 3
                    if top_line + 3 < len(self.chat_buffer) and self.chat_selected >= top_line:
                        self.chat_index += 1   # move history down
                    self.chat_selected += 1   # move selection up
                    self.draw_chat()

            elif key == curses.KEY_DOWN:   # DOWN
                if self.chat_selected >= self.dont_hide_chat_selection:   # if it is -1, selection is hidden
                    if self.chat_index and self.chat_selected <= self.chat_index + 2:   # +2 from status and input lines
                        self.chat_index -= 1   # move history up
                    self.chat_selected -= 1   # move selection down
                    self.draw_chat()

            elif self.enable_autocomplete and key == 9:   # TAB - same as CTRL+I
                if self.input_buffer and self.input_index == len(self.input_buffer):
                    completions = peripherals.complete_path(completion_base, separator=False)
                    if completions:
                        path = completions[selected_completion]
                        self.input_buffer = path
                        self.input_index = len(path)
                        self.show_cursor()
                        selected_completion += 1
                        if selected_completion > len(completions) - 1:
                            selected_completion = 0

            # opposite than above, because tree is drawn top down
            elif key == 575:   # CTRL+UP
                if self.tree_selected >= 0:
                    if self.tree_index and self.tree_selected <= self.tree_index + 2:
                        self.tree_index -= 1
                    self.tree_selected -= 1
                    self.draw_tree()

            elif key == 534:   # CTRL+DOWN
                if self.tree_selected + 1 < self.tree_clean_len:
                    top_line = self.tree_index + self.tree_hw[0] - 3
                    if top_line + 3 < self.tree_clean_len and self.tree_selected >= top_line:
                        self.tree_index += 1
                    self.tree_selected += 1
                    self.draw_tree()

            elif key == 0:   # CTRL+SPACE
                if 300 <= self.tree_format[self.tree_selected_abs] <= 399:
                    # if selected tree entry is channel
                    # stop wait_input and return so new prompt can be loaded
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    return tmp, self.chat_selected, self.tree_selected_abs, 4
                # if selected tree entry is drop-down
                if (self.tree_format[self.tree_selected_abs] % 10):
                    self.tree_format[self.tree_selected_abs] -= 1
                else:
                    self.tree_format[self.tree_selected_abs] += 1
                self.draw_tree()
                self.tree_format_changed = 1

            elif key == ctrl(110):   # Ctrl+N
                self.input_buffer = self.input_buffer[:self.input_index] + "\n" + self.input_buffer[self.input_index:]
                self.input_index += 1
                self.show_cursor()

            elif key == ctrl(114):   # Ctrl+R
                if self.chat_selected != -1:
                    self.replying_msg = True
                    self.deleting_msg = False
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    return tmp, self.chat_selected, self.tree_selected_abs, 1

            elif key == ctrl(101):   # Ctrl+E
                if self.chat_selected != -1:
                    self.deleting_msg = False
                    self.replying_msg = False
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    return tmp, self.chat_selected, self.tree_selected_abs, 2

            elif key == ctrl(100):   # Ctrl+D
                if self.chat_selected != -1:
                    self.replying_msg = False
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    self.deleting_msg = True
                    return tmp, self.chat_selected, self.tree_selected_abs, 3

            elif key == ctrl(98):   # Ctrl+B
                tmp = self.input_buffer
                self.input_buffer = ""
                return tmp, self.chat_selected, self.tree_selected_abs, 7

            elif key == ctrl(112):   # CTRL+P when replying
                tmp = self.input_buffer
                self.input_buffer = ""
                return tmp, self.chat_selected, self.tree_selected_abs, 6

            elif self.deleting_msg and key == 110:   # N when deleting
                self.deleting_msg = False
                tmp = self.input_buffer
                self.input_buffer = ""
                return "n", self.chat_selected, self.tree_selected_abs, 5

            elif self.deleting_msg and key == 121:   # Y when deleting
                self.deleting_msg = False
                tmp = self.input_buffer
                self.input_buffer = ""
                return "y", self.chat_selected, self.tree_selected_abs, 0

            elif key == ctrl(103):   # Ctrl+G
                if self.chat_selected != -1:
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    return tmp, self.chat_selected, self.tree_selected_abs, 8

            elif key == ctrl(119):   # Ctrl+W
                if self.chat_selected != -1:
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    self.asking_num = True
                    return tmp, self.chat_selected, self.tree_selected_abs, 9

            elif key == ctrl(111):   # Ctrl+O
                if self.chat_selected != -1:
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    self.asking_num = True
                    return tmp, self.chat_selected, self.tree_selected_abs, 10

            elif key == ctrl(120):   # Ctrl+X
                if self.chat_selected != -1:
                    tmp = self.input_buffer
                    self.input_buffer = ""
                    self.deleting_msg = True
                    return tmp, self.chat_selected, self.tree_selected_abs, 11

            elif key == ctrl(104):   # Ctrl+H
                tmp = self.input_buffer
                self.input_buffer = ""
                return tmp, self.chat_selected, self.tree_selected_abs, 12

            elif key == ctrl(117):   # Ctrl+U
                tmp = self.input_buffer
                self.input_buffer = ""
                self.enable_autocomplete = True
                self.misspelled = []
                return tmp, self.chat_selected, self.tree_selected_abs, 13

            elif key == ctrl(108):   # Ctrl+L
                self.screen.clear()
                self.redraw_ui()

            elif key == curses.KEY_RESIZE:
                self.resize()
                h, _ = self.screen_hw
                _, w = self.input_hw

            # terminal reserved keys: Ctrl+ C, Q, S, Z, M

            # keep index inside screen
            self.cursor_pos = self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
            self.cursor_pos = max(self.cursor_pos, 0)
            self.cursor_pos = min(w - 1, self.cursor_pos)
            if not self.enable_autocomplete:
                self.spellcheck()
            self.draw_input_line()
        return None, None, None, None
