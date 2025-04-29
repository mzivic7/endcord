import curses
import logging
import sys
import threading
import time

from endcord import acs, peripherals

logger = logging.getLogger(__name__)
INPUT_LINE_JUMP = 20   # jump size when moving input line
MAX_DELTA_STORE = 50   # limit undo size
MIN_ASSIST_LETTERS = 2
ASSIST_TRIGGERS = ("#", "@", ":", ";")
if sys.platform == "win32":
    BACKSPACE = 8   # i cant believe this
else:
    BACKSPACE = curses.KEY_BACKSPACE


def ctrl(x):
    """Convert character code to ctrl-modified"""
    return x - 96


def set_list_item(input_list, item, index):
    """Replace existing item or append to list if it doesnt exist"""
    try:
        input_list[index] = item
    except IndexError:
        input_list.append(item)
    return input_list


def safe_insch(screen, y, x, character, color):
    """
    Safely insert character into line.
    This is because curses.insch will throw exception for weird chracters.
    curses.insstr will not, but is slower.
    """
    try:
        # cant insch weird characters, but this is faster than always calling insstr
        screen.insch(y, x, character, color)
    except (OverflowError, UnicodeEncodeError):
        screen.insstr(y, x, character, color)


class TUI():
    """Methods used to draw terminal user interface"""

    def __init__(self, screen, config, keybindings):
        self.spellchecker = peripherals.SpellCheck(config["aspell_mode"], config["aspell_lang"])
        acs_map = acs.get_map()
        curses.use_default_colors()
        curses.curs_set(0)   # using custom cursor
        print("\x1b[?2004h")   # enable bracketed paste mode
        self.last_free_id = 1   # last free color pair id
        self.color_cache = []   # for restoring colors
        self.attrib_map = [0]   # has 0 so its index starts from 1 to be matched with color pairs
        tree_bg = config["color_tree_default"][1]
        self.init_pair((255, -1))   # white on default
        self.init_pair((233, 255))   # black on white
        self.init_pair(config["color_tree_default"])   # 3
        self.init_pair(config["color_tree_selected"])
        self.init_pair(config["color_tree_muted"])
        self.init_pair(config["color_tree_active"])   # 6
        self.init_pair(config["color_tree_unseen"])
        self.init_pair(config["color_tree_mentioned"])
        self.init_pair(config["color_tree_active_mentioned"])   # 9
        self.init_pair(config["color_misspelled"])
        self.init_pair(config["color_extra_line"])
        self.init_pair(config["color_title_line"])   # 12
        self.init_pair(config["color_prompt"])
        self.init_pair(config["color_input_line"])
        self.init_pair(config["color_cursor"])   # 15
        self.init_pair(config["color_chat_selected"])
        self.init_pair(config["color_status_line"])
        self.init_pair((46, tree_bg))    # green   # 18
        self.init_pair((208, tree_bg))   # orange
        self.init_pair((196, tree_bg))   # red
        self.init_pair(config["color_extra_window"])   # 21
        self.color_default = self.last_free_id + 1
        self.role_color_start_id = self.last_free_id   # starting id for role colors
        self.keybindings = {key: (val,) if not isinstance(val, tuple) else val for key, val in keybindings.items()}
        self.screen = screen

        # load config
        self.have_title = bool(config["format_title_line_l"])
        self.have_title_tree = bool(config["format_title_tree"])
        vert_line = config["tree_vert_line"][0]
        self.vert_line = acs_map.get(vert_line, vert_line)
        self.tree_width = config["tree_width"]
        self.extra_window_h = config["extra_window_height"]
        self.blink_cursor_on = config["cursor_on_time"]
        self.blink_cursor_off = config["cursor_off_time"]
        self.tree_dm_status = config["tree_dm_status"]
        self.member_list_width = config["member_list_width"]
        self.assist = config["assist"]

        # find all first chain parts
        self.chainable = []
        for binding in self.keybindings.values():
            if isinstance(binding, str):
                split_binding = binding.split("-")
                if len(split_binding) == 1:
                    continue
                elif len(split_binding) > 2:
                    sys.exit(f"Invalid keybinding: {binding}")
                try:
                    self.chainable.append(int(split_binding[0]))
                except ValueError:
                    self.chainable.append(split_binding[0])

        # initial values
        if not (self.blink_cursor_on and self.blink_cursor_off):
            self.enable_blink_cursor = False
        else:
            self.enable_blink_cursor = True
        self.disable_drawing = False
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
        self.enable_autocomplete = False
        self.spelling_range = [0, 0]
        self.misspelled = []
        self.delta_store = []
        self.last_action = None
        self.delta_cache = ""
        self.delta_index = 0
        self.undo_index = None
        self.input_select_start = None
        self.input_select_end = None
        self.input_select_text = ""
        self.typing = time.time()
        self.extra_line_text = ""
        self.extra_window_title = ""
        self.extra_window_body = ""
        self.member_list = []
        self.member_list_format = []
        self.extra_selected = -1
        self.extra_index = 0
        self.extra_select = False
        self.mlist_selected = -1
        self.mlist_index = 0
        self.run = True
        self.win_extra_line = None
        self.win_extra_window = None
        self.win_member_list = None
        self.win_prompt = None
        self.keybinding_chain = None
        self.assist_start = -1

        # start drawing
        self.need_update = threading.Event()
        self.screen_update_thread = threading.Thread(target=self.screen_update, daemon=True)
        self.screen_update_thread.start()

        self.resize()

        if self.enable_blink_cursor:
            self.blink_cursor_thread = threading.Thread(target=self.blink_cursor, daemon=True)
            self.blink_cursor_thread.start()
        self.need_update.set()


    def screen_update(self):
        """Thread that updates drawn content on physical screen"""
        while True:
            self.need_update.wait()
            # here must be delay, otherwise output gets messed up
            time.sleep(0.01)
            curses.doupdate()
            self.need_update.clear()


    def resize(self):
        """Resize screen area"""
        h, w = self.screen.getmaxyx()
        chat_hwyx = (
            h - 2 - int(self.have_title),
            w - (self.tree_width + 1),
            int(self.have_title),
            self.tree_width + 1,
        )
        input_line_hwyx = (1, w - (self.tree_width + 1), h - 1, self.tree_width + 1)
        status_line_hwyx = (1, w - (self.tree_width + 1), h - 2, self.tree_width + 1)
        tree_hwyx = (
            h - int(self.have_title_tree),
            self.tree_width,
            int(self.have_title),
            0,
        )
        self.win_chat = self.screen.derwin(*chat_hwyx)
        prompt_hwyx = (1, len(self.prompt), h - 1, self.tree_width + 1)
        self.win_prompt = self.screen.derwin(*prompt_hwyx)
        input_line_hwyx = (
            1,
            w - (self.tree_width + 1) - len(self.prompt),
            h - 1,
            self.tree_width + len(self.prompt) + 1,
        )
        self.win_input_line = self.screen.derwin(*input_line_hwyx)
        self.win_status_line = self.screen.derwin(*status_line_hwyx)
        self.win_tree = self.screen.derwin(*tree_hwyx)
        if self.have_title:
            title_line_yx = (1, w - (self.tree_width + 1), 0, self.tree_width + 1)
            self.win_title_line = self.screen.derwin(*title_line_yx)
            self.title_hw = self.win_title_line.getmaxyx()
        if self.have_title_tree:
            tree_title_line_hwyx = (1, self.tree_width, 0, 0)
            self.win_title_tree = self.screen.derwin(*tree_title_line_hwyx)
            self.tree_title_hw = self.win_title_tree.getmaxyx()
        self.screen_hw = self.screen.getmaxyx()
        self.chat_hw = self.win_chat.getmaxyx()
        self.status_hw = self.win_status_line.getmaxyx()
        self.input_hw = self.win_input_line.getmaxyx()
        self.tree_hw = self.win_tree.getmaxyx()
        self.win_extra_line = None
        self.win_extra_window = None
        self.win_member_list = None
        self.redraw_ui()


    def get_dimensions(self):
        """Return current dimensions for screen objects"""
        return (
            tuple(self.win_chat.getmaxyx()),
            tuple(self.win_tree.getmaxyx()),
            tuple(self.win_status_line.getmaxyx()),
        )

    def get_selected(self):
        """Return index of currently selected line and how much text has been scrolled"""
        return self.chat_selected, self.chat_index


    def get_extra_selected(self):
        """Return index of selected line in extra window"""
        return self.extra_selected


    def get_mlist_selected(self):
        """Return index of selected line in member list"""
        return self.mlist_selected


    def get_my_typing(self):
        """Return whether it has been typed in past 3s"""
        if time.time() - self.typing > 3:
            return None
        return True


    def get_tree_format(self):
        """Return tree format if it has been changed"""
        if self.tree_format_changed:
            self.tree_format_changed = False
            return self.tree_format
        return None


    def get_assist(self):
        """Return word to be assisted with completing and type of asssist needed"""
        if self.assist_start >= 0:
            if self.assist_start < self.input_index - (MIN_ASSIST_LETTERS - 1):
                if (
                    self.assist_start != -1 and
                    self.assist_start < len(self.input_buffer) and
                    self.input_buffer[self.assist_start-1] in ASSIST_TRIGGERS
                ):
                    assist_type = ASSIST_TRIGGERS.index(self.input_buffer[self.assist_start-1]) + 1
                    if assist_type == 3 and self.assist_start != 1 and self.input_buffer[self.assist_start-2] != " ":
                        # skip :emoji trigger if no space before it
                        return None, None
                    assist_word = self.input_buffer[self.assist_start : self.input_index]
                    return assist_word, assist_type
                self.assist_start = -1
                return None, 100
            if self.assist_start > self.input_index:
                return None, 100
        return None, None


    def get_last_free_color_id(self):
        """Return last free color id. Should be run at the end of all color initializations in endcord.tui."""
        return self.last_free_id


    def get_color_cache(self):
        """Return first 255 cached colors"""
        return self.color_cache[:255]


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


    def set_input_index(self, index):
        """Set cursor position on input line"""
        self.input_index = index
        _, w = self.input_hw
        self.cursor_pos = self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
        self.cursor_pos = max(self.cursor_pos, 0)
        self.cursor_pos = min(w - 1, self.cursor_pos)
        self.show_cursor()


    def store_input_selected(self):
        """Get selected text from imput line"""
        input_select_start = self.input_select_start
        input_select_end = self.input_select_end
        if input_select_start > input_select_end:
            # swap so start is always left side
            input_select_start, input_select_end = input_select_end, input_select_start
        self.input_select_start = None   # stop selection
        self.input_select_text = self.input_buffer[input_select_start:input_select_end]
        return input_select_start, input_select_end


    def allow_chat_selected_hide(self, allow):
        """Allow selected line in chat to be none, position -1"""
        self.dont_hide_chat_selection = not(allow)


    def tree_select_active(self):
        """Move tree selection to active channel"""
        skipped = 0
        drop_down_skip_guild = False
        drop_down_skip_category = False
        drop_down_skip_channel = False
        for num, code in enumerate(self.tree_format):
            if code == 1100:
                skipped += 1
                drop_down_skip_guild = False
                continue
            elif code == 1200:
                skipped += 1
                drop_down_skip_category = False
                continue
            elif code == 1300:
                skipped += 1
                drop_down_skip_channel = False
                continue
            elif drop_down_skip_guild or drop_down_skip_category or drop_down_skip_channel:
                skipped += 1
                continue
            first_digit = code % 10
            if first_digit == 0 and code < 200:
                drop_down_skip_guild = True
            elif first_digit == 0 and code < 300:
                drop_down_skip_category = True
            elif first_digit == 0 and 500 <= code <= 599:
                drop_down_skip_channel = True
            if (code % 100) // 10 in (4, 5):
                self.tree_selected = num - skipped
                self.tree_index = max(self.tree_selected - self.tree_hw[0] + 3, 0)
                break
        self.draw_tree()


    def tree_select(self, tree_pos):
        """Select specific irem in tree by its index"""
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
            if num == tree_pos:
                self.tree_selected = num - skipped
                self.tree_index = max(self.tree_selected - self.tree_hw[0] + 3, 0)
                break
        self.draw_tree()


    def redraw_ui(self):
        """Redraw entire ui"""
        self.screen.vline(0, self.tree_hw[1], self.vert_line, self.screen_hw[0])
        if self.have_title and self.have_title_tree:
            # fill gap between titles
            self.screen.addch(0, self.tree_hw[1], self.vert_line, curses.color_pair(12))
        self.screen.noutrefresh()
        self.need_update.set()
        self.draw_status_line()
        self.draw_chat()
        self.update_prompt(self.prompt)   # draw_input_line() is called in here
        self.draw_tree()
        if self.have_title:
            self.draw_title_line()
        if self.have_title_tree:
            self.draw_title_tree()
        self.draw_extra_line(self.extra_line_text)
        self.draw_extra_window(self.extra_window_title, self.extra_window_body, self.extra_select)
        self.draw_member_list(self.member_list, self.member_list_format)


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
        self.win_status_line.insstr(0, 0, status_line + "\n", curses.color_pair(17) | self.attrib_map[17])
        self.win_status_line.noutrefresh()
        self.need_update.set()


    def draw_title_line(self):
        """Draw title line, works same as status line"""
        h, w = self.title_hw
        title_txt = self.title_txt_l[:w-1]
        if self.title_txt_r and len(title_txt) + len(self.title_txt_r) + 4 < w:
            title_line = title_txt + " " * (w - len(title_txt) - len(self.title_txt_r)) + self.title_txt_r
        else:
            title_line = title_txt + " " * (w - len(title_txt))
        self.win_title_line.insstr(0, 0, title_line + "\n", curses.color_pair(12) | self.attrib_map[12])
        self.win_title_line.noutrefresh()
        self.need_update.set()


    def draw_title_tree(self):
        """Draw tree title line, works same as status line, but without right text"""
        h, w = self.tree_title_hw
        title_txt = self.title_tree_txt[:w]
        title_line = title_txt + " " * (w - len(title_txt))
        self.win_title_tree.insstr(0, 0, title_line + "\n", curses.color_pair(12) | self.attrib_map[12])
        self.win_title_tree.noutrefresh()
        self.need_update.set()


    def draw_input_line(self):
        """Draw text input line"""
        w = self.input_hw[1]
        # show only part of line when longer than screen
        start = max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
        end = start + w - 1
        line_text = self.input_buffer[start:end].replace("\n", "␤")

        # prepare selected range
        if self.input_select_start is not None:
            selected_start_screen = self.input_select_start - max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
            selected_end_screen = self.input_select_end - max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
            if selected_start_screen > selected_end_screen:
                # swap so start is always left side
                selected_start_screen, selected_end_screen = selected_end_screen, selected_start_screen

        # draw
        character = " "
        pos = 0
        cursor_drawn = False
        for pos, character in enumerate(line_text):
            # cursor in the string
            if not cursor_drawn and self.cursor_pos == pos:
                safe_insch(self.win_input_line, 0, self.cursor_pos, character, curses.color_pair(15) | self.attrib_map[15])
                cursor_drawn = True
            # selected part of string
            elif self.input_select_start is not None and selected_start_screen <= pos < selected_end_screen:
                safe_insch(self.win_input_line, 0, pos, character, curses.color_pair(15) | self.attrib_map[15])
            else:
                for bad_range in self.misspelled:
                    if bad_range[0] <= pos < sum(bad_range) and (bad_range[0] > self.cursor_pos or self.cursor_pos >= sum(bad_range)+1):
                        safe_insch(self.win_input_line, 0, pos, character, curses.color_pair(10) | self.attrib_map[10])
                        break
                else:
                    safe_insch(self.win_input_line, 0, pos, character, curses.color_pair(14) | self.attrib_map[14])
        self.win_input_line.insch(0, pos + 1, "\n", curses.color_pair(0))
        # cursor at the end of string
        if not cursor_drawn and self.cursor_pos >= len(line_text):
            self.show_cursor()
        self.win_input_line.noutrefresh()
        self.need_update.set()


    def draw_chat(self, norefresh=False):
        """Draw chat with applied color formatting"""
        h, w = self.chat_hw
        # drawing from down to up
        y = h
        chat_format = self.chat_format[self.chat_index:]
        try:
            for num, line in enumerate(self.chat_buffer[self.chat_index:]):
                y = h - (num + 1)
                if y < 0 or y >= h:
                    break
                if num == self.chat_selected - self.chat_index:
                    self.win_chat.insstr(y, 0, line + " " * (w - len(line)) + "\n", curses.color_pair(16))
                else:
                    line_format = chat_format[num]
                    default_color_id = line_format[0][0]
                    # filled with spaces so background is drawn all the way
                    default_color = curses.color_pair(default_color_id) | self.attrib_map[default_color_id]
                    self.win_chat.insstr(y, 0, " " * w + "\n", curses.color_pair(default_color_id))
                    for pos, character in enumerate(line):
                        if pos >= w:
                            break
                        for format_part in line_format[1:]:
                            if format_part[1] <= pos < format_part[2]:
                                color = format_part[0]
                                if isinstance(color, list):   # attribute-only color is a list
                                    # using base color because it is in message content anyway
                                    color_ready = curses.color_pair(default_color_id)
                                    for attribute in color:
                                        color_ready |= attribute
                                else:
                                    if color > 255:   # set all colors after 255 to default color
                                        color = self.color_default
                                    color_ready = curses.color_pair(color) | self.attrib_map[color]
                                safe_insch(self.win_chat, y, pos, character, color_ready)
                                break
                        else:
                            safe_insch(self.win_chat, y, pos, character, default_color)
            # fill empty lines with spaces so background is drawn all the way
            y -= 1
            while y >= 0:
                self.win_chat.insstr(y, 0, "\n", curses.color_pair(0))
                y -= 1
            self.win_chat.noutrefresh()
            if not norefresh:
                self.need_update.set()
        except curses.error:
            # exception will happen when window is resized to smaller w dimensions
            if not self.disable_drawing:
                self.resize()


    def draw_tree(self):
        """Draw channel tree"""
        try:
            h, w = self.tree_hw
            # drawinf from top to down
            skipped = 0   # skipping drop-down ends (code 1000)
            drop_down_skip_guild = False
            drop_down_skip_category = False
            drop_down_skip_channel = False
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
                elif code == 1300:
                    skipped += 1
                    drop_down_level -= 1
                    drop_down_skip_channel = False
                    continue
                text_start = drop_down_level * 3 + 1
                if code < 300 or 500 <= code <= 599:
                    drop_down_level += 1
                if drop_down_skip_guild or drop_down_skip_category or drop_down_skip_channel:
                    skipped += 1
                    continue
                self.tree_clean_len += 1
                if first_digit == 0 and code < 200:
                    drop_down_skip_guild = True
                elif first_digit == 0 and code < 300:
                    drop_down_skip_category = True
                elif first_digit == 0 and 500 <= code <= 599:
                    drop_down_skip_channel = True
                y = max(num - skipped - self.tree_index, 0)
                if y >= h:
                    break
                second_digit = (code % 100) // 10
                color = curses.color_pair(3)
                color_line = curses.color_pair(3)
                selected = False
                if second_digit == 1:   # muted
                    color = curses.color_pair(5) | self.attrib_map[5]
                elif second_digit == 2:   # mentioned
                    color = curses.color_pair(8) | self.attrib_map[8]
                elif second_digit == 3:   # unread
                    color = curses.color_pair(7) | self.attrib_map[7]
                elif second_digit == 4:   # active
                    color = curses.color_pair(6) | self.attrib_map[6]
                    color_line = curses.color_pair(6)
                elif second_digit == 5:   # active mentioned
                    color = curses.color_pair(9) | self.attrib_map[9]
                    color_line = curses.color_pair(6)
                if y == self.tree_selected - self.tree_index:   # selected
                    color = curses.color_pair(4) | self.attrib_map[4]
                    color_line = curses.color_pair(4)
                    self.tree_selected_abs = self.tree_selected + skipped
                    selected = True
                # filled with spaces so background is drawn all the way
                self.win_tree.insstr(y, 0, " " * w + "\n", color_line)
                self.win_tree.insstr(y, 0, line[:text_start], color_line)
                self.win_tree.insstr(y, text_start, line[text_start:], color)
                # if this is dm, set color for status sign
                # drawing it only for "normal" DMs, just to save some color pairs until python curses fixes the bug
                if 300 <= code < 399 and second_digit == 0 and not selected:
                    if first_digit == 2:   # online
                        # this character is always at position 4 (set in formatter)
                        self.win_tree.addch(y, 4, self.tree_dm_status, curses.color_pair(18))
                    elif first_digit == 3:   # idle
                        self.win_tree.addch(y, 4, self.tree_dm_status, curses.color_pair(19))
                    elif first_digit == 4:   # dnd
                        self.win_tree.addch(y, 4, self.tree_dm_status, curses.color_pair(20))
            y += 1
            while y < h:
                self.win_tree.insstr(y, 0, "\n", curses.color_pair(1))
                y += 1
            self.win_tree.noutrefresh()
            self.need_update.set()
        except curses.error:
            # this exception will happen when window is resized to smaller h dimensions
            self.resize()


    def draw_extra_line(self, text=None, toggle=False):
        """
        Draw extra line above status line and resize chat.
        If toggle and same text is repeated then remve extra line.
        """
        if toggle and text == self.extra_line_text:
            self.remove_extra_line()
            return
        self.extra_line_text = text
        if text and not self.disable_drawing:
            h, w = self.screen.getmaxyx()
            if not self.win_extra_line:
                del self.win_chat
                chat_hwyx = (
                    h - 3 - int(self.have_title),
                    w - (self.tree_width + 1),
                    int(self.have_title),
                    self.tree_width + 1,
                )
                self.win_chat = self.screen.derwin(*chat_hwyx)
                self.chat_hw = self.win_chat.getmaxyx()
                if not self.member_list:
                    self.draw_chat(norefresh=True)
                extra_line_hwyx = (1, w - (self.tree_width + 1), h - 3, self.tree_width + 1)
                self.win_extra_line = self.screen.derwin(*extra_line_hwyx)
                self.draw_member_list(self.member_list, self.member_list_format, force=True)
            self.win_extra_line.insstr(0, 0, text + " " * (w - len(text)) + "\n", curses.color_pair(11) | self.attrib_map[11])
            self.win_extra_line.noutrefresh()
            self.need_update.set()


    def remove_extra_line(self):
        """Disable drawing of extra line above status line, and resize chat"""
        if self.win_extra_line:
            del self.win_chat
            self.extra_line_text = ""
            self.win_extra_line = None
            h, w = self.screen.getmaxyx()
            chat_hwyx = (h - 2 - int(self.have_title), w - (self.tree_width + 1), int(self.have_title), self.tree_width + 1)
            self.win_chat = self.screen.derwin(*chat_hwyx)
            self.chat_hw = self.win_chat.getmaxyx()
            if not self.member_list:
                self.draw_chat()
            self.draw_member_list(self.member_list, self.member_list_format, force=True)


    def draw_extra_window(self, title_text, body_text, select=False, start_zero=False):
        """
        Draw extra window above status line and resize chat.
        title_text is string, body_text is list.
        """
        self.extra_select = select
        self.extra_window_title = title_text
        self.extra_window_body = body_text
        if start_zero:
            self.extra_index = 0
            self.extra_selected = 0
        if title_text and not self.disable_drawing:
            h, w = self.screen.getmaxyx()
            if not self.win_extra_window:
                del self.win_chat
                self.win_extra_line = None
                chat_hwyx = (
                    h - 3 - int(self.have_title) - self.extra_window_h,
                    w - (self.tree_width + 1),
                    int(self.have_title),
                    self.tree_width + 1,
                )
                self.win_chat = self.screen.derwin(*chat_hwyx)
                self.chat_hw = self.win_chat.getmaxyx()
                if not self.member_list:
                    self.draw_chat(norefresh=True)
                extra_window_hwyx = (
                    self.extra_window_h + 1,
                    w - (self.tree_width + 1),
                    h - 3 - self.extra_window_h,
                    self.tree_width + 1,
                )
                self.win_extra_window = self.screen.derwin(*extra_window_hwyx)
                self.draw_member_list(self.member_list, self.member_list_format, force=True)
            self.win_extra_window.insstr(0, 0, title_text + " " * (w - len(title_text)) + "\n", curses.color_pair(11) | self.attrib_map[11])
            h = self.win_extra_window.getmaxyx()[0]
            y = 0
            for num, line in enumerate(body_text):
                y = max(num - self.extra_index, 0)
                if y + 1 >= h:
                    break
                if y >= 0:
                    if num == self.extra_selected:
                        self.win_extra_window.insstr(y + 1, 0, line + " " * (w - len(line)) + "\n", curses.color_pair(11) | self.attrib_map[11])
                    else:
                        self.win_extra_window.insstr(y + 1, 0, line + " " * (w - len(line)) + "\n", curses.color_pair(21) | self.attrib_map[21])
            y += 2
            while y < h:
                self.win_extra_window.insstr(y, 0, "\n", curses.color_pair(1))
                y += 1
            self.win_extra_window.noutrefresh()
            self.need_update.set()


    def remove_extra_window(self):
        """Disable drawing of extra window above status line, and resize chat"""
        if self.win_extra_window:
            del (self.win_extra_window, self.win_chat)
            self.extra_window_title = ""
            self.extra_window_body = ""
            self.win_extra_window = None
            h, w = self.screen.getmaxyx()
            chat_hwyx = (h - 2 - int(self.have_title), w - (self.tree_width + 1), int(self.have_title), self.tree_width + 1)
            self.win_chat = self.screen.derwin(*chat_hwyx)
            self.chat_hw = self.win_chat.getmaxyx()
            if not self.member_list:
                self.draw_chat()
            self.draw_extra_line(self.extra_line_text)
            self.draw_member_list(self.member_list, self.member_list_format, force=True)


    def draw_member_list(self, member_list, member_list_format, force=False):
        """Draw member list and resize chat"""
        self.member_list = member_list
        self.member_list_format = member_list_format
        if member_list and not self.disable_drawing:
            h, w = self.screen.getmaxyx()
            if not self.win_member_list or force:
                if not force and self.win_member_list:
                    self.mlist_selected = -1
                    self.mlist_index = 0
                if self.win_extra_window:
                    common_h = h - 3 - int(self.have_title) - self.extra_window_h
                elif self.win_extra_line:
                    common_h = h - 3 - int(self.have_title)
                else:
                    common_h = h - 2 - int(self.have_title)
                chat_hwyx = (
                    common_h,
                    w - (self.tree_width + 1) - (self.member_list_width + 1),
                    int(self.have_title),
                    self.tree_width + 1,
                )
                self.win_chat = self.screen.derwin(*chat_hwyx)
                self.chat_hw = self.win_chat.getmaxyx()
                self.draw_chat(norefresh=True)
                member_list_hwyx = (
                    common_h,
                    self.member_list_width,
                    int(self.have_title),
                    w - self.member_list_width,
                )
                self.win_member_list = self.screen.derwin(*member_list_hwyx)
                self.screen.vline(int(self.have_title), w - self.member_list_width - 1, self.vert_line, common_h)
                self.screen.noutrefresh()
            h, w = self.win_member_list.getmaxyx()
            y = 0
            for num, line in enumerate(member_list):
                y =  max(num - self.mlist_index, 0)
                if y >= h:
                    break
                line_format = member_list_format[num]
                if num == self.mlist_selected:
                    self.win_member_list.insstr(y, 0, line + " " * (w - len(line)) + "\n", curses.color_pair(4) | self.attrib_map[4])
                else:
                    for pos, character in enumerate(line + " " * (w - len(line)) + "\n"):
                        if pos >= w:
                            break
                        for format_part in line_format:
                            if format_part[1] <= pos < format_part[2]:
                                color = format_part[0]
                                if color > 255:   # set all colors after 255 to default color
                                    color = self.color_default
                                color_ready = curses.color_pair(color) | self.attrib_map[color]
                                safe_insch(self.win_member_list, y, pos, character, color_ready)
                                break
                        else:
                            safe_insch(self.win_member_list, y, pos, character, curses.color_pair(self.color_default) | self.attrib_map[self.color_default])
            y += 1
            while y < h:
                self.win_member_list.insstr(y, 0, "\n", curses.color_pair(1))
                y += 1
            self.win_member_list.noutrefresh()
            self.need_update.set()


    def remove_member_list(self):
        """Remove member list and resize chat"""
        if self.win_member_list:
            del (self.win_member_list, self.win_chat)
            self.member_list = []
            self.member_list_format = []
            self.win_member_list = None
            h, w = self.screen.getmaxyx()
            chat_hwyx = (h - 2 - int(self.have_title), w - (self.tree_width + 1), int(self.have_title), self.tree_width + 1)
            self.win_chat = self.screen.derwin(*chat_hwyx)
            self.chat_hw = self.win_chat.getmaxyx()
            if self.win_extra_line:
                chat_hwyx = (
                    h - 3 - int(self.have_title),
                    w - (self.tree_width + 1),
                    int(self.have_title),
                    self.tree_width + 1,
                )
                self.win_chat = self.screen.derwin(*chat_hwyx)
                self.chat_hw = self.win_chat.getmaxyx()
            elif self.win_extra_window:
                chat_hwyx = (
                    h - 3 - int(self.have_title) - self.extra_window_h,
                    w - (self.tree_width + 1),
                    int(self.have_title),
                    self.tree_width + 1,
                )
                self.win_chat = self.screen.derwin(*chat_hwyx)
                self.chat_hw = self.win_chat.getmaxyx()
            self.draw_chat()


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
            self.win_input_line.insch(0, self.cursor_pos, character, curses.color_pair(color_id) | self.attrib_map[color_id])
        else:
            self.win_input_line.addch(0, self.cursor_pos, character, curses.color_pair(color_id) | self.attrib_map[color_id])
        self.win_input_line.noutrefresh()
        self.need_update.set()


    def blink_cursor(self):
        """Thread that makes cursor blink, hibernates after some time"""
        self.hibernate_cursor = 0
        while self.run:
            while self.run and self.hibernate_cursor >= 10:
                time.sleep(self.blink_cursor_on)
            if self.cursor_on:
                color_id = 14
                sleep_time = self.blink_cursor_on
            else:
                color_id = 15
                sleep_time = self.blink_cursor_off
            self.set_cursor_color(color_id)
            time.sleep(sleep_time)
            self.hibernate_cursor += 1
            self.cursor_on = not self.cursor_on


    def show_cursor(self):
        """Force cursor to be shown on screen and reset blinking"""
        if self.enable_blink_cursor:
            self.set_cursor_color(15)
            self.cursor_on = True
            self.hibernate_cursor = 0


    def lock_ui(self, lock):
        """Turn ON/OFF main TUI drawing"""
        self.disable_drawing = lock
        if lock:
            self.hibernate_cursor = 10
        else:
            self.screen.clear()
            self.redraw_ui()


    def update_status_line(self, text_l, text_r=None):
        """Update status text"""
        redraw = False
        if text_l != self.status_txt_l:
            self.status_txt_l = text_l
            redraw = True
        if text_r != self.status_txt_r:
            self.status_txt_r = text_r
            redraw = True
        if redraw and not self.disable_drawing:
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
            if redraw and not self.disable_drawing:
                self.draw_title_line()


    def update_title_tree(self, text):
        """Update status text"""
        if self.have_title_tree and text != self.title_tree_txt:
            self.title_tree_txt = text
            if not self.disable_drawing:
                self.draw_title_tree()


    def update_chat(self, chat_text, chat_format):
        """Update text buffer"""
        self.chat_buffer = chat_text
        self.chat_format = chat_format
        if not self.disable_drawing:
            self.draw_chat()


    def update_tree(self, tree_text, tree_format):
        """Update channel tree"""
        self.tree = tree_text
        self.tree_format = tree_format
        if not self.disable_drawing:
            self.draw_tree()
        self.tree_format_changed = True


    def update_prompt(self, prompt):
        """Draw prompt line and resize input line"""
        self.prompt = prompt
        if not self.disable_drawing:
            h, w = self.screen.getmaxyx()
            del (self.win_prompt, self.win_input_line)
            input_line_hwyx = (1, w - (self.tree_width + 1) - len(self.prompt), h - 1, self.tree_width + len(self.prompt) + 1)
            self.win_input_line = self.screen.derwin(*input_line_hwyx)
            self.input_hw = self.win_input_line.getmaxyx()
            self.spellcheck()
            self.draw_input_line()
            prompt_hwyx = (1, len(self.prompt), h - 1, self.tree_width + 1)
            self.win_prompt = self.screen.derwin(*prompt_hwyx)
            self.win_prompt.insstr(0, 0, self.prompt, curses.color_pair(13) | self.attrib_map[13])
            self.win_prompt.noutrefresh()
            self.need_update.set()


    def init_pair(self, color, force_id=None):
        """Initialize color pair while keeping track of last unused id, and store its attribute in attr_map"""
        if len(color) == 2:
            fg, bg = color
            attribute = 0
        else:
            fg, bg, attribute = color
            attribute = str(attribute).lower()
            if attribute in ("b", "bold"):
                attribute = curses.A_BOLD
            elif attribute in ("u", "underline"):
                attribute = curses.A_UNDERLINE
            elif attribute in ("i", "italic"):
                attribute = curses.A_ITALIC
            else:
                attribute = 0
        if force_id:
            curses.init_pair(force_id, fg, bg)
            self.color_cache = set_list_item(self.color_cache, (fg, bg), force_id)
            self.attrib_map = set_list_item(self.attrib_map, attribute, force_id)
        else:
            curses.init_pair(self.last_free_id, fg, bg)
            self.color_cache.append((fg, bg))
            self.attrib_map.append(attribute)
        self.last_free_id += 1
        return self.last_free_id - 1


    def init_colors(self, colors):
        """Initialize multiple color pairs"""
        color_codes = []
        for color in colors:
            pair_id = self.init_pair(color)
            color_codes.append(pair_id)
        self.color_default = color_codes[0]
        self.role_color_start_id = self.last_free_id
        return color_codes


    def init_colors_formatted(self, colors, alt_color):
        """Initialize multiple color pairs in double nested lists twice, one wih normal color and one bg from with alt_color"""
        color_codes = []
        for format_colors in colors:
            format_codes = []
            for color in format_colors:
                pair_id = self.init_pair(color[:3])
                format_codes.append([pair_id, *color[3:]])
            color_codes.append(format_codes)
        # using bg from alt_color
        for format_colors in colors:
            format_codes = []
            for num, color in enumerate(format_colors):
                if num == 0:
                    color[1] = alt_color[1]
                if color[1] == -2:
                    color[1] = format_colors[0][1]
                    color[1] = alt_color[1]
                pair_id = self.init_pair(color[:3])
                format_codes.append([pair_id, *color[3:]])
            color_codes.append(format_codes)
        self.role_color_start_id = self.last_free_id
        return color_codes


    def init_role_colors(self, all_roles, bg, alt_bg, guild_id=None):
        """Initialize 2 pairs of role colors for different backgrounds, for all or specific guild"""
        if guild_id:
            selected_id = self.role_color_start_id
        else:
            selected_id = None
        for guild in all_roles:
            if guild_id:
                if guild["guild_id"] != guild_id:
                    continue
            for role in guild["roles"]:
                color = role["ansi"]
                found = False
                for guild_i in all_roles:
                    for role_i in guild_i["roles"]:
                        if "color_id" not in role_i:
                            break
                        if role_i["ansi"] == color:
                            role["color_id"] = role_i["color_id"]
                            role["alt_color_id"] = role_i["alt_color_id"]
                            found = True
                            break
                    if found:
                        break
                else:
                    pair_id = self.init_pair((color, bg, selected_id))
                    role["color_id"] = pair_id
                    pair_id = self.init_pair((color, alt_bg, selected_id))
                    role["alt_color_id"] = pair_id
                    if guild_id:
                        selected_id += 1
            if guild_id:
                break
        return all_roles


    def restore_colors(self):
        """Re-initialize cached colors"""
        for num, color in enumerate(self.color_cache):
            curses.init_pair(num + 1, *color)


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
            range_word_end = len(input_buffer) - len(input_buffer.split(" ")[-1]) - bool(" " in input_buffer)
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


    def add_to_delta_store(self, key, character=None):
        """Add input line delta to delta_store"""
        if key not in ("BACKSPACE", "DELETE", " ", "UNDO", "REDO"):
            action = "ADD"
        elif key == " ":
            action = "SPACE"
        else:
            action = key

        # clear future history when undo/redo then edit
        if self.last_action != action and ((self.last_action == "UNDO" and action != "REDO") or (self.last_action == "REDO" and action != "UNDO")):
            self.delta_store = self.delta_store[:self.undo_index]

        # add delta_cache to delta_store
        if self.last_action != action or abs(self.input_index - self.delta_index) >= 2:
            # checking index change for case when cursor is moved
            if self.delta_cache and (self.last_action != "SPACE" or (action not in ("ADD", "BACKSPACE", "DELETE"))):
                if self.last_action == "SPACE":
                    # space is still adding text
                    self.delta_store.append([self.delta_index - 1, self.delta_cache, "ADD"])
                else:
                    self.delta_store.append([self.delta_index - 1, self.delta_cache, self.last_action])
                if len(self.delta_store) > MAX_DELTA_STORE:
                    # limit history size
                    del self.delta_store[0]
                self.delta_cache = ""
            self.last_action = action

        # add to delta_cache
        if action == "BACKSPACE" and character:
            self.delta_cache = character + self.delta_cache
            self.delta_index = self.input_index
            self.undo_index = None
        elif action == "DELETE" and character:
            self.delta_cache += character
            self.delta_index = self.input_index
            self.undo_index = None
        elif action in ("ADD", "SPACE"):
            self.delta_cache += key
            self.delta_index = self.input_index
            self.undo_index = None


    def delete_selection(self):
        """Delete selected text in input line and add it to undo history"""
        input_select_start, input_select_end = self.store_input_selected()
        # delete selection
        self.input_buffer = self.input_buffer[:input_select_start] + self.input_buffer[input_select_end:]
        # add selection to undo history as backspace
        self.input_index = input_select_end
        for letter in self.input_select_text[::-1]:
            self.input_index -= 1
            self.add_to_delta_store("BACKSPACE", letter)


    def common_keybindings(self, key):
        """Handle keybinding events that are common for all buffers"""
        if key == curses.KEY_UP:   # UP
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

        elif key in self.keybindings["tree_up"]:
            if self.tree_selected >= 0:
                if self.tree_index and self.tree_selected <= self.tree_index + 2:
                    self.tree_index -= 1
                self.tree_selected -= 1
                self.draw_tree()

        elif key in self.keybindings["tree_down"]:
            if self.tree_selected + 1 < self.tree_clean_len:
                top_line = self.tree_index + self.tree_hw[0]
                if top_line < self.tree_clean_len and self.tree_selected >= top_line - 3:
                    self.tree_index += 1
                self.tree_selected += 1
                self.draw_tree()

        elif key in self.keybindings["tree_select"]:
            # if selected tree entry is channel
            if 300 <= self.tree_format[self.tree_selected_abs] <= 399:
                # stop wait_input and return so new prompt can be loaded
                return 4
            # if selected tree entry is dms drop down
            if self.tree_selected_abs == 0:   # for dms
                if (self.tree_format[self.tree_selected_abs] % 10):
                    self.tree_format[self.tree_selected_abs] -= 1
                else:
                    self.tree_format[self.tree_selected_abs] += 1
                self.draw_tree()
            # if selected tree entry is guild drop-down
            elif 100 <= self.tree_format[self.tree_selected_abs] <= 199:
                # this will trrigger open_guild() in app.py that will update and expand tree
                return 19
            # if selected tree entry is threads drop-down
            elif 400 <= self.tree_format[self.tree_selected_abs] <= 599:
                # stop wait_input and return so new prompt can be loaded
                return 4
            # if selected tree entry is category drop-down
            elif self.tree_selected_abs >= 0:
                if (self.tree_format[self.tree_selected_abs] % 10):
                    self.tree_format[self.tree_selected_abs] -= 1
                else:
                    self.tree_format[self.tree_selected_abs] += 1
                self.draw_tree()
            self.tree_format_changed = True

        elif key in self.keybindings["tree_collapse_threads"]:
            if (self.tree_format[self.tree_selected_abs] % 10):
                self.tree_format[self.tree_selected_abs] -= 1
            else:
                self.tree_format[self.tree_selected_abs] += 1
            self.draw_tree()

        elif key in self.keybindings["tree_join_thread"]:
            return 21

        elif key in self.keybindings["extra_up"]:
            if self.extra_window_body:
                if self.extra_select and self.extra_selected >= 0:
                    if self.extra_index and self.extra_selected <= self.extra_index:
                        self.extra_index -= 1
                    self.extra_selected -= 1
                    self.draw_extra_window(self.extra_window_title, self.extra_window_body, self.extra_select)
                elif self.extra_index > 0:
                    self.extra_index -= 1
                    self.draw_extra_window(self.extra_window_title, self.extra_window_body, self.extra_select)
            elif self.win_member_list:
                if self.mlist_selected >= 0:
                    if self.mlist_index and self.mlist_selected <= self.mlist_index:
                        self.mlist_index -= 1
                    self.mlist_selected -= 1
                    self.draw_member_list(self.member_list, self.member_list_format)
                elif self.mlist_index > 0:
                    self.mlist_index -= 1
                    self.draw_member_list(self.member_list, self.member_list_format)

        elif key in self.keybindings["extra_down"]:
            if self.extra_window_body:
                if self.extra_select:
                    if self.extra_selected + 1 < len(self.extra_window_body):
                        top_line = self.extra_index + self.win_extra_window.getmaxyx()[0] - 1
                        if top_line < len(self.extra_window_body) and self.extra_selected >= top_line - 1:
                            self.extra_index += 1
                        self.extra_selected += 1
                        self.draw_extra_window(self.extra_window_title, self.extra_window_body, self.extra_select)
                elif self.extra_index + 1 < len(self.extra_window_body):
                    self.extra_index += 1
                    self.draw_extra_window(self.extra_window_title, self.extra_window_body, self.extra_select)
            elif self.win_member_list:
                if self.mlist_selected + 1 < len(self.member_list):
                    top_line = self.mlist_index + self.win_member_list.getmaxyx()[0] - 1
                    if top_line < len(self.member_list) and self.mlist_selected >= top_line - 1:
                        self.mlist_index += 1
                    self.mlist_selected += 1
                    self.draw_member_list(self.member_list, self.member_list_format)

        elif self.extra_select and key == self.keybindings["extra_select"]:
            return 27

        elif key in self.keybindings["channel_info"] and self.tree_selected > 0:
            self.extra_index = 0
            self.extra_selected = -1
            return 25

        elif key in self.keybindings["hide_channel"]:
            return 26

        elif key in self.keybindings["cycle_status"]:
            return 33

        elif key in self.keybindings["toggle_member_list"]:
            return 35

        elif key in self.keybindings["command"]:
            return 38

        return None


    def return_input_code(self, code):
        """Clean input line and return input code wit other data"""
        tmp = self.input_buffer
        self.input_buffer = ""
        return tmp, self.chat_selected, self.tree_selected_abs, code


    def wait_input(self, prompt="", init_text=None, reset=True, keep_cursor=False, scroll_bot=False, autocomplete=False, clear_delta=False):
        """
        Take input from user, and show it on screen
        Return typed text, absolute_tree_position and whether channel is changed
        """
        if reset:
            self.input_buffer = ""
            self.input_index = 0
            self.input_line_index = 0
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
        if not self.disable_drawing:
            self.spellcheck()
            self.update_prompt(prompt)   # draw_input_line() is called in heren
        if clear_delta:
            self.delta_store = []
            self.last_key = None
            self.delta_cache = ""
            self.undo_index = None
        bracket_paste = False
        selected_completion = 0
        self.keybinding_chain = None
        key = -1
        while self.run:
            key = self.screen.getch()

            w = self.input_hw[1]
            if self.disable_drawing:
                if key == 27:   # ESCAPE
                    self.screen.nodelay(True)
                    key = self.screen.getch()
                    if key in (-1, 27):
                        self.input_buffer = ""
                        self.screen.nodelay(False)
                        return None, 0, 0, 100
                    self.screen.nodelay(False)
                elif key in self.keybindings["media_pause"]:
                    return None, 0, 0, 101
                elif key in self.keybindings["media_replay"]:
                    return None, 0, 0, 102
                elif key in self.keybindings["media_seek_forward"]:
                    return None, 0, 0, 103
                elif key in self.keybindings["media_seek_backward"]:
                    return None, 0, 0, 104
                elif key in self.keybindings["redraw"]:
                    return None, 0, 0, 105
                elif key == curses.KEY_RESIZE:
                    pass
                continue   # disable all inputs from main UI

            if key == 27:   # ESCAPE
                # terminal waits when Esc is pressed, but not when sending escape sequence
                self.screen.nodelay(True)
                key = self.screen.getch()
                if key == -1:
                    # escape key
                    self.screen.nodelay(False)
                    if self.assist_start:
                        self.assist_start = -1
                    return self.return_input_code(5)
                # sequence (bracketed paste or ALT+KEY)
                sequence = [27, key]
                # -1 means no key is pressed, 126 is end of escape sequence
                while key != -1:
                    key = self.screen.getch()
                    sequence.append(key)
                    if key == 126:
                        break
                    if key == 27:   # holding escape key
                        sequence.append(-1)
                        break
                self.screen.nodelay(False)
                # match sequences
                if len(sequence) == 3 and sequence[2] == -1:   # ALT+KEY
                    key = f"ALT+{sequence[1]}"
                elif sequence == [27, 91, 50, 48, 48, 126]:
                    bracket_paste = True
                    continue
                elif sequence == [27, 91, 50, 48, 49, 126]:
                    bracket_paste = False
                    continue
                elif sequence[-1] == -1 and sequence[-2] == 27:
                    # holding escape key
                    if self.assist_start:
                        self.assist_start = -1
                    return self.return_input_code(5)

            # handle chained keybindings
            if key in self.chainable and not self.keybinding_chain:
                self.keybinding_chain = key
                continue
            if self.keybinding_chain:
                key = f"{self.keybinding_chain}-{key}"
                self.keybinding_chain = None

            if key == 10:   # ENTER
                # wehen pasting, dont return, but insert newline character
                if bracket_paste:
                    self.input_buffer = self.input_buffer[:self.input_index] + "\n" + self.input_buffer[self.input_index:]
                    self.input_index += 1
                    self.add_to_delta_store("\n")
                    pass
                else:
                    self.cursor_on = True
                    self.input_select_start = None
                    return self.return_input_code(0)

            code = self.common_keybindings(key)
            if code:
                return self.return_input_code(code)

            if isinstance(key, int) and 32 <= key <= 126:   # all regular characters
                if self.input_select_start is not None:
                    self.delete_selection()
                    self.input_select_start = None
                self.input_buffer = self.input_buffer[:self.input_index] + chr(key) + self.input_buffer[self.input_index:]
                self.input_index += 1
                self.typing = int(time.time())
                if self.enable_autocomplete:
                    completion_base = self.input_buffer
                    selected_completion = 0
                self.add_to_delta_store(chr(key))
                self.show_cursor()
                if self.assist:
                    if chr(key) in ASSIST_TRIGGERS:
                        self.assist_start = self.input_index

            elif key == BACKSPACE:
                if self.input_select_start is not None:
                    self.delete_selection()
                    self.input_select_start = None
                elif self.input_index > 0:
                    removed_char = self.input_buffer[self.input_index-1]
                    self.input_buffer = self.input_buffer[:self.input_index-1] + self.input_buffer[self.input_index:]
                    self.input_index -= 1
                    if self.enable_autocomplete:
                        completion_base = self.input_buffer
                        selected_completion = 0
                    self.add_to_delta_store("BACKSPACE", removed_char)
                    self.show_cursor()

            elif key == curses.KEY_DC:   # DEL
                if self.input_select_start is not None:
                    self.delete_selection()
                    self.input_select_start = None
                elif self.input_index < len(self.input_buffer):
                    removed_char = self.input_buffer[self.input_index]
                    self.input_buffer = self.input_buffer[:self.input_index] + self.input_buffer[self.input_index+1:]
                    self.add_to_delta_store("DELETE", removed_char)
                    self.show_cursor()

            elif key == curses.KEY_LEFT:
                if self.input_index > 0:
                    # if index hits left screen edge, but there is more text to left, move line right
                    if self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index) == 0:
                        self.input_line_index += min(INPUT_LINE_JUMP, w - 3)
                    else:
                        self.input_index -= 1
                    self.show_cursor()
                self.input_select_start = None

            elif key == curses.KEY_RIGHT:
                if self.input_index < len(self.input_buffer):
                    # if index hits right screen edge, but there is more text to right, move line right
                    if self.input_index - max(0, len(self.input_buffer) - w - self.input_line_index) == w:
                        self.input_line_index -= min(INPUT_LINE_JUMP, w - 3)
                    else:
                        self.input_index += 1
                    self.show_cursor()
                self.input_select_start = None

            elif key == curses.KEY_HOME:
                self.input_index = 0
                self.input_line_index = 0
                self.input_select_start = None

            elif key == curses.KEY_END:
                self.input_index = len(self.input_buffer)
                self.input_select_start = None

            elif key in self.keybindings["word_left"]:
                left_len = 0
                for word in self.input_buffer[:self.input_index].split(" ")[::-1]:
                    if word == "":
                        left_len += 1
                    else:
                        left_len += len(word)
                        break
                self.input_index -= left_len
                self.input_index = max(self.input_index, 0)
                self.input_select_start = None

            elif key in self.keybindings["word_right"]:
                left_len = 0
                for word in self.input_buffer[self.input_index:].split(" "):
                    if word == "":
                        left_len += 1
                    else:
                        left_len += len(word)
                        break
                self.input_index += left_len
                self.input_index = min(self.input_index, len(self.input_buffer))
                self.input_select_start = None

            elif key in self.keybindings["select_word_left"]:
                if self.input_select_start is None:
                    self.input_select_end = self.input_select_start = self.input_index
                left_len = 0
                for word in self.input_buffer[:self.input_index].split(" ")[::-1]:
                    if word == "":
                        left_len += 1
                    else:
                        left_len += len(word)
                        break
                self.input_index -= left_len
                self.input_index = max(self.input_index, 0)
                if self.input_select_start is not None:
                    self.input_select_end -= left_len

            elif key in self.keybindings["select_word_right"]:
                if self.input_select_start is None:
                    self.input_select_end = self.input_select_start = self.input_index
                left_len = 0
                for word in self.input_buffer[self.input_index:].split(" "):
                    if word == "":
                        left_len += 1
                    else:
                        left_len += len(word)
                        break
                self.input_index += left_len
                self.input_index = min(self.input_index, len(self.input_buffer))
                if self.input_select_start is not None:
                    self.input_select_end += left_len

            elif key in self.keybindings["undo"]:
                self.add_to_delta_store("UNDO")
                if self.undo_index is None:
                    self.undo_index = len(self.delta_store) - 1
                    undo = True
                elif self.undo_index > 0:
                    self.undo_index -= 1
                    undo = True   # dont undo if hit history end
                if undo and self.undo_index >= 0:
                    # get delta
                    delta_index, delta_text, delta_code = self.delta_store[self.undo_index]
                    if delta_code == "ADD":
                        # remove len(delta_text) before index_pos
                        self.input_buffer = self.input_buffer[:delta_index - len(delta_text) + 1] + self.input_buffer[delta_index + 1:]
                        self.input_index = delta_index - len(delta_text) + 1
                    elif delta_code == "BACKSPACE":
                        # add text at index pos
                        self.input_buffer = self.input_buffer[:delta_index+1] + delta_text + self.input_buffer[delta_index+1:]
                        self.input_index = delta_index + len(delta_text) + 1
                    elif delta_code == "DELETE":
                        # add text at index pos
                        self.input_buffer = self.input_buffer[:delta_index+1] + delta_text + self.input_buffer[delta_index+1:]
                        self.input_index = delta_index + 1
                self.input_select_start = None

            elif key in self.keybindings["redo"]:
                self.add_to_delta_store("REDO")
                if self.undo_index is not None and self.undo_index < len(self.delta_store):
                    self.undo_index += 1
                    # get delta
                    delta_index, delta_text, delta_code = self.delta_store[self.undo_index - 1]
                    if delta_code == "ADD":
                        # add text at index_pos - len(text)
                        delta_index = delta_index - len(delta_text) + 1
                        self.input_buffer = self.input_buffer[:delta_index] + delta_text + self.input_buffer[delta_index:]
                        self.input_index = delta_index + len(delta_text)
                    elif delta_code in ("BACKSPACE", "DELETE"):
                        # remove len(text) after index pos
                        self.input_buffer = self.input_buffer[:delta_index + 1] + self.input_buffer[delta_index + len(delta_text) + 1:]
                        self.input_index = delta_index + 1
                self.input_select_start = None

            elif key in self.keybindings["select_left"]:
                if self.input_select_start is None:
                    self.input_select_start = self.input_index
                if self.input_index > 0:
                    # if index hits left screen edge, but there is more text to left, move line right
                    if self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index) == 0:
                        self.input_line_index += min(INPUT_LINE_JUMP, w - 3)
                    else:
                        self.input_index -= 1
                self.input_select_end = self.input_index

            elif key in self.keybindings["select_right"]:
                if self.input_select_start is None:
                    self.input_select_start = self.input_index
                if self.input_index < len(self.input_buffer):
                    # if index hits right screen edge, but there is more text to right, move line right
                    if self.input_index - max(0, len(self.input_buffer) - w - self.input_line_index) == w:
                        self.input_line_index -= min(INPUT_LINE_JUMP, w - 3)
                    else:
                        self.input_index += 1
                self.input_select_end = self.input_index

            elif key in self.keybindings["select_all"]:
                self.input_select_start = 0
                self.input_select_end = len(self.input_buffer)

            elif self.input_select_start and key == self.keybindings["copy_sel"]:
                self.store_input_selected()
                return self.return_input_code(20)

            elif self.input_select_start and key == self.keybindings["cut_sel"]:
                self.delete_selection()
                return self.return_input_code(20)

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

            elif key in self.keybindings["attach_prev"]:
                return self.return_input_code(14)

            elif key in self.keybindings["attach_next"]:
                return self.return_input_code(15)

            elif key in self.keybindings["ins_newline"]:
                self.input_buffer = self.input_buffer[:self.input_index] + "\n" + self.input_buffer[self.input_index:]
                self.input_index += 1
                self.show_cursor()

            elif key in self.keybindings["reply"] and self.chat_selected != -1:
                return self.return_input_code(1)

            elif key in self.keybindings["edit"] and self.chat_selected != -1:
                return self.return_input_code(2)

            elif key in self.keybindings["delete"] and self.chat_selected != -1:
                return self.return_input_code(3)

            elif key in self.keybindings["toggle_ping"]:
                return self.return_input_code(6)

            elif key in self.keybindings["scroll_bottom"]:
                return self.return_input_code(7)


            elif key in self.keybindings["go_replied"] and self.chat_selected != -1:
                return self.return_input_code(8)

            elif key in self.keybindings["download"] and self.chat_selected != -1:
                return self.return_input_code(9)

            elif key in self.keybindings["browser"] and self.chat_selected != -1:
                return self.return_input_code(10)

            elif key in self.keybindings["cancel"]:
                return self.return_input_code(11)

            elif key in self.keybindings["copy_msg"]:
                return self.return_input_code(12)

            elif key in self.keybindings["upload"]:
                self.enable_autocomplete = True
                self.misspelled = []
                return self.return_input_code(13)

            elif key in self.keybindings["redraw"]:
                self.screen.clear()
                self.resize()

            elif key in self.keybindings["attach_cancel"]:
                return self.return_input_code(16)

            elif key in self.keybindings["view_media"] and self.chat_selected != -1:
                return self.return_input_code(17)

            elif key in self.keybindings["spoil"] and self.chat_selected != -1:
                return self.return_input_code(18)

            elif key in self.keybindings["profile_info"] and self.chat_selected != -1:
                self.extra_index = 0
                self.extra_selected = -1
                return self.return_input_code(24)

            elif key in self.keybindings["show_summaries"]:
                self.extra_index = 0
                self.extra_selected = -1
                return self.return_input_code(28)

            elif key in self.keybindings["search"]:
                self.extra_index = 0
                self.extra_selected = -1
                return self.return_input_code(29)

            elif key in self.keybindings["copy_channel_link"] and self.tree_selected > 0:
                return self.return_input_code(30)

            elif key in self.keybindings["copy_message_link"] and self.chat_selected != -1:
                return self.return_input_code(31)

            elif key in self.keybindings["go_channel"] and self.chat_selected != -1:
                return self.return_input_code(32)

            elif key in self.keybindings["record_audio"]:
                return self.return_input_code(34)

            elif key in self.keybindings["add_reaction"]:
                return self.return_input_code(36)

            elif key in self.keybindings["show_reactions"]:
                return self.return_input_code(37)

            elif key == curses.KEY_RESIZE:
                self.resize()
                _, w = self.input_hw

            # terminal reserved keys: CTRL+ C, I, J, M, Q, S, Z

            # keep index inside screen
            self.cursor_pos = self.input_index - max(0, len(self.input_buffer) - w + 1 - self.input_line_index)
            self.cursor_pos = max(self.cursor_pos, 0)
            self.cursor_pos = min(w - 1, self.cursor_pos)
            if not self.enable_autocomplete:
                self.spellcheck()
            if not self.disable_drawing:
                self.draw_input_line()
        return None, None, None, None


    def wait_input_forum(self, prompt=""):
        """
        Same as wait_input() but only for forums, does no process any text.
        Return absolute_tree_position and whether channel is changed
        """
        self.input_buffer = ""
        self.input_index = 0
        self.input_line_index = 0
        self.cursor_pos = 0
        self.enable_autocomplete = False
        self.chat_selected = -1
        self.chat_index = 0
        self.draw_chat()
        self.delta_store = []
        self.last_key = None
        self.delta_cache = ""
        self.update_prompt(prompt)   # draw_input_line() is called in heren
        key = -1
        while self.run:
            key = self.screen.getch()

            if self.disable_drawing:
                if key == 27:   # ESCAPE
                    self.screen.nodelay(True)
                    key = self.screen.getch()
                    if key in (-1, 27):
                        self.input_buffer = ""
                        self.screen.nodelay(False)
                        return None, 0, 0, 100
                    self.screen.nodelay(False)
                elif key == curses.KEY_RESIZE:
                    pass
                continue   # disable all inputs from main UI

            if key == 27:   # ESCAPE
                # terminal waits when Esc is pressed, but not when sending escape sequence
                self.screen.nodelay(True)
                key = self.screen.getch()
                if key == -1:
                    # escape key
                    self.screen.nodelay(False)
                    return self.return_input_code(5)
                # sequence (bracketed paste or ALT+KEY)
                sequence = [27, key]
                # -1 means no key is pressed, 126 is end of escape sequence
                while key != -1:
                    key = self.screen.getch()
                    sequence.append(key)
                    if key == 126:
                        break
                    if key == 27:   # holding escape key
                        sequence.append(-1)
                        break
                self.screen.nodelay(False)
                # match sequences
                if len(sequence) == 3 and sequence[2] == -1:   # ALT+KEY
                    key = f"ALT+{sequence[1]}"
                elif sequence[-1] == -1 and sequence[-2] == 27:
                    # holding escape key
                    return self.return_input_code(5)

            if key == 10:   # ENTER
                self.input_index = 0
                self.input_line_index = 0
                self.cursor_pos = 0
                self.cursor_on = True
                self.input_select_start = None
                self.draw_input_line()
                return self.return_input_code(22)

            code = self.common_keybindings(key)
            if code:
                return self.return_input_code(code)

            if key in self.keybindings["cancel"]:
                return self.return_input_code(11)

            if key in self.keybindings["forum_join_thread"]:
                return self.return_input_code(23)

            if key in self.keybindings["redraw"]:
                self.screen.clear()
                self.resize()

            elif key == curses.KEY_RESIZE:
                self.resize()

        return None, None, None, None
