# cython: boundscheck=False, wraparound=False, cdivision=True

from cpython.tuple cimport PyTuple_GET_ITEM
import pygame

cdef unsigned int A_STANDOUT   = 0x00010000
cdef unsigned int A_UNDERLINE  = 0x00020000
cdef unsigned int A_BOLD       = 0x00200000
cdef unsigned int A_ITALIC     = 0x80000000


cdef inline bint is_emoji(unicode ch):
    cdef int code = ord(ch)
    return (
        (0x1F300 <= code <= 0x1F9FF) or
        (0x2600 <= code <= 0x27BF) or
        (0x2300 <= code <= 0x23FF) or
        (0x2B00 <= code <= 0x2BFF)
    )


cdef inline object render_emoji_scaled(object emoji_font, unicode ch, int char_height):
    try:
        surf = emoji_font.render(ch, True, (255, 255, 255))
        return pygame.transform.smoothscale(surf, (char_height, char_height))
    except pygame.error:
        return None


cpdef insstr(
    list buffer,
    int nlines,
    int ncols,
    set dirty_lines,
    object dirty_lines_lock,
    int y,
    int x,
    unicode text,
    unsigned int attr=0
):
    cdef int i, j, row, col, line_len
    cdef unicode line, ch
    cdef str ready_line
    cdef object row_buffer
    cdef Py_ssize_t text_len
    cdef tuple cell

    cdef list lines = text.split('\n')
    cdef int len_lines = len(lines)

    for i, line in enumerate(lines):
        if i < len_lines - 1:
            line_len = ncols - x
            ready_line = (line[:line_len]).ljust(line_len)
        else:
            ready_line = line

        row = y + i
        if row >= nlines:
            break

        row_buffer = buffer[row]
        for j, ch in enumerate(ready_line[:ncols - x]):
            col = x + j
            cell = (ch, attr)
            row_buffer[col] = cell

        with dirty_lines_lock:
            dirty_lines.add(row)


# def insstr(self, y, x, text, attr=0):
#     """curses.insstr clone using pygame"""
#     insstr(
#         buffer=self.buffer,
#         nlines=self.nlines,
#         ncols=self.ncols,
#         dirty_lines=self.dirty_lines,
#         dirty_lines_lock=self.dirty_lines_lock,
#         y=y,
#         x=x,
#         text=text,
#         attr=attr,
#     )


cpdef render(
    object surface,
    list buffer,
    set dirty_lines,
    int ncols,
    int char_width,
    int char_height,
    object font,
    object emoji_font,
    list color_map,
):
    cdef int y, i, draw_x, px_x, px_y, span_draw_x
    cdef object row, ch, attr_obj, attr2_obj, emoji
    cdef unsigned int attr, attr2, flags
    cdef tuple fg, bg
    cdef list text_buffer
    cdef str text

    for y in dirty_lines:
        row = buffer[y]
        i = 0
        draw_x = 0
        while i < ncols:
            ch = <object>PyTuple_GET_ITEM(row[i], 0)
            attr_obj = <object>PyTuple_GET_ITEM(row[i], 1)
            attr = int(attr_obj)
            flags = attr & 0xFFFF0000

            if is_emoji(ch):
                px_x = draw_x * char_width
                px_y = y * char_height
                fg, bg = color_map[attr & 0xFFFF]
                if flags & A_STANDOUT:
                    fg, bg = bg, fg
                surface.fill(bg, (px_x, px_y, 2 * char_width, char_height))
                emoji = render_emoji_scaled(emoji_font, ch, char_height)
                if emoji:
                    offset = px_x + (2 * char_width - char_height) // 2
                    surface.blit(emoji, (offset, px_y))
                draw_x += 2   # emoji takes two cells visually
                i += 1   # but only one buffer cell
                continue

            span_draw_x = draw_x
            text_buffer = []
            while i < ncols:
                ch = <object>PyTuple_GET_ITEM(row[i], 0)
                attr2_obj = <object>PyTuple_GET_ITEM(row[i], 1)
                attr2 = int(attr2_obj)
                if attr2 != attr or is_emoji(ch):
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
            px_x = span_draw_x * char_width
            px_y = y * char_height
            surface.fill(bg, (px_x, px_y, len(text) * char_width, char_height))
            font.strong = bool(flags & A_BOLD)
            font.oblique = bool(flags & A_ITALIC)
            font.underline = bool(flags & A_UNDERLINE)
            font.render_to(surface, (px_x, px_y), text, fg)

    dirty_lines.clear()


# def render(self):
#     """Render buffer onto screen"""
#     with self.dirty_lines_lock:
#         render(
#             surface=self.surface,
#             buffer=self.buffer,
#             dirty_lines=self.dirty_lines,
#             ncols=self.ncols,
#             char_width=self.char_width,
#             char_height=self.char_height,
#             font=self.font,
#             emoji_font=self.emoji_font,
#             color_map=color_map,
#         )
