# cython: boundscheck=False, wraparound=False

import curses
cimport cython

cpdef void img_to_curses(
    object screen,
    object img,
    object img_gray,
    int start_color_id,
    list ascii_palette,
    int ascii_palette_len,
    int screen_width,
    int screen_height,
    int width,
    int height
):
    cdef int x, y, y_fill, padding_h, padding_w, color
    cdef object character
    cdef int gray_val

    cdef object pixels = img.load()
    cdef object pixels_gray = img_gray.load()

    padding_h = (screen_height - height) // 2
    padding_w = (screen_width - width) // 2
    bg_color = curses.color_pair(start_color_id + 1)

    # top padding
    for y_fill in range(padding_h):
        screen.insstr(y_fill, 0, " " * screen_width, bg_color)

    # image rows
    for y in range(height):
        row_y = y + padding_h

        # left padding
        if padding_w > 0:
            screen.insstr(row_y, 0, " " * padding_w, bg_color)

        for x in range(width):
            gray_val = pixels_gray[x, y]
            character = ascii_palette[(gray_val * ascii_palette_len) // 255]
            color = start_color_id + pixels[x, y] + 16
            screen.insch(row_y, x + padding_w, character, curses.color_pair(color))

        # right padding
        if x + padding_w + 1 < screen_width:
            screen.insstr(row_y, x + padding_w + 1, " " * (screen_width - (x + padding_w + 1)), bg_color)

    # bottom padding
    if screen_height != height:
        for y_fill in range(padding_h + 1):
            try:
                screen.insstr(screen_height - 1 - y_fill, 0, " " * screen_width, bg_color)
            except curses.error:
                pass

    screen.noutrefresh()
