import curses

from endcord import xterm256

pallete = xterm256.palette
colors = xterm256.colors


def argmin(values):
    """Return index of smallest value in a list"""
    return min(range(len(values)), key=values.__getitem__)


def closest_color(rgb):
    """
    Find closest 8bit xterm256 color to provided rgb color.
    Return ANSI code and rgb color.
    """
    r, g, b = rgb
    distances = []
    for color in colors:
        r_i, g_i, b_i = color
        distance = (r - r_i)**2 + (g - g_i)**2 + (b - b_i)**2
        distances.append((distance, color))
    index = argmin(distances)
    return index, distances[index][1]


def int_to_rgb(int_color):
    """Convert integer color string to rgb tuple"""
    b = int_color  & 255
    g = (int_color >> 8) & 255
    r = (int_color >> 16) & 255
    return (r, g, b)


def convert_role_colors(all_roles):
    """
    For all roles, in all guilds, convert integer color format into rgb tuple color and closest 8bit ANSI color code.
    If ANSI code is 0 (black).
    """
    for guild in all_roles:
        for role in guild["roles"]:
            rgb = int_to_rgb(role["color"])
            ansi = closest_color(rgb)[0]
            role["color"] = rgb
            role["ansi"] = ansi
    return all_roles


def show_all_colors(screen):
    """Show all available colors and their codes, wait for input, then exit"""
    curses.use_default_colors()
    for i in range(0, curses.COLORS):
        curses.init_pair(i, i, -1)
    screen.addstr(1, 1, "Press any key to close")
    h, w = screen.getmaxyx()
    x = 1
    y = 2
    for i in range(0, curses.COLORS):
        screen.addstr(y, x, str(i), curses.color_pair(i))
        x += 5
        if x + 3 > w:
            y += 1
            x = 1
        if y >= h:
            break
    screen.getch()
