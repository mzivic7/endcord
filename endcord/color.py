import math

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
        distance = math.sqrt((r - r_i)**2 + (g - g_i)**2 + (b - b_i)**2)   # euclidean distance
        distances.append((distance, color))
    index = argmin(distances)
    return index, distances[index][1]
