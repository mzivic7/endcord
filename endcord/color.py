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


def check_color(color):
    """Check if color format is valid and repair it"""
    if color is None:
        return [-1, -1]
    if color[0] is None:
        color[0] = -1
    elif color[1] is None:
        color[1] = -1
    return color


def check_color_formatted(color_format):
    """
    Check if color format is valid and repair it.
    Replace -2 values for non-default colors with default for this format.
    """
    if color_format is None:
        return [[-1, -1]]
    for color in color_format[1:]:
        if color[0] == -2:
            color[0] = color_format[0][0]
    return color_format


def extract_colors(config):
    """Extract simple colors from config if any value is None, default is used"""
    return (
        check_color(config["color_default"]),
        check_color(config["color_chat_mention"]),
        check_color(config["color_chat_blocked"]),
        check_color(config["color_chat_deleted"]),
        check_color(config["color_chat_separator"]),
    )


def extract_colors_formatted(config):
    """Extract complex formatted colors from config"""
    return (
        check_color_formatted(config["color_format_message"]),
        check_color_formatted(config["color_format_newline"]),
        check_color_formatted(config["color_format_reply"]),
        check_color_formatted(config["color_format_reactions"]),
        # not complex but is here so it can be initialized for alt bg color
        [check_color(config["color_chat_edited"])],
        [check_color(config["color_chat_url"])],
        [check_color(config["color_chat_spoiler"])],
        check_color_formatted(config["color_format_forum"]),
    )


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
