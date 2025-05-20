import curses
import logging
import re
from datetime import datetime

import emoji

logger = logging.getLogger(__name__)
DAY_MS = 24*60*60*1000
DISCORD_EPOCH_MS = 1420070400000
TREE_EMOJI_REPLACE = "▮"

SEARCH_HELP_TEXT = """from:user_id
mentions:user_id
has:link/embed/file/video/image/sound/sticker
before:date (format: 2015-01-01)
after:date (format: 2015-01-01)
in:channel_id
pinned:true/false"""

COMMAND_ASSISTS = (
    ("goto <#[channel_id]>", "goto"),
    ("view_pfp <@[user_id]>", "view_pfp"),
    ("react [reaction]", "react"),
    ("status *[type]", "status"),
    ("download *[num]", "download"),
    ("open_link *[num]", "open_link"),
    ("play *[num]", "play"),
    ("search *[search_string]", "search"),
    ("record / record cancel", "record"),
    ("upload *[path]", "upload"),
    ("profile *<@[user_id]>", "profile"),
    ("channel *<#[channel_id]>", "channel"),
    ("summaries *<#[channel_id]>", "summaries"),
    ("hide *<#[channel_id]>", "hide"),
    ("toggle_mute *<#[channel_id]>", "toggle_mute"),
    ("mark_as_read *<#[channel_id]>", "mark_as_read"),
    ("copy_message", "copy_message"),
    ("spoil", "spoil"),
    ("link_channel *<#[channel_id]>", "link_channel"),
    ("link_message", "link_message"),
    ("goto_mention *[num]", "goto_mention"),
    ("cancel (up/download)", "cancel"),
    ("member_list", "member_list"),
    ("toggle_thread", "toggle_thread"),
    ("bottom", "bottom"),
    ("go_reply", "go_reply"),
    ("show_reactions", "show_reactions"),
    ("toggle_tab", "toggle_tab"),
    ("switch_tab [num]", "switch_tab"),
    ("paste_clipboard_image", "paste_clipboard_image"),
    ("check_standing", "check_standing"),
    ("set [key] = [value]", "set"),

)

match_emoji_string = re.compile(r"(?<!\\):.+:")
match_d_emoji_string = re.compile(r"<.*?:.*?:\d*?>")
match_d_emoji_name = re.compile(r"(?<=<:).*?(?=:)")
match_d_anim_emoji_name = re.compile(r"(?<=<a:).*?(?=:)")
match_mention_string = re.compile(r"<@\d*?>")
match_mention_id = re.compile(r"(?<=<@)\d*?(?=>)")
match_role_string = re.compile(r"<@&\d*?>")
match_role_id = re.compile(r"(?<=<@&)\d*?(?=>)")
match_channel_string = re.compile(r"<#\d*?>")
match_channel_id = re.compile(r"(?<=<#)\d*?(?=>)")
match_channel_id_msg = re.compile(r"(?<=<#)\d*?(?=>>MSG)")
match_channel_id_msg_group = re.compile(r"((?<=<#)\d*?(?=>))(>>MSG)?")
match_escaped_md = re.compile(r"\\(?=[^a-zA-Z\d\s])")
match_md_underline = re.compile(r"(?<!\\)((?<=_))?__[^_]+__")
match_md_bold = re.compile(r"(?<!\\)((?<=\*))?\*\*[^\*]+\*\*")
match_md_strikethrough = re.compile(r"(?<!\\)((?<=~))?~~[^~]+~~")   # unused
match_md_spoiler = re.compile(r"(?<!\\)((?<=\|))?\|\|[^_]+\|\|")
match_md_code_snippet = re.compile(r"(?<!`|\\)`[^`]+`")
match_md_code_block = re.compile(r"(?s)```.*?```")
match_md_italic = re.compile(r"\b(?<!\\)(?<!\\_)(((?<=_))?_[^_]+_)\b|(((?<=\*))?\*[^\*]+\*)")
match_url = re.compile(r"https?:\/\/\w+(\.\w+)+[^\r\n\t\f\v )\]>]*")
match_discord_channel_url = re.compile(r"https:\/\/discord\.com\/channels\/(\d*)\/(\d*)")
match_discord_message_url = re.compile(r"https:\/\/discord\.com\/channels\/(\d*)\/(\d*)\/(\d*)")
match_sticker_id = re.compile(r"<;\d*?;>")


def sort_by_indexes(input_list, indexes):
    """Sort input list by given indexes"""
    return [val for (_, val) in sorted(zip(indexes, input_list), key=lambda x: x[0])]


def sorted_indexes(input_list):
    """Return indexes of sorted input list"""
    return [i for i, x in sorted(enumerate(input_list), key=lambda x: x[1])]


def normalize_string(input_string, max_length):
    """
    Normalize length of string, by cropping it or appending spaces.
    Set max_length to None to disable.
    """
    input_string = str(input_string)
    if not max_length:
        return input_string
    if len(input_string) > max_length:
        return input_string[:max_length]
    while len(input_string) < max_length:
        input_string = input_string + " "
    return input_string


def normalize_int_str(input_int, digits_limit):
    """Convert integer to string and limit its value to preferred number of digits"""
    int_str = str(min(input_int, 10**digits_limit - 1))
    while len(int_str) < digits_limit:
        int_str = f" {int_str}"
    return int_str


def generate_timestamp(discord_time, format_string, timezone=True):
    """Converts discord timestamp string to formatted string and optionally converts to current timezone"""
    try:
        time_obj = datetime.strptime(discord_time, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        time_obj = datetime.strptime(discord_time, "%Y-%m-%dT%H:%M:%S%z")   # edge case
    if timezone:
        time_obj = time_obj.astimezone()
    return datetime.strftime(time_obj, format_string)


def timestamp_from_snowflake(snowflake, format_string, timezone=True):
    """Converts discord snowflake to formatted string and optionally converts to current timezone"""
    time_obj = datetime.fromtimestamp(((snowflake >> 22) + DISCORD_EPOCH_MS) / 1000)
    if timezone:
        time_obj = time_obj.astimezone()
    return datetime.strftime(time_obj, format_string)


def day_from_snowflake(snowflake, timezone=True):
    """Extract day from discord snowflake with optional timezone conversion"""
    snowflake = int(snowflake)
    if timezone:
        time_obj = datetime.fromtimestamp(((snowflake >> 22) + DISCORD_EPOCH_MS) / 1000)
        time_obj = time_obj.astimezone()
        return time_obj.day
    # faster than datetime, but no timezone conversion
    return ((snowflake >> 22) + DISCORD_EPOCH_MS) / DAY_MS


def emoji_name(emoji_char):
    """Return emoji name from its unicode"""
    return emoji.demojize(emoji_char).replace(":", "")


def replace_emoji_string(line):
    """Replace emoji string (:emoji:) with single character"""
    return re.sub(match_emoji_string, TREE_EMOJI_REPLACE, line)


def trim_at_emoji(line, limit):
    """Remove zwj emojis that are near the limit of the string"""
    if len(line) < limit-1:
        return line
    i = len(line) - 1
    while i >= 0:
        if emoji.is_emoji(line[i]):
            i -= 1
        else:
            break
    return line[:i+1]


def replace_discord_emoji(line):
    """
    Transform emoji strings into nicer looking ones:
    `some text <:emoji_name:emoji_id> more text` --> `some text :emoji_name: more text`
    """
    for string_match in re.findall(match_d_emoji_string, line):
        text = re.search(match_d_emoji_name, string_match)
        if not text:
            text = re.search(match_d_anim_emoji_name, string_match)   # animated
        if text:
            line = line.replace(string_match, f":{text.group()}:")
    return line


def replace_mentions(line, usernames_ids):
    """
    Transforms mention string into nicer looking one:
    `some text <@user_id> more text` --> `some text @username more text`
    """
    for string_match in re.findall(match_mention_string, line):
        text = re.search(match_mention_id, string_match)
        for user in usernames_ids:
            if text.group() == user["id"]:
                line = line.replace(string_match, f"@{user["username"]}")
                break
    return line


def replace_roles(line, roles_ids):
    """
    Transforms roles string into nicer looking one:
    `some text <@role_id> more text` --> `some text @role_name more text`
    """
    for string_match in re.findall(match_role_string, line):
        text = re.search(match_role_id, string_match)
        for role in roles_ids:
            if text.group() == role["id"]:
                line = line.replace(string_match, f"@{role["name"]}")
                break
    return line


def replace_channels(line, chanels_ids):
    """
    Transforms channels string into nicer looking one:
    `some text <#channel_id> more text` --> `some text #channel_name more text`
    """
    for string_match in re.findall(match_channel_string, line):
        text = re.search(match_channel_id, string_match)
        for channel in chanels_ids:
            if text.group() == channel["id"]:
                line = line.replace(string_match, f"#{channel["name"]}")
                break
    return line


def replace_escaped_md(line, except_ranges=[]):
    r"""
    Replace escaped markdown characters.
    eg "\:" --> ":"
    """
    for match in re.finditer(match_escaped_md, line):
        start = match.start()
        end = match.end()
        skip = False
        for except_range in except_ranges:
            start_r = except_range[0]
            end_r = except_range[1]
            if start > start_r and start < end_r and end > start_r and end < end_r:
                skip = True
                break
        if not skip:
            line = line[:start] + line[end:]
    return line


def replace_spoilers_oneline(line):
    """Replace spoiler: ||content|| with ACS_BOARD characters"""
    for _ in range(10):   # lets have some limits
        string_match = re.search(match_md_spoiler, line)
        if not string_match:
            break
        start = string_match.start()
        end = string_match.end()
        line = line[:start] + "▒" * (end - start) + line[end:]
    return line


def format_md_all(line, content_start, except_ranges):
    """
    Replace all supported formatted markdown strings and return list of their formats.
    This should be called only after curses has initialized color.
    Strikethrough is apparently not supported by curses.
    Formatting is not performed inside except_ranges.
    """
    line_format = []
    for _ in range(10):   # lets have some limits
        line_content = line[content_start:]
        format_len = 2
        string_match = re.search(match_md_underline, line_content)
        if not string_match:
            string_match = re.search(match_md_bold, line_content)
            if not string_match:
                string_match = re.search(match_md_italic, line_content)
                # curses.color() must be initialized
                attribute = curses.A_ITALIC
                format_len = 1
                if not string_match:
                    break
            else:
                attribute = curses.A_BOLD
        else:
            attribute = curses.A_UNDERLINE
        start = string_match.start() + content_start
        end = string_match.end() + content_start
        skip = False
        for except_range in except_ranges:
            start_r = except_range[0]
            end_r = except_range[1]
            # if this match is entirely inside excepted range
            if start > start_r and start < end_r and end > start_r and end < end_r:
                skip = True
                break
        if skip:
            continue
        text = string_match.group(0)[format_len:-format_len]
        line = line[:start] + text + line[end:]
        # rearrange formats at indexes after this format index
        done = False
        for format_part in line_format:
            if format_part[1] > start:
                format_part[1] -= 2 * format_len
                format_part[2] -= 2 * format_len
            if format_part[1] == start:
                format_part[2] -= 2 * format_len
            if format_part[1] == start and format_part[2] == end - 2 * format_len and format_part[1] != attribute:
                format_part[0] += [attribute]
                done = True
        if not done:
            line_format.append([[attribute], start, end - 2 * format_len])
    return line, line_format


def format_multiline_one_line(formats_range, line_len, newline_len, color):
    """Generate format for multiline matches, for one line, with custom end position"""
    line_format = []
    if not color:
        return line_format
    for format_range in formats_range:
        if format_range[0] > line_len or format_range[1] < newline_len:
            continue
        if format_range[0] >= newline_len:
            if format_range[1] < line_len:
                line_format.append([color, format_range[0], format_range[1]])
            else:
                line_format.append([color, format_range[0], line_len])
        elif format_range[1] < line_len:
            line_format.append([color, newline_len, format_range[1]])
        else:
            line_format.append([color, newline_len, line_len])
    return line_format


def format_multiline_one_line_end(formats_range, line_len, newline_len, color, end):
    """Generate format for multiline matches, for one line, with custom end position"""
    line_format = []
    if not color:
        return line_format
    for format_range in formats_range:
        if format_range[0] > line_len or format_range[1] < newline_len:
            continue
        if format_range[0] >= newline_len:
            if format_range[1] < line_len:
                line_format.append([color, format_range[0], end])
            else:
                line_format.append([color, format_range[0], end])
        elif format_range[1] < line_len:
            line_format.append([color, newline_len, end])
        else:
            line_format.append([color, newline_len, end])
    return line_format


def split_long_line(line, max_len, align=0):
    """
    Split long line into list, on nearest space to left or on newline
    optionally align newline to specified length
    """
    lines_list = []
    while line:
        if len(line) > max_len:
            newline_index = len(line[:max_len].rsplit(" ", 1)[0])
            if newline_index == 0:
                newline_index = max_len
            elif newline_index < align:
                newline_index = max_len
            if "\n" in line[:newline_index]:
                newline_index = line.index("\n")
            lines_list.append(line[:newline_index])
            try:
                if line[newline_index] in (" ", "\n"):   # remove space and \n
                    line = line[newline_index+1:]
                else:
                    line = line[newline_index:]
            except IndexError:
                line = line[newline_index+1:]
        elif "\n" in line:
            newline_index = line.index("\n")
            lines_list.append(line[:newline_index])
            line = line[newline_index+1:]
        else:
            lines_list.append(line)
            break
        if align:
            line = " " * align + line
    return lines_list


def clean_type(embed_type):
    r"""
    Clean embed type string from excessive information
    eg. `image\png` ---> `image`
    """
    return embed_type.split("/")[0]


def replace_discord_url(message, current_guild):
    """Replace discord url only from this guild, for channel or message"""
    text = message["content"]
    mention_msg = []
    for match in re.finditer(match_discord_message_url, text):
        if match.group(1) == current_guild:
            text = text[:match.start()] + f"<#{match.group(2)}>>MSG" + text[match.end():]
            mention_msg.append(match.group(3))
    for match in re.finditer(match_discord_channel_url, text):
        if match.group(1) == current_guild:
            text = text[:match.start()] + f"<#{match.group(2)}>" + text[match.end():]
    message["content"] = text
    if mention_msg:
        message["mention_msg"] = mention_msg
    return message



def generate_chat(messages, roles, channels, max_length, my_id, my_roles, member_roles, colors, colors_formatted, blocked, config):
    """
    Generate chat according to provided formatting.
    Message shape:
        format_reply (message that is being replied to)
        format_message (main message line)
        format_newline (if main message is too long, it goes on newlines)
        format_reactions (reactions added to main message)
    Possible options for format_message:
        %content
        %username
        %global_name
        %timestamp
        %edited
    Possible options for format_newline:
        %content   # remainder from previous line
        %timestamp
    Possible options for format_reply:
        %content
        %username
        %global_name
        %timestamp   # of replied message
    Possible options for format_reactions:
        %timestamp   # of message
        %reactions   # all reactions after they pass through format_one_reaction
    Possible options for format_one_reaction:
        %reaction
        %count
    Possible options for format_timestamp:
        same as format codes for datetime package
    Possoble options for blocked_mode:
        0 - no blocking
        1 - mask blocked messages
        2 - hide blocked messages
    limit_username normalizes length of usernames, by cropping them or appending spaces. Set to None to disable.
    Returned indexes correspond to each message as how many lines it is covering.
    use_nick will make it use nick instead global_name whenever possible.
    """

    # load from config
    format_message = config["format_message"]
    format_newline = config["format_newline"]
    format_reply = config["format_reply"]
    format_reactions = config["format_reactions"]
    format_one_reaction = config["format_one_reaction"]
    format_timestamp = config["format_timestamp"]
    edited_string = config["edited_string"]
    reactions_separator = config["reactions_separator"]
    limit_username = config["limit_username"]
    limit_global_name = config["limit_global_name"]
    use_nick = config["use_nick_when_available"]
    convert_timezone = config["convert_timezone"]
    blocked_mode = config["blocked_mode"]
    keep_deleted = config["keep_deleted"]
    date_separator = config["chat_date_separator"]
    format_date = config["format_date"]
    emoji_as_text = config["emoji_as_text"]
    quote_character = config["quote_character"]

    chat = []
    chat_format = []
    indexes = []
    chat_map = []   # ((num, username:(start, end), is_reply, reactions:((start, end), ...)), ...)
    len_edited = len(edited_string)
    enable_separator = format_date and date_separator
    # load colors
    color_default = [colors[0]]
    color_blocked = [colors[2]]
    color_deleted = [colors[3]]
    color_separator = [colors[4]]
    color_code = colors[5]
    color_chat_edited = colors_formatted[4][0]
    color_mention_chat_edited = colors_formatted[12][0]
    color_chat_url = colors_formatted[5][0][0]
    color_mention_chat_url = colors_formatted[13][0][0]
    color_spoiler = colors_formatted[6][0][0]
    color_mention_spoiler = colors_formatted[14][0][0]
    # load formatted colors: [[id], [id, start, end]...]
    color_message = colors_formatted[0]
    color_newline = colors_formatted[1]
    color_reply = colors_formatted[2]
    color_reactions = colors_formatted[3]
    color_mention_message = colors_formatted[8]
    color_mention_newline = colors_formatted[9]
    color_mention_reply = colors_formatted[10]
    color_mention_reactions = colors_formatted[11]

    placeholder_timestamp = generate_timestamp("2015-01-01T00:00:00.000000+00:00", format_timestamp)
    pre_content_len = len(format_message
        .replace("%username", " " * limit_username)
        .replace("%global_name", " " * limit_global_name)
        .replace("%timestamp", placeholder_timestamp)
        .replace("%edited", "")
        .replace("%content", ""),
    ) - 1
    pre_name_len = len(format_message
        .replace("%username", "\n")
        .replace("%global_name", "\n")
        .replace("%timestamp", placeholder_timestamp)
        .split("\n")[0],
    ) - 1
    newline_len = len(format_newline
        .replace("%timestamp", placeholder_timestamp)
        .replace("%content", ""),
        )
    pre_reaction_len = len(
        format_reactions
        .replace("%timestamp", placeholder_timestamp)
        .replace("%reactions", ""),
    ) - 1
    if format_message.find("%username") > format_message.find("%global_name"):
        end_name = pre_name_len + limit_username + 1
    else:
        end_name = pre_name_len + limit_global_name + 1

    for num, message in enumerate(messages):
        temp_chat = []   # stores only one multiline message
        temp_format = []
        temp_chat_map = []
        mentioned = False
        edited = message["edited"]
        user_id = message["user_id"]
        selected_color_spoiler = color_spoiler

        # select base color
        color_base = color_default
        for mention in message["mentions"]:
            if mention["id"] == my_id:
                mentioned = True
                selected_color_spoiler = color_mention_spoiler
                break
        for role in message["mention_roles"]:
            if role in my_roles:
                mentioned = True
                selected_color_spoiler = color_mention_spoiler
                break

        # skip deleted
        disable_formatting = False
        if "deleted" in message:
            if keep_deleted:
                color_base = color_deleted
                disable_formatting = True
                selected_color_spoiler = color_deleted
            else:
                continue

        # get member role color
        role_color = None
        alt_role_color = None
        for member in member_roles:
            if member["user_id"] == user_id:
                role_color = member.get("primary_role_color")
                alt_role_color = member.get("primary_role_alt_color")
                break

        reply_color_format = color_base

        # handle blocked messages
        if blocked_mode and user_id in blocked:
            if blocked_mode == 1:
                message["username"] = "blocked"
                message["global_name"] = "blocked"
                message["nick"] = "blocked"
                message["content"] = "Blocked message"
                message["embeds"] = []
                message["stickers"] = []
                color_base = color_blocked
            else:
                indexes.append(0)
                temp_chat_map.append(None)
                continue   # to not break message-to-chat conversion

        # date separator
        try:
            if enable_separator and day_from_snowflake(message["id"]) != day_from_snowflake(messages[num+1]["id"]):
                # if this message is 1 day older than next message (up - past message)
                date = generate_timestamp(message["timestamp"], format_date, convert_timezone)
                # keep text always in center
                filler = max_length - len(date)
                filler_l = filler // 2
                filler_r = filler - filler_l
                temp_chat.append(f"{date_separator * filler_l}{date}{date_separator * filler_r}")
                temp_format.append([color_separator])
                temp_chat_map.append(None)
        except IndexError:
            pass

        # replied message line
        if message["referenced_message"]:
            if message["referenced_message"]["id"]:
                if blocked_mode and message["referenced_message"]["user_id"] in blocked:
                    message["referenced_message"]["username"] = "blocked"
                    message["referenced_message"]["global_name"] = "blocked"
                    message["referenced_message"]["nick"] = "blocked"
                    message["referenced_message"]["content"] = "Blocked message"
                    reply_color_format = color_blocked
                if use_nick and message["referenced_message"]["nick"]:
                    global_name_nick = message["referenced_message"]["nick"]
                elif message["referenced_message"]["global_name"]:
                    global_name_nick = message["referenced_message"]["global_name"]
                else:
                    global_name_nick = message["referenced_message"]["username"]
                reply_embeds = message["referenced_message"]["embeds"].copy()
                content = ""
                if message["referenced_message"]["content"]:
                    content = replace_escaped_md(message["referenced_message"]["content"])
                    content = replace_spoilers_oneline(content)
                    content = replace_discord_emoji(content)
                    content = replace_mentions(content, message["referenced_message"]["mentions"])
                    content = replace_roles(content, roles)
                    content = replace_channels(content, channels)
                    if emoji_as_text:
                        content = emoji.demojize(content)
                if reply_embeds:
                    for embed in reply_embeds:
                        if embed["url"] and embed["url"] not in content:
                            if content:
                                content += "\n"
                            content += f"[{clean_type(embed["type"])} embed]: {embed["url"]}"
                reply_line = (
                    format_reply
                    .replace("%username", normalize_string(message["referenced_message"]["username"], limit_username))
                    .replace("%global_name", normalize_string(str(global_name_nick), limit_global_name))
                    .replace("%timestamp", generate_timestamp(message["referenced_message"]["timestamp"], format_timestamp, convert_timezone))
                    .replace("%content", content.replace("\r", " ").replace("\n", " "))
                )
            else:
                reply_line =  (
                    format_reply
                    .replace("%username", normalize_string("Unknown", limit_username))
                    .replace("%global_name", normalize_string("Unknown", limit_global_name))
                    .replace("%timestamp", "")
                    .replace("%content", message["referenced_message"]["content"].replace("\r", "").replace("\n", ""))
                )
            if len(reply_line) > max_length:
                reply_line = reply_line[:max_length - 3] + "..."   # -3 to leave room for "..."
            temp_chat.append(reply_line)
            if disable_formatting or reply_color_format == color_blocked:
                temp_format.append([reply_color_format])
            elif mentioned:
                temp_format.append(color_mention_reply)
            else:
                temp_format.append(color_reply)
            temp_chat_map.append((num, None, True, None))

        # main message
        quote = False
        if use_nick and message["nick"]:
            global_name_nick = message["nick"]
        elif message["global_name"]:
            global_name_nick = message["global_name"]
        else:
            global_name_nick = message["username"]
        content = ""
        if message["content"]:
            content = replace_discord_emoji(message["content"])
            content = replace_mentions(content, message["mentions"])
            content = replace_roles(content, roles)
            content = replace_channels(content, channels)
            if emoji_as_text:
                content = emoji.demojize(content)
            if content.startswith("> "):
                content = quote_character + " " + content[2:]
                quote = True
        for embed in message["embeds"]:
            if embed["url"] and embed["url"] not in content:
                if content:
                    content += "\n"
                content += f"[{clean_type(embed["type"])} embed]: {embed["url"]}"
        for sticker in message["stickers"]:
            sticker_type = sticker["format_type"]
            if content:
                content += "\n"
            if sticker_type == 1:
                content += f"[png sticker] (can be opened): {sticker["name"]}"
            elif sticker_type == 2:
                content += f"[apng sticker] (can be opened): {sticker["name"]}"
            elif sticker_type == 3:
                content += f"[lottie sticker] (cannot be opened): {sticker["name"]}"
            else:
                content += f"[gif sticker] (can be opened): {sticker["name"]}"

        message_line = (
            format_message
            .replace("%username", normalize_string(message["username"], limit_username))
            .replace("%global_name", normalize_string(str(global_name_nick), limit_global_name))
            .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
            .replace("%edited", edited_string if edited else "")
            .replace("%content", content)
        )

        # find all code snippets and blocks
        code_snippets = []
        code_blocks = []
        for match in re.finditer(match_md_code_snippet, message_line):
            code_snippets.append([match.start(), match.end()])
        for match in re.finditer(match_md_code_block, message_line):
            code_blocks.append([match.start(), match.end()])
        except_ranges = code_snippets + code_blocks

        # find all urls
        urls = []
        if color_chat_url:
            for match in re.finditer(match_url, message_line):
                start = match.start()
                end = match.end()
                skip = False
                for except_range in except_ranges:
                    start_r = except_range[0]
                    end_r = except_range[1]
                    if start > start_r and start < end_r and end > start_r and end <= end_r:
                        skip = True
                        break
                if not skip:
                    urls.append([start, end])

        # find all spoilers
        spoilers = []
        for match in re.finditer(match_md_spoiler, message_line):
            spoilers.append([match.start(), match.end()])
        # exclude spoiled messages
        spoilers = spoilers[message.get("spoiled"):]

        # limit message_line and split to multiline
        message_line_formatted, _ = format_md_all(message_line, pre_content_len, except_ranges + urls)
        newline_sign = False
        newline_index = max_length
        if len(message_line) > max_length:
            newline_index = len(message_line[:max_length].rsplit(" ", 1)[0])   #  splits line on space
            if len(message_line) != len(message_line_formatted):
                newline_index_formatted = len(message_line_formatted[:max_length].rsplit(" ", 1)[0])
                if newline_index < newline_index_formatted:
                    # splits line on space while ignoring markdown characters
                    newline_index = len(" ".join(message_line.split(" ")[:len(message_line[:max_length].split(" "))]))
            if newline_index <= len(
                format_newline
                .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
                .replace("%content", ""),
                ):
                    newline_index = max_length
            # if there is \n on current line, use its position to split line
            if "\n" in message_line[:newline_index]:
                newline_index = message_line.index("\n")
                quote = False
                newline_sign = True
                split_on_space = 0
            if message_line[newline_index] in (" ", "\n"):   # remove space and \n
                next_line = message_line[newline_index+1:]
                split_on_space = 1
            else:
                next_line = message_line[newline_index:]
                split_on_space = 0
            message_line = message_line[:newline_index]
        elif "\n" in message_line:
            newline_index = message_line.index("\n")
            next_line = message_line[newline_index+1:]
            message_line = message_line[:newline_index]
            quote = False
            newline_sign = True
            split_on_space = 1
        else:
            next_line = None

        # format markdown
        message_line, md_format = format_md_all(message_line, pre_content_len, except_ranges + urls)
        message_line = replace_escaped_md(message_line, except_ranges + urls)

        if newline_sign and next_line.startswith("> "):
            next_line = next_line[2:]   # will be added in newline while loop
            quote = True

        # replace spoilers
        format_spoilers = format_multiline_one_line(spoilers, newline_index+1, 0, selected_color_spoiler)
        for spoiler_range in format_spoilers:
            start = spoiler_range[1]
            end = spoiler_range[2]
            message_line = message_line[:start] + "▒" * (end - start) + message_line[end:]

        # code blocks formatting here to add spaces to end of string
        code_block_format = format_multiline_one_line_end(code_blocks, newline_index+1, 0, color_code, max_length-1)
        if code_block_format:
            message_line = message_line.ljust(max_length-1)

        temp_chat.append(message_line)
        temp_chat_map.append((num, (pre_name_len, end_name), False, None))

        # formatting
        if disable_formatting:
            temp_format.append([color_base])
        elif mentioned:
            format_line = color_mention_message[:]
            format_line += md_format
            format_line += format_multiline_one_line(urls, newline_index+1, 0, color_mention_chat_url)
            format_line += format_multiline_one_line(code_snippets, newline_index+1, 0, color_code)
            format_line += code_block_format
            format_line += format_spoilers
            if alt_role_color:
                format_line.append([alt_role_color, pre_name_len, end_name])
            if edited and not next_line:
                format_line.append(color_mention_chat_edited + [len(message_line) - len_edited, len(message_line)])
            temp_format.append(format_line)
        else:
            format_line = color_message[:]
            format_line += md_format
            format_line += format_multiline_one_line(urls, newline_index+1, 0, color_chat_url)
            format_line += format_multiline_one_line(code_snippets, newline_index+1, 0, color_code)
            format_line += code_block_format
            format_line += format_spoilers
            if role_color:
                format_line.append([role_color, pre_name_len, end_name])
            if edited and not next_line:
                format_line.append([*color_chat_edited, len(message_line) - len_edited, len(message_line)])
            temp_format.append(format_line)

        # newline
        line_num = 1
        while next_line:
            if quote:
                full_content = quote_character + " " + next_line
                extra_newline_len = 2
            else:
                full_content = next_line
                extra_newline_len = 0
            new_line = (
                format_newline
                .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
                .replace("%content", full_content)
            )

            # correct index for each new line
            content_index_correction = newline_len + extra_newline_len - 1 + (not split_on_space) - newline_index
            for url in urls:
                url[0] += content_index_correction
                url[1] += content_index_correction
            for spoiler in spoilers:
                spoiler[0] += content_index_correction
                spoiler[1] += content_index_correction
            for code_snippet in code_snippets:
                code_snippet[0] += content_index_correction
                code_snippet[1] += content_index_correction
            for code_block in code_blocks:
                code_block[0] += content_index_correction
                code_block[1] += content_index_correction
            except_ranges = code_snippets + code_blocks

            # limit new_line and split to next line
            new_line_formatted, _ = format_md_all(new_line, pre_content_len + extra_newline_len, except_ranges + urls)
            newline_sign = False
            if len(new_line) > max_length:
                newline_index = len(new_line[:max_length].rsplit(" ", 1)[0])
                if len(message_line) != len(new_line_formatted):
                    newline_index_formatted = len(new_line_formatted[:max_length].rsplit(" ", 1)[0])
                    if newline_index < newline_index_formatted:
                        newline_index = len(" ".join(new_line.split(" ")[:len(new_line[:max_length].split(" "))]))
                if newline_index <= newline_len + 2*quote:
                    newline_index = max_length
                if "\n" in new_line[:newline_index]:
                    newline_index = new_line.index("\n")
                    quote = False
                    newline_sign = True
                    split_on_space = 0
                try:
                    if new_line[newline_index] in (" ", "\n"):   # remove space and \n
                        next_line = new_line[newline_index+1:]
                        split_on_space = 1
                    else:
                        next_line = new_line[newline_index:]
                        split_on_space = 0
                except IndexError:
                    next_line = new_line[newline_index+1:]
                    split_on_space = 1
                new_line = new_line[:newline_index]
            elif "\n" in new_line:
                newline_index = new_line.index("\n")
                next_line = new_line[newline_index+1:]
                new_line = new_line[:newline_index]
                quote = False
                newline_sign = True
                split_on_space = 1
            else:
                next_line = None

            # format markdown
            new_line, md_format = format_md_all(new_line, pre_content_len + extra_newline_len, except_ranges + urls)

            if newline_sign and next_line.startswith("> "):
                next_line = quote_character + " " + next_line[2:]
                quote = True

            # replace spoilers
            format_spoilers = format_multiline_one_line(spoilers, len(new_line), newline_len, selected_color_spoiler)
            for spoiler_range in format_spoilers:
                start = spoiler_range[1]
                end = spoiler_range[2]
                new_line = new_line[:start] + "▒" * (end - start) + new_line[end:]

            # code blocks formatting here to add spaces to end of string
            code_block_format = format_multiline_one_line_end(code_blocks, len(new_line), newline_len, color_code, max_length-1)
            if code_block_format:
                new_line = new_line.ljust(max_length-1)

            temp_chat.append(new_line)
            temp_chat_map.append((num, ))

            # formatting
            if disable_formatting:
                temp_format.append([color_base])
            elif mentioned:
                format_line = color_mention_newline[:]
                format_line += md_format
                format_line += format_multiline_one_line(urls, len(new_line), newline_len, color_mention_chat_url)
                format_line += format_multiline_one_line(code_snippets, len(new_line), newline_len, color_code)
                format_line += code_block_format
                format_line += format_spoilers
                if edited and not next_line:
                    format_line.append(color_mention_chat_edited + [len(new_line) - len_edited, len(new_line)])
                temp_format.append(format_line)
            else:
                format_line = color_newline[:]
                format_line += md_format
                format_line += format_multiline_one_line(urls, len(new_line), newline_len, color_chat_url)
                format_line += format_multiline_one_line(code_snippets, len(new_line), newline_len, color_code)
                format_line += code_block_format
                format_line += format_spoilers
                if edited and not next_line:
                    format_line.append([*color_chat_edited, len(new_line) - len_edited, len(new_line)])
                temp_format.append(format_line)
            line_num += 1

        # reactions
        if message["reactions"]:
            reactions = []
            for reaction in message["reactions"]:
                emoji_str = reaction["emoji"]
                if emoji_as_text:
                    emoji_str = emoji_name(emoji_str)
                my_reaction = ""
                if reaction["me"]:
                    my_reaction = "*"
                reactions.append(
                    format_one_reaction
                    .replace("%reaction", emoji_str)
                    .replace("%count", f"{my_reaction}{reaction["count"]}"),
                )
            reactions_line = (
                format_reactions
                .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
                .replace("%reactions", reactions_separator.join(reactions))
            )
            if len(reactions_line) > max_length:
                reactions_line = reactions_line[:max_length]
            temp_chat.append(reactions_line)
            if disable_formatting:
                temp_format.append([color_base])
            elif mentioned:
                temp_format.append(color_mention_reactions)
            else:
                temp_format.append(color_reactions)
            reactions_map = []
            offset = 0
            for reaction in reaction:
                reactions_map.append([pre_reaction_len + offset, pre_reaction_len + len(reaction) + offset])
                offset += len(reactions_separator) + len(reaction)
            temp_chat_map.append((num, None, False, reactions_map))
        indexes.append(len(temp_chat))

        # invert message lines order and append them to chat
        # it is inverted because chat is drawn from down to upside
        chat.extend(temp_chat[::-1])
        chat_format.extend(temp_format[::-1])
        chat_map.extend(temp_chat_map[::-1])
    return chat, chat_format, indexes, chat_map


def generate_status_line(my_user_data, my_status, unseen, typing, active_channel, action, tasks, tabs, format_status_line, format_rich, limit_typing=30, use_nick=True, fun=True):
    """
    Generate status line according to provided formatting.
    Possible options for format_status_line:
        %global_name
        %username
        %status   # discord status if online, otherwise 'connecting' or 'offline'
        %custom_status
        %custom_status_emoji
        %pronouns
        %unreads   # '[New unreads]' if this channel has unread messages
        %typing
        %rich
        %server
        %channel
        %action   # replying/editig/deleting
        %task   # currently running long task
        %tabs
    Possible options for format_rich:
        %type
        %name
        %state
        %details
        %small_text
        %large_text
    length of the %typing string can be limited with limit_typing
    use_nick will make it use nick instead username in typing whenever possible.
    """
    # typing
    if len(typing) == 0:
        typing_string = ""
    elif len(typing) == 1:
        if use_nick and typing[0]["nick"]:
            typing_string = typing[0]["nick"]
        else:
            typing_string = typing[0]["username"]
        # -15 is for "(... is typing)"
        typing_string = typing_string[:limit_typing - 15]
        sufix = "... is typing"
        typing_string = f"({typing_string.replace("\n ", ", ")}{sufix})"
    else:
        usernames = []
        for user in typing:
            if use_nick and user["nick"]:
                usernames.append(user["nick"])
            else:
                usernames.append(user["username"])
        typing_string = "\n ".join(usernames)
        # -13 is for "( are typing)"
        if len(typing_string) > limit_typing - 13:
            # -16 is for "(+XX are typing)"
            break_index = len(typing_string[:limit_typing - 16].rsplit("\n", 1)[0])
            remaining = len(typing_string[break_index+2:].split("\n "))
            if len(typing[0]["username"]) > limit_typing - 16:
                remaining -= 1   # correction when first user is cut
            typing_string = typing_string[:break_index] + f" +{remaining}"
        sufix = " are typing"
        typing_string = f"({typing_string.replace("\n ", ", ")}{sufix})"

    # my rich presence
    if my_status["activities"]:
        state = my_status["activities"][0]["state"][:limit_typing]
        details = my_status["activities"][0]["details"][:limit_typing]
        sm_txt = my_status["activities"][0]["small_text"]
        lg_txt = my_status["activities"][0]["large_text"]
        if my_status["activities"][0]["type"] == 0:
            verb = "Playing"
        else:
            verb = "Listening to"
        rich = (
            format_rich
            .replace("%type", verb)
            .replace("%name", my_status["activities"][0]["name"])
            .replace("%state", state if state else "")
            .replace("%details", details if details else "")
            .replace("%small_text", sm_txt if sm_txt else "")
            .replace("%large_text", lg_txt if lg_txt else "")
        )
        if fun:
            rich = rich.replace("Metal", "🤘 Metal").replace("metal", "🤘 metal")
    else:
        rich = "No rich presence"
    if my_status["client_state"] == "online":
        status = my_status["status"]
    else:
        status = my_status["client_state"]
    guild = active_channel["guild_name"]

    # action
    action_string = ""
    if action["type"] == 1:   # replying
        ping = ""
        if action["mention"]:
            ping = "(PING) "
        if action["global_name"]:
            name = action["global_name"]
        else:
            name = action["username"]
        action_string = f"Replying {ping}to {name}"
    elif action["type"] == 2:   # editing
        action_string = "Editing the message"
    elif action["type"] == 3:   # confirm deleting
        action_string = "Really delete the message? [Y/n]"
    elif action["type"] == 4:   # select from multiple links
        action_string = "Select link to open in browser (type a number)"
    elif action["type"] == 5:   # select from multiple attachments
        action_string = "Select attachment link to download (type a number)"
    elif action["type"] == 6:   # select attachment media to play
        action_string = "Select attachment link to play (type a number)"
    elif action["type"] == 7:   # cancel all downloads
        action_string = "Really cancel all downloads/attachments? [Y/n]"
    elif action["type"] == 8:   # ask for upload path
        action_string = "Type file path to upload"
    elif action["type"] == 9:   # confirm hiding channel
        action_string = "Really hide this channel? [Y/n]"
    elif action["type"] == 10:   # select to which channel to go
        action_string = "Select channel/message to go to (type a number)"
    elif action["type"] == 11:   # reacting
        if action["global_name"]:
            name = action["global_name"]
        else:
            name = action["username"]
        action_string = f"Reacting to {name}"
    elif action["type"] == 12:   # select reaction to show details
        action_string = "Select reaction (type a number)"

    if my_status["custom_status_emoji"]:
        custom_status_emoji = str(my_status["custom_status_emoji"]["name"])
    else:
        custom_status_emoji = ""

    # running long tasks
    tasks = sorted(tasks, key=lambda x:x[1])
    if len(tasks) == 0:
        task = ""
    elif len(tasks) == 1:
        task = tasks[0][0]
    else:
        task = f"{tasks[0][0]} (+{len(tasks) - 1})"
    if not tabs:
        tabs = ""

    return (
        format_status_line
        .replace("%global_name", str(my_user_data["global_name"]))
        .replace("%username", my_user_data["username"])
        .replace("%status", status)
        .replace("%custom_status", str(my_status["custom_status"]))
        .replace("%custom_emoji", custom_status_emoji)
        .replace("%pronouns", str(my_user_data["pronouns"]))
        .replace("%unreads", "[New unreads]" if unseen else "")
        .replace("%typing", typing_string)
        .replace("%rich", rich)
        .replace("%server", guild if guild else "DM")
        .replace("%channel", str(active_channel["channel_name"]))
        .replace("%action", action_string)
        .replace("%task", task)
        .replace("%tabs", tabs)
    )


def generate_tab_string(tabs, active_tab, unseen, format_tabs, tabs_separator, limit_len, max_len):   #noqa
    """
    Generate tabs list string according to provided formatting.
    Possible options for generate_tab_string:
        %num
        %name
        %server
    """
    tabs_separated = []
    trimmed_left = False
    for num, tab in enumerate(tabs):
        tabs_separated.append(format_tabs
            .replace("%num", str(num + 1))
            .replace("%name", tab["channel_name"][:limit_len])
            .replace("%server", tab["guild_name"][:limit_len]),
        )
        # scroll to active if string is too long
        if num == active_tab:
            while len(tabs_separator.join(tabs_separated)) >= max_len:
                if not tabs_separated:
                    break
                trimmed_left = True
                tabs_separated.pop(0)
        if len(tabs_separator.join(tabs_separated)) >= max_len:
            break
    tab_string = tabs_separator.join(tabs_separated)

    if trimmed_left:
        tab_string = f"< {tab_string}"

    # trim right side of tab string
    if len(tab_string) > max_len:
        tab_string = tab_string[:max_len - 2 * (trimmed_left + 1)] + " >"
    return tab_string


def generate_prompt(my_user_data, active_channel, format_prompt, limit_prompt=15):
    """
    Generate status line according to provided formatting.
    Possible options for format_status_line:
        %global_name
        %username
        %server
        %channel
    """
    guild = active_channel["guild_name"]
    return (
        format_prompt
        .replace("%global_name", str(my_user_data["global_name"])[:limit_prompt])
        .replace("%username", my_user_data["username"][:limit_prompt])
        .replace("%server", guild[:limit_prompt] if guild else "DM")
        .replace("%channel", str(active_channel["channel_name"])[:limit_prompt])
    )


def generate_extra_line(attachments, selected, max_len):
    """
    Generate extra line containing attachments information, with format:
    Attachments: [attachment.name] - [Uploading/OK/Too-Large/Restricted/Failed], Selected:N, Total:N
    """
    if attachments:
        total = len(attachments)
        name = attachments[selected]["name"]
        match attachments[selected]["state"]:
            case 0:
                state = "Uploading"
            case 1:
                state = "OK"
            case 2:
                state = "Too Large"
            case 3:
                state = "Restricted"
            case 4:
                state = "Failed"
            case _:
                state = "Unknown"
        end = f" - {state}, Selected:{selected + 1}, Total:{total}"
        return f" Attachments: {name}"[:max_len - len(end)] + end
    return ""


def generate_extra_window_profile(user_data, user_roles, presence, max_len):
    """Generate extra window title and body for user profile view"""
    # prepare user strings
    nick = ""
    if user_data["nick"]:
        nick = f"Nick: {user_data["nick"]}"
    global_name = ""
    if user_data["global_name"]:
        global_name = f"Name: {user_data["global_name"]}"
    username = f"Username: {user_data["username"]}"
    pronouns = ""
    if user_data["pronouns"]:
        pronouns = f"Pronouns: {user_data["pronouns"]}"
    roles_string = ", ".join(user_roles)
    member_since = timestamp_from_snowflake(int(user_data["id"]), "%Y-%m-%d")

    # build title
    title_line = ""
    items = [nick, global_name, username, pronouns]
    complete = True
    for num, item in enumerate(items):
        if len(title_line + item) + 3 > max_len:
            complete = False
            break
        if item:
            title_line += f"{items[num]} | "
    title_line = title_line[:-3]
    items = items[num+complete:]
    if not title_line:
        title_line = items.pop(0)[:max_len]

    # add overflow from title line to to body
    body_line = ""
    if items:
        add_newline = False
        for item in items:
            if item:
                body_line += f"{item} | "
                add_newline = True
        if add_newline:
            body_line += "\n"

    # activity
    if presence:
        status = presence["status"].capitalize().replace("Dnd", "DnD")
        if presence["custom_status"]:
            custom = f" - {presence["custom_status"]}"
        else:
            custom = ""
        body_line += f"Status: {status}{custom}\n"
    else:
        body_line += "Could not fetch status\n"

    # build body
    if user_data["tag"]:
        body_line += f"Tag: {user_data["tag"]}\n"
    body_line += f"Member since: {member_since}\n"
    if user_data["joined_at"]:
        body_line += f"Joined: {user_data["joined_at"]}\n"

    # rich presences
    if presence:
        if presence["activities"]:
            body_line += "\n"
        for activity in presence["activities"]:
            if activity["type"] == 0:
                action = "Playing"
            else:
                action = "Listening to"
            if activity["state"]:
                state = f" - {activity["state"]}"
            else:
                state = ""
            body_line += f"{action} {activity["name"]}{state}\n"
            if activity["details"]:
                body_line += f"{activity["details"]}\n"
            if activity["small_text"]:
                body_line += f"{activity["small_text"]}\n"
            if activity["large_text"]:
                body_line += f"{activity["large_text"]}\n"
            body_line += "\n"

    if roles_string:
        body_line += f"Roles: {roles_string}\n"
    if user_data["bio"]:
        body_line += f"Bio:\n{user_data["bio"]}"

    body = split_long_line(body_line, max_len)
    return title_line, body


def generate_extra_window_channel(channel, max_len):
    """Generate extra window title and body for channel info view"""
    title_line = f"Channel: {channel["name"]}"[:max_len]
    body_line = ""
    no_embed = not channel.get("allow_attach", True)
    no_write = not channel.get("allow_write", True)
    if no_embed and no_write:
        body_line += "No write and embed permissions\n"
    elif no_embed:
        body_line += "No embed permissions\n"
    elif no_write:
        body_line += "No write permissions\n"
    if channel["topic"]:
        body_line += f"Topic:\n{channel["topic"]}"
    else:
        body_line += "No topic."

    body = split_long_line(body_line, max_len)
    return title_line, body


def generate_extra_window_guild(guild, max_len):
    """Generate extra window title and body for guild info view"""
    title_line = f"Server: {guild["name"]}"[:max_len]

    # build body
    body_line = f"Members: {guild["member_count"]}\n"
    if guild["description"]:
        body_line += f"Description:\n{guild["description"]}"
    else:
        body_line += "No description."

    body = split_long_line(body_line, max_len)
    return title_line, body


def generate_extra_window_summaries(summaries, max_len, channel_name=None):
    """Generate extra window title and body for summaries list view"""
    if channel_name:
        title_line = f"[{channel_name}] Summaries:"
    else:
        title_line = "Summaries:"
    body = []
    indexes = []
    if summaries:
        for summary in summaries:
            summary_date = timestamp_from_snowflake(int(summary["message_id"]), "%m-%d-%H:%M")
            summary_string = f"[{summary_date}] - {summary["topic"]}: {summary["description"]}"
            summary_lines = split_long_line(summary_string, max_len, align=16)
            indexes.append({
                "lines": len(summary_lines),
                "message_id": summary["message_id"],
            })
            body.extend(summary_lines)
    else:
        body = ["No summaries."]
    return title_line, body, indexes


def generate_extra_window_search(messages, roles, channels, blocked, total_msg, config, max_len, limit_lines=3, newline_len=4):
    """
    Generate extra window title and body for message search view
    Possible options for format_message:
        %content
        %username
        %global_name
        %date
        %channel
    """
    limit_username = config["limit_username"]
    limit_global_name = config["limit_global_name"]
    use_nick = config["use_nick_when_available"]
    convert_timezone = config["convert_timezone"]
    blocked_mode = config["blocked_mode"]
    format_date = config["format_forum_timestamp"]
    emoji_as_text = config["emoji_as_text"]
    format_message = config["format_search_message"]
    title_line = f"Search results: {total_msg} messages"

    body = []
    indexes = []
    if messages:
        for message in messages:

            # skip blocked messages
            if blocked_mode and message["user_id"] in blocked:
                indexes.append({
                    "lines": 0,
                    "message_id": message["id"],
                })
                continue

            if use_nick and message["nick"]:
                global_name_nick = message["nick"]
            elif message["global_name"]:
                global_name_nick = message["global_name"]
            else:
                global_name_nick = message["username"]

            channel_name = "Unknown"
            channel_id = message["channel_id"]
            for channel in channels:
                if channel["id"] == channel_id:
                    channel_name = channel["name"]
                    break

            content = ""
            if message["content"]:
                content = replace_discord_emoji(message["content"])
                content = replace_mentions(content, message["mentions"])
                content = replace_roles(content, roles)
                content = replace_channels(content, channels)
                content = replace_spoilers_oneline(content)
                if emoji_as_text:
                    content = emoji.demojize(content)

            for embed in message["embeds"]:
                if embed["url"] and embed["url"] not in content:
                    if content:
                        content += "\n"
                    content += f"[{clean_type(embed["type"])} embed]: {embed["url"]}"

            # skip empty messages
            if not content:
                indexes.append({
                    "lines": 0,
                    "message_id": message["id"],
                })
                continue

            message_string = (
                format_message
                .replace("%username", normalize_string(message["username"], limit_username))
                .replace("%global_name", normalize_string(str(global_name_nick), limit_global_name))
                .replace("%date", generate_timestamp(message["timestamp"], format_date, convert_timezone))
                .replace("%channel", normalize_string(channel_name, limit_global_name))
                .replace("%content", content)
            )

            message_lines = split_long_line(message_string, max_len, align=newline_len)
            message_lines = message_lines[:limit_lines]
            indexes.append({
                "lines": len(message_lines),
                "message_id": message["id"],
                "channel_id": message["channel_id"],
            })
            body.extend(message_lines)

    else:
        body = ["No messages found."]
    return title_line, body, indexes


def generate_extra_window_text(title_text, body_text, max_len):
    """Generate extra window title and body for summaries list view"""
    title_line = title_text[:max_len]
    body = split_long_line(body_text, max_len)
    return title_line, body


def generate_extra_window_assist(found, assist_type, max_len):
    """Generate extra window title and body for assist"""
    body = []
    prefix = ""
    if assist_type == 1:
        title_line = "Channel assist:"
        prefix = "#"
    elif assist_type == 2:
        title_line = "Username/role assist:"
        prefix = "@"
    elif assist_type == 3:
        title_line = "Emoji assist:"
        prefix = ""   # handled externally
    elif assist_type == 4:
        title_line = "Sticker assist:"
        prefix = ""
    elif assist_type == 5:
        title_line = "Command:"
        prefix = ""
    for item in found:
        body.append(f"{prefix}{item[0]}"[:max_len])
    if not body:
        body = ["No matches"]
    return title_line[:max_len], body


def generate_extra_window_reactions(reaction, details, max_len):
    """Generate extra window title and body for reactions"""
    title_line = f"Users who reacted {reaction["emoji"]}: "
    body = []
    for user in details:
        body.append(user["username"][:max_len])
    return title_line[:max_len], body


def generate_forum(threads, blocked, max_length, colors, colors_formatted, config):
    """
    Generate chat according to provided formatting.
    Possible options for forum_format:
        %thread_name
        %timestamp
        %msg_num
    Possible options for format_one_reaction:
        %reaction
        %count
    Possible options for format_timestamp:
        same as format codes for datetime package
    Possoble options for blocked_mode:
        0 - no blocking
        1 - mask blocked messages
        2 - hide blocked messages
    limit_thread_name normalizes length of thread name, by cropping them or appending spaces. Set to None to disable.
    use_nick will make it use nick instead global_name whenever possible.
    """
    forum_thread_format = config["format_forum"]
    forum_format_timestamp = config["format_forum_timestamp"]
    color_blocked = [colors[2]]
    color_format_forum = colors_formatted[7]   # 15 is unused
    blocked_mode = config["blocked_mode"]
    limit_thread_name = config["limit_thread_name"]
    convert_timezone = config["convert_timezone"]

    forum = []
    forum_format = []
    for thread in threads:
        owner_id = thread["owner_id"]

        # handle blocked messages
        if blocked_mode and owner_id in blocked:
            if blocked_mode == 1:
                thread["username"] = "blocked"
                thread["global_name"] = "blocked"
                thread["nick"] = "blocked"

        thread_line = (
            forum_thread_format
            .replace("%thread_name", normalize_string(thread["name"], limit_thread_name))
            .replace("%timestamp", generate_timestamp(thread["timestamp"], forum_format_timestamp, convert_timezone))
            .replace("%msg_count", normalize_int_str(thread["message_count"], 3))
        )
        if len(thread_line) > max_length:
            thread_line = thread_line[:max_length - 3] + "..."   # -3 to leave room for "..."
        forum.append(thread_line)

        if thread["owner_id"] in blocked:
            forum_format.append([color_blocked])
        else:
            forum_format.append(color_format_forum)

    return forum, forum_format


def generate_member_list(member_list_raw, guild_roles, width, use_nick, status_sign):
    """Generate member list"""
    # colors: 18 - green, 19 - orange, 20 - red
    member_list = []
    member_list_format = []
    if not member_list_raw:
        return ["No online members"], [[]]
    for member in member_list_raw:
        this_format = []
        if "id" in member:

            # format text
            if use_nick and member["nick"]:
                global_name_nick = member["nick"]
            elif member["global_name"]:
                global_name_nick = member["global_name"]
            else:
                global_name_nick = member["username"]
            text = f"{status_sign} {global_name_nick}"

            # get status color
            if member["status"] == "dnd":
                this_format.append([20, 0, 2])
            elif member["status"] == "idle":
                this_format.append([19, 0, 2])
            elif member["status"] == "offline":
                text = f"  {global_name_nick}"
                #this_format.append([])
            else:   # online
                this_format.append([18, 0, 2])

            # get role color
            member_roles = member["roles"]
            for role in guild_roles:
                if role["id"] in member_roles:
                    if role.get("color_id"):
                        this_format.append([role["color_id"], 2, width])
                    break

        else:   # user group
            text = "Unknown group"
            if member["group"] == "online":
                text = "Online"
            elif member["group"] == "offline":
                text = "Offline"
            group_id = member["group"]
            for role in guild_roles:
                if role["id"] == group_id:
                    text = role["name"]
            this_format = []

        member_list.append(trim_at_emoji(text[:width-1], width-1) + " ")
        member_list_format.append(this_format)

    return member_list, member_list_format


def generate_tree(dms, guilds, threads, unseen, mentioned, guild_positions, activities, collapsed, uncollapsed_threads, active_channel_id, dd_vline, dd_hline, dd_intersect, dd_corner, dd_pointer, dd_thread, dd_forum, dm_status_char, safe_emoji=False, show_invisible=False):
    """
    Generate channel tree according to provided formatting.
    tree_format keys:
        1XX - DM/Guild (top level drop down menu)
        2XX - category (second level drop down menu)
        3XX - channel (not drop-down)
        4XX - thread
        5XX - channel/forum (third level drop down menu)
        X0X - normal
        X1X - muted
        X2X - mentioned
        X3X - unread
        X4X - active channel
        X5X - active and mentioned
        XX0 - collapsed drop-down
        XX1 - uncollapsed drop-down
        XX2 - online DM
        XX3 - idle DM
        XX4 - DnD DM
        1100 - end of top level drop down
        1200 - end of second level drop down
        1300 - end of third level drop down
    Voice channels are ignored.
    """
    intersection = f"{dd_intersect}{dd_hline*2}"   # default: "|--"
    pass_by = f"{dd_vline}  "   # default: "|  "
    intersection_end = f"{dd_corner}{dd_hline*2}"   # default: "\\--"
    pass_by_end = f"{pass_by}{intersection_end}"   # default: "|  \\--"
    intersection_thread = f"{dd_intersect}{dd_hline}{dd_thread}"   # default: "|-<"
    end_thread = f"{dd_corner}{dd_hline}{dd_thread}"   # default: "\\-<"
    tree = []
    tree_format = []
    tree_metadata = []
    tree.append(f"{dd_pointer} Direct Messages")
    code = 101
    if 0 in collapsed:
        code = 100
    tree_format.append(code)
    tree_metadata.append({
        "id": 0,
        "type": -1,
        "name": None,
        "muted": False,
        "parent_index": None,
    })
    for dm in dms:
        if dm["name"]:
            name = dm["name"]
        elif dm["recipients"]:
            name = dm["recipients"][0]["username"]
        else:
            name = "Unknown DM"
        unseen_dm = False
        mentioned_dm = False
        if dm["id"] in unseen:
            unseen_dm = True
        if dm["id"] in mentioned:
            mentioned_dm = True
        muted = dm.get("muted", False)
        active = (dm["id"] == active_channel_id)
        if safe_emoji:
            name = replace_emoji_string(emoji.demojize(name))
        code = 300
        # get dm status
        if len(dm["recipients"]) == 1:
            for activity in activities:
                if activity["id"] == dm["recipients"][0]["id"]:
                    status = activity["status"]
                    if status == "online":
                        code += 2
                    elif status == "idle":
                        code += 3
                    elif status == "dnd":
                        code += 4
                    elif not show_invisible:
                        # "offline" means "invisible" but online
                        break
                    name = dm_status_char + name
                    break
        tree.append(f"{intersection} {name}")
        if muted:
            code += 10
        elif active and not mentioned_dm:
            code += 40
        elif active and mentioned_dm:
            code += 50
        elif mentioned_dm:
            code += 20
            tree_format[0] += 20
        elif unseen_dm:
            code += 30
            tree_format[0] += 30
        if not active and 0 in collapsed:
            tree_format[0] == 100
        tree_format.append(code)
        tree_metadata.append({
            "id": dm["id"],
            "type": dm["type"],
            "name": dm["name"],
            "muted": muted,
            "parent_index": 0,
        })
    tree.append("END-DMS-DROP-DOWN")
    tree_format.append(1100)
    tree_metadata.append(None)

    # sort guilds
    guilds_sorted = []
    guilds_used_index = []
    for guild_sorted_id in guild_positions:
        for num, guild in enumerate(guilds):
            if guild["guild_id"] == guild_sorted_id:
                guilds_sorted.append(guilds[num])
                guilds_used_index.append(num)
                break
    # add unsorted guilds
    for num, guild in enumerate(guilds):
        if num not in guilds_used_index:
            guilds_sorted.append(guild)

    for guild in guilds_sorted:
        # prepare data
        muted_guild = guild.get("muted", False)
        unseen_guild = False
        ping_guild = False
        for guild_th in threads:
            if guild_th["guild_id"] == guild["guild_id"]:
                threads_guild = guild_th["channels"]
                break
        else:
            threads_guild = []

        # sort categories and channels
        categories = []
        categories_position = []
        for channel in guild["channels"]:
            if channel["type"] == 4:
                # categories are also hidden if they have no visible channels
                muted = channel.get("muted", False)
                hidden = 1
                if channel.get("hidden"):
                    hidden = 2
                else:
                    hidden = 1
                # using local storage instead for collapsed
                # collapsed = category_set["collapsed"]
                categories.append({
                    "id": channel["id"],
                    "name": channel["name"],
                    "channels": [],
                    "muted": muted,
                    "collapsed": False,
                    "hidden": hidden,
                    "unseen": False,
                    "ping": False,
                })
                categories_position.append(channel["position"])

        # separately sort channels in their categories
        bare_channels = []
        bare_channels_position = []
        for channel in guild["channels"]:
            if channel["type"] in (0, 5, 15):
                # find this channel threads, if any
                for channel_th in threads_guild:
                    if channel_th["channel_id"] == channel["id"]:
                        threads_ch = channel_th["threads"]
                        break
                else:
                    threads_ch = []
                unseen_ch = False
                mentioned_ch = False
                if channel["id"] in unseen:
                    unseen_ch = True
                if channel["id"] in mentioned:
                    mentioned_ch = True
                for category in categories:
                    if channel["parent_id"] == category["id"]:
                        muted_ch = channel.get("muted", False)
                        hidden_ch = channel.get("hidden", False)
                        # hide restricted channels now because they can be marked as unseen/ping
                        if not channel.get("permitted", False):
                            hidden_ch = True
                        if not (category["muted"] or category["hidden"] or hidden_ch or muted_ch):
                            if unseen_ch:
                                category["unseen"] = True
                                unseen_guild = True
                            if mentioned_ch:
                                category["ping"] = True
                                ping_guild = True
                        if not hidden_ch and category["hidden"] != 2:
                            category["hidden"] = False
                        active = (channel["id"] == active_channel_id)
                        category["channels"].append({
                            "id": channel["id"],
                            "name": channel["name"],
                            "position": channel["position"],
                            "muted": muted_ch,
                            "hidden": hidden_ch,
                            "unseen": unseen_ch,
                            "ping": mentioned_ch,
                            "active": active,
                            "threads": threads_ch,
                            "forum": channel["type"] == 15,
                        })
                        break
                else:
                    # top level channels can be inaccessible
                    muted_ch = channel.get("muted", False)
                    hidden_ch = channel.get("hidden", False)
                    if not channel.get("permitted", False):
                        hidden_ch = True
                    active = channel["id"] == active_channel_id
                    bare_channels.append({
                        "id": channel["id"],
                        "name": channel["name"],
                        "channels": None,
                        "muted": muted_ch,
                        "hidden": hidden_ch,
                        "unseen": unseen_ch,
                        "ping": mentioned_ch,
                        "active": active,
                    })
                    bare_channels_position.append(channel["position"])
        categories += bare_channels
        categories_position += bare_channels_position

        # sort categories by position key
        categories = sort_by_indexes(categories, categories_position)

        # add guild to the tree
        name = guild["name"]
        if safe_emoji:
            name = replace_emoji_string(emoji.demojize(name))
        tree.append(f"{dd_pointer} {name}")
        code = 101
        if muted_guild:
            code += 10
        elif ping_guild:
            code += 20
        elif unseen_guild:
            code += 30
        if guild["guild_id"] in collapsed:
            code -= 1
        tree_format.append(code)
        guild_index = len(tree_format) - 1
        tree_metadata.append({
            "id": guild["guild_id"],
            "type": -1,
            "name": guild["name"],
            "muted": muted_guild,
            "parent_index": None,
        })

        # add categories to the tree
        for category in categories:
            if not category["hidden"]:
                if category["channels"]:
                    category_index = len(tree_format)

                    # sort channels by position key
                    channels_position = []
                    for channel in category["channels"]:
                        channels_position.append(channel["position"])
                    category["channels"] = sort_by_indexes(category["channels"], sorted_indexes(channels_position))

                    # add to the tree
                    name = category["name"]
                    if safe_emoji:
                        name = replace_emoji_string(emoji.demojize(name))
                    tree.append(f"{intersection}{dd_pointer} {name}")
                    code = 201
                    if category["muted"]:
                        code += 10
                    elif category["ping"]:
                        code += 20
                    elif category["unseen"]:
                        code += 30
                    if category["collapsed"] or category["id"] in collapsed:
                        code -= 1
                    tree_format.append(code)
                    tree_metadata.append({
                        "id": category["id"],
                        "type": 4,
                        "name": category["name"],
                        "muted": category["muted"],
                        "parent_index": guild_index,
                    })

                    # add channels to the tree
                    category_channels = category["channels"]
                    for channel in category_channels:
                        if not channel["hidden"]:
                            name = channel["name"]
                            forum = channel["forum"]
                            channel_threads = channel.get("threads", [])
                            channel_index = len(tree_format)
                            if safe_emoji:
                                name = replace_emoji_string(emoji.demojize(name))
                            if forum:
                                tree.append(f"{pass_by}{intersection}{dd_forum} {name}")
                            elif channel_threads:
                                tree.append(f"{pass_by}{intersection}{dd_pointer} {name}")
                            else:
                                tree.append(f"{pass_by}{intersection} {name}")
                            if channel_threads:
                                code = 500
                            else:
                                code = 300
                            if channel["muted"] and not channel["active"]:
                                code += 10
                            elif channel["active"] and channel["ping"]:
                                code += 50
                            elif channel["active"]:
                                code += 40
                            elif channel["ping"]:
                                code += 20
                            elif channel["unseen"]:
                                code += 30
                            if channel_threads and (channel["id"] in uncollapsed_threads):
                                code += 1
                            tree_format.append(code)
                            tree_metadata.append({
                                "id": channel["id"],
                                "type": 15 if forum else 0,
                                "name": channel["name"],
                                "muted": channel["muted"],
                                "parent_index": category_index,
                            })

                            # add channel threads to the tree
                            for thread in channel_threads:
                                joined = thread["joined"]
                                if not joined and forum:
                                    # skip non-joined threads for forum
                                    continue
                                name = thread["name"]
                                thread_id = thread["id"]
                                active = (thread_id == active_channel_id)
                                if safe_emoji:
                                    name = replace_emoji_string(emoji.demojize(name))
                                tree.append(f"{pass_by}{pass_by}{intersection_thread} {name}")
                                code = 400
                                if (thread["muted"] or not joined) and not active:
                                    code += 10
                                elif thread_id == active_channel_id and thread_id in mentioned:
                                    code += 50
                                elif active:
                                    code += 40
                                elif thread_id in mentioned:
                                    code += 20
                                elif thread_id in unseen:
                                    code += 30
                                tree_format.append(code)
                                tree_metadata.append({
                                    "id": thread["id"],
                                    "type": thread["type"],
                                    "name": thread["name"],
                                    "muted": thread["muted"],
                                    "parent_index": channel_index,
                                })
                            if channel_threads:
                                tree.append(f"{pass_by}{pass_by}END-CHANNEL-DROP-DOWN")
                                tree_format.append(1300)
                                tree_metadata.append(None)

                    tree.append(f"{pass_by}END-CATEGORY-DROP-DOWN")
                    tree_format.append(1200)
                    tree_metadata.append(None)
                else:
                    name = category["name"]
                    if safe_emoji:
                        name = replace_emoji_string(emoji.demojize(name))
                    tree.append(f"{intersection} {name}")
                    code = 300
                    if muted and not channel["active"]:
                        code += 10
                    elif category["ping"]:
                        code += 20
                    elif category["unseen"]:
                        code += 30
                    tree_format.append(code)
                    category["muted"] = muted
                    tree_metadata.append({
                        "id": category["id"],
                        "type": 0,
                        "name": category["name"],
                        "muted": category["muted"],
                        "parent_index": guild_index,
                    })

        tree.append("END-GUILD-DROP-DOWN")
        tree_format.append(1100)
        tree_metadata.append(None)

    # add drop-down corners
    for num, code in enumerate(tree_format):
        if code >= 1000:
            if code == 1300 and (tree_format[num - 1] // 100) % 10 == 4:   # thread end if there are threads
                tree[num - 1] = f"{pass_by}{pass_by}{end_thread}{tree[num - 1][9:]}"
            elif tree[num - 1][:4] != f"{intersection}{dd_pointer}":
                if (tree_format[num - 1] < 500 or tree_format[num - 1] > 599) and tree[num][:3] == pass_by:
                    # skipping colapsed forums
                    tree[num - 1] = pass_by_end + tree[num - 1][6:]
                elif tree[num - 1][:3] == intersection:
                    tree[num - 1] = intersection_end + tree[num - 1][3:]
            if code == 1100 and tree_format[num - 1] == 1200:
                for back, _ in enumerate(tree_format):
                    if tree[num - back - 1][:3] == pass_by:
                        tree[num - back - 1] = "   " + tree[num - back - 1][3:]
                    else:
                        tree[num - back - 1] = intersection_end + tree[num - back - 1][3:]
                        break
            if code == 1200 and tree_format[num - 1] == 1300:
                for back, _ in enumerate(tree_format):
                    if tree[num - back - 2][3:6] == pass_by:
                        tree[num - back - 2] = f"{pass_by}   {tree[num - back - 2][6:]}"
                    else:
                        tree[num - back - 2] = pass_by_end + tree[num - back - 2][6:]
                        break
    return tree, tree_format, tree_metadata


def update_tree_parents(tree_format, tree_metadata, num, code, match_conditions):
    """
    Update tree parents recursively with specified code and match_conditions.
    Num is index of tree_format key.
    Code is single digit from tree_format, representing second digit in key.
    Match conditions is list of same codes that will be replaced.
    """
    parent_index = tree_metadata[num]["parent_index"]
    for i in range(3):   # avoid infinite loops, there can be max 3 nest levels
        if parent_index is None:
            break
        parent_code = tree_format[parent_index]
        parent_first_digit = parent_code % 10
        parent_second_digit = (parent_code % 100) // 10
        if parent_second_digit in match_conditions:
            tree_format[parent_index] = parent_first_digit * 100 + code * 10 + parent_first_digit
        parent_index = tree_metadata[parent_index]["parent_index"]
    return tree_format


def update_tree(tree_format, tree_metadata, guilds, unseen, mentioned, active_channel_id, seen_id):
    """
    Update format for alread generated tree.
    Optimised version of init_tree for when tree is already generated.
    Unused because it marks unseen wrong aand performance gain is insignificant.
    Threads and forums not implemented.
    """
    unseen_channels = [x["channel_id"] for x in unseen]
    for num, code in enumerate(tree_format):
        if 300 <= code <= 399:
            obj_id = tree_metadata[num]["id"]
            second_digit = (code % 100) // 10
            first_digit = code % 10
            if obj_id in unseen_channels:
                if second_digit == 0:
                    tree_format[num] = 330 + first_digit
                    tree_format = update_tree_parents(tree_format, tree_metadata, num, 3, (0, ))
            if obj_id in mentioned:
                if second_digit in (0, 3):
                    tree_format[num] = 320 + first_digit
                    tree_format = update_tree_parents(tree_format, tree_metadata, num, 2, (0, 3))
                elif second_digit == 4:
                    tree_format[num] = 350 + first_digit
                    tree_format = update_tree_parents(tree_format, tree_metadata, num, 3, (4, ))
            if obj_id == active_channel_id:   # set active channel
                if second_digit == 2:
                    tree_format[num] = 350 + first_digit
                else:
                    tree_format[num] = 340 + first_digit
            elif second_digit in (4, 5):   # disable previous active channel
                if tree_metadata[num]["muted"]:
                    tree_format[num] = 310 + first_digit
                else:
                    tree_format[num] = 300 + first_digit
            if obj_id == seen_id:   # remove unseen/ping
                if second_digit in (2, 3):
                    tree_format[num] = 300 + first_digit
                    tree_format = update_tree_parents(tree_format,tree_metadata, num, 0, (2, 3))

        # unloaded guild drop downs (guilds without downloaded channel permissions)
        if 100 <= code <= 199:
            guild_id = tree_metadata[num]["id"]
            for channel in unseen:
                channel_id = channel["channel_id"]
                if channel["guild_id"] == guild_id:
                    # trace that channel to the guild while skiping muted and hidden
                    # find this guild
                    for guild in guilds:
                        if guild["guild_id"] == guild_id:
                            parent_id = None
                            muted = guild.get("muted", False)
                            # find this channel stats
                            if not muted:
                                for channel_g in guild["channels"]:
                                    if channel_g["id"] == channel_id:
                                        muted = not channel_g.get("permitted", True) or (channel_g.get("muted", False) or (channel_g.get("hidden", False) and channel_g["type"] in (0, 5)))
                                        parent_id = channel_g.get("parent_id")
                                        break
                            # apply channels parent (category) stats
                            if not muted:
                                for channel_g in guild["channels"]:
                                    if channel_g["id"] == parent_id:
                                        muted = channel_g.get("muted", False) or channel_g.get("hidden", False)
                                        break
                            break
                    if not muted:
                        first_digit = code % 10
                        # check if its also mention
                        if channel_id in mentioned:
                            if channel_id == active_channel_id:
                                tree_format[num] = 120 + first_digit
                            else:
                                tree_format[num] = 150 + first_digit
                            break
                        else:
                            tree_format[num] = 130 + first_digit
                            # not breaking because some other channel might mention
    return tree_format
