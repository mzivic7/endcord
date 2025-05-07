import logging
import re
import time
from datetime import datetime, timedelta, timezone

DISCORD_EPOCH_MS = 1420070400000
STATUS_STRINGS = ("online", "idle", "dnd", "invisible")
logger = logging.getLogger(__name__)

match_from = re.compile(r"from:<@\d*>")
match_mentions = re.compile(r"mentions:<@\d*>")
match_has = re.compile(r"has:(?:link|embed|file|video|image|sound|sticker)")
match_before = re.compile(r"before:\d{4}-\d{2}-\d{2}")
match_after = re.compile(r"after:\d{4}-\d{2}-\d{2}")
match_in = re.compile(r"in:<#\d*>")
match_pinned = re.compile(r"pinned:(?:true|false)")

match_setting = re.compile(r"(\w+) ?= ?(.+)")
match_channel = re.compile(r"<#(\d*)>")
match_profile = re.compile(r"<@(\d*)>")


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

    # 9 - UPLOAD
    elif text.lower().startswith("upload"):
        cmd_type = 9
        cmd_args = {"path": text[7:]}

    # 10 - SPOIL
    elif text.lower().startswith("spoil"):
        cmd_type = 10

    # 11 - TOGGLE_THREAD
    elif text.lower().startswith("toggle_thread"):
        cmd_type = 11

    # 12 - PROFILE
    elif text.lower().startswith("profile"):
        cmd_type = 12
        match = re.search(match_profile, text)
        if match:
            cmd_args = {"user_id": match.group(1)}

    # 13 - CHANNEL
    elif text.lower().startswith("channel"):
        cmd_type = 13
        match = re.search(match_channel, text)
        if match:
            cmd_args = {"channel_id": match.group(1)}

    # 14 - SUMMARIES
    elif text.lower().startswith("summaries"):
        cmd_type = 14
        match = re.search(match_channel, text)
        if match:
            cmd_args = {"channel_id": match.group(1)}

    # 15 - HIDE
    elif text.lower().startswith("hide"):
        cmd_type = 15
        match = re.search(match_channel, text)
        if match:
            cmd_args = {"channel_id": match.group(1)}

    # 16 - SEARCH
    elif text.lower().startswith("search"):
        cmd_type = 16
        search_text = text[7:].strip(" ")
        cmd_args = {"search_text": search_text}

    # 17 - LINK_CHANNEL
    elif text.lower().startswith("link_channel"):
        cmd_type = 17
        match = re.search(match_channel, text)
        if match:
            cmd_args = {"channel_id": match.group(1)}

    # 18 - LINK_MESSAGE
    elif text.lower().startswith("link_message"):
        cmd_type = 18

    # 19 - GOTO_MENTION
    elif text.lower().startswith("goto_mention"):
        cmd_type = 19
        try:
            num = int(text.split(" ")[1])
            cmd_args = {"num": num}
        except (IndexError, ValueError):
            pass

    # 20 - STATUS
    elif text.lower().startswith("status"):
        cmd_type = 20
        text += " "
        if text.split(" ")[1].lower() in STATUS_STRINGS:
            cmd_args = {"status": text.split(" ")[1].lower()}
        else:
            try:
                num = int(text.split(" ")[1].lower()) - 1
                if num < len(STATUS_STRINGS) - 1:
                    cmd_args = {"status": STATUS_STRINGS[num]}
            except ValueError:
                pass

    # 21 - RECORD
    elif text.lower().startswith("record"):
        cmd_type = 21
        text += " "
        cmd_args = {"cancel": text.split(" ")[1].lower() == "cancel"}

    # 22 - MEMBER_LIST
    elif text.lower().startswith("member_list"):
        cmd_type = 22

    # 23 - REACT
    elif text.lower().startswith("react"):
        cmd_type = 23
        react_text = text[6:].strip(" ")
        cmd_args = {"react_text": react_text}

    # 24 - SHOW_REACTIONS
    elif text.lower().startswith("show_reactions"):
        cmd_type = 24

    # 25 - GOTO
    elif text.lower().startswith("goto"):
        cmd_type = 25
        match = re.search(match_channel, text)
        if match:
            cmd_args = {"channel_id": match.group(1)}
        else:
            cmd_type = 0

    # 26 - VIEW_PFP
    elif text.lower().startswith("view_pfp"):
        cmd_type = 26
        match = re.search(match_profile, text)
        if match:
            cmd_args = {"user_id": match.group(1)}

    # 27 - CHECK_STANDING
    elif text.lower().startswith("check_standing"):
        cmd_type = 27

    return cmd_type, cmd_args
