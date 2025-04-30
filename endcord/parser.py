import re
import time
from datetime import datetime, timedelta, timezone

DISCORD_EPOCH_MS = 1420070400000

match_from = re.compile(r"from:<@\d*>")
match_mentions = re.compile(r"mentions:<@\d*>")
match_has = re.compile(r"has:(?:link|embed|file|video|image|sound|sticker)")
match_before = re.compile(r"before:\d{4}-\d{2}-\d{2}")
match_after = re.compile(r"after:\d{4}-\d{2}-\d{2}")
match_in = re.compile(r"in:<#\d*>")
match_pinned = re.compile(r"pinned:(?:true|false)")

match_setting = re.compile(r"(\w+) ?= ?(.+)")


def date_to_snowflake(date, end=False):
    """Convert date to discord snowflake, rounded to day start, if end=True then is rounded to day end"""
    try:
        time_obj = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        time_obj = datetime.now()
        time_obj = time_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    time_obj = time_obj.replace(tzinfo=timezone.utc)
    if int(time_obj.timestamp()) > time.time():
        time_obj = datetime.now()
        time_obj = time_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        time_obj = time_obj.replace(tzinfo=timezone.utc)
    if end:
        time_obj += timedelta(days=1)
    return (int(time_obj.timestamp()) * 1000 - DISCORD_EPOCH_MS) << 22


def search_string(text):
    """
    Parse search string.
    from:[<@ID>]
    mentions:[<@ID>]
    has:[link|embed|file|video|image|sound|sticker]
    before:[2015-01-01]
    after:[2015-01-01]
    in:[<#ID>]
    pinned:[true|false]
    """
    author_id = []
    for match in re.findall(match_from, text):
        text = text.replace(match, "")
        author_id.append(match[7:-1])
    mentions = []
    for match in re.findall(match_mentions, text):
        text = text.replace(match, "")
        author_id.append(match[11:-1])
    has = []
    for match in re.findall(match_has, text):
        text = text.replace(match, "")
        has.append(match[4:])
    max_id = []
    for match in re.findall(match_before, text):
        text = text.replace(match, "")
        max_id.append(date_to_snowflake(match[7:]))
    min_id = []
    for match in re.findall(match_after, text):
        text = text.replace(match, "")
        min_id.append(date_to_snowflake(match[6:], end=True))
    channel_id = []
    for match in re.findall(match_in, text):
        text = text.replace(match, "")
        channel_id.append(match[5:-1])
    pinned = []
    for match in re.findall(match_pinned, text):
        text = text.replace(match, "")
        pinned.append(match[7:])
    text = text.strip()
    return text, channel_id, author_id, mentions, has, max_id, min_id, pinned


def command_string(text):
    """Parse command string"""

    # 0 - UNKNOWN
    cmd_type = 0
    cmd_args = {}

    # 1 - SET
    if text.lower().startswith("set"):
        # "set [key] = [value]" / "set [key]=[value]"
        cmd_type = 1
        match = re.search(match_setting, text)
        if match:
            key = match.group(1)
            value = match.group(2)
            if not (key and value):
                cmd_type = 0
        else:
            cmd_type = 0
        cmd_args = {
            "key": key,
            "value": value,
        }

    # 2 - BOTTOM
    elif text.lower().startswith("bottom"):
        cmd_type = 2

    # 3 - GO_REPLY
    elif text.lower().startswith("go_reply"):
        cmd_type = 3

    # 4 - DOWNLOAD
    elif text.lower().startswith("download"):
        cmd_type = 4
        try:
            num = int(text.split(" ")[1])
            cmd_args = {"num": num}
        except (IndexError, ValueError):
            pass

    # 5 - OPEN_LINK
    elif text.lower().startswith("open_link"):
        cmd_type = 5
        try:
            num = int(text.split(" ")[1])
            cmd_args = {"num": num}
        except (IndexError, ValueError):
            pass

    # 6 - PLAY
    elif text.lower().startswith("play"):
        cmd_type = 6
        try:
            num = int(text.split(" ")[1])
            cmd_args = {"num": num}
        except (IndexError, ValueError):
            pass

    # 7 - CANCEL
    elif text.lower().startswith("cancel"):
        cmd_type = 7

    # 8 - COPY_MESSAGE
    elif text.lower().startswith("copy_message"):
        cmd_type = 8

    return cmd_type, cmd_args
