from math import sqrt

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
        distance = sqrt((r - r_i)**2 + (g - g_i)**2 + (b - b_i)**2)   # euclidean distance
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
