import curses
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)
DAY_MS = 24*60*60*1000
DISCORD_EPOCH_MS = 1420070400000

match_emoji_string = re.compile(r"<.*?:.*?:\d*?>")
match_emoji_name = re.compile(r"(?<=<:).*?(?=:)")
match_a_emoji_name = re.compile(r"(?<=<a:).*?(?=:)")
match_mention_string = re.compile(r"<@\d*?>")
match_mention_id = re.compile(r"(?<=<@)\d*?(?=>)")
match_role_string = re.compile(r"<@&\d*?>")
match_role_id = re.compile(r"(?<=<@&)\d*?(?=>)")
match_channel_string = re.compile(r"<#\d*?>")
match_channel_id = re.compile(r"(?<=<#)\d*?(?=>)")
match_escaped_md = re.compile(r"\\(?=[^a-zA-Z\d\s])")
match_md_underline = re.compile(r"(?<!\\)((?<=_))?__[^_]+__")
match_md_bold = re.compile(r"(?<!\\)((?<=\*))?\*\*[^\*]+\*\*")
match_md_strikethrough = re.compile(r"(?<!\\)((?<=~))?~~[^~]+~~")   # unused
match_md_italic = re.compile(r"(?<!\\)(?<!\\_)(((?<=_))?_[^_]+_)|(((?<=\*))?\*[^\*]+\*)")
match_url = re.compile(r"https?:\/\/\w+(\.\w+)+[^\r\n\t\f\v )\]>]*")


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


def generate_timestamp(discord_time, format_string, timezone=True):
    """Converts discord timestamp string to formatted string and optionally converts to current timezone"""
    try:
        time_obj = datetime.strptime(discord_time, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        time_obj = datetime.strptime(discord_time, "%Y-%m-%dT%H:%M:%S%z")   # edge case
    if timezone:
        time_obj = time_obj.astimezone()
    return datetime.strftime(time_obj, format_string)


def day_from_snowflake(snowflake, timezone=True):
    """Extract day from discord snowflake with optional timezone conversion"""
    snowflake = int(snowflake)
    if timezone:
        time_obj = datetime.fromtimestamp(((snowflake >> 22) + DISCORD_EPOCH_MS) / 1000).astimezone()
        time_obj = time_obj.astimezone()
        return time_obj.day
    # faster than datetime, but no timezone conversion
    return ((snowflake >> 22) + DISCORD_EPOCH_MS) / DAY_MS


def clean_emojis(line):
    """
    Transform emoji strings into nicer looking ones:
    `some text <:emoji_name:emoi_id> more text` ---> `some text <emoji_name> more text`
    """
    for string_match in re.findall(match_emoji_string, line):
        text = re.search(match_emoji_name, string_match)
        if not text:
            text = re.search(match_a_emoji_name, string_match)   # animated
        if text:
            line = line.replace(string_match, f"<{text.group()}>")
    return line


def replace_mention(line, usernames_ids):
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
    `some text <#channel_id> more text` --> `some text >channel_name more text`
    """
    for string_match in re.findall(match_channel_string, line):
        text = re.search(match_channel_id, string_match)
        for channel in chanels_ids:
            if text.group() == channel["id"]:
                line = line.replace(string_match, f">{channel["name"]}")
                break
    return line


def replace_escaped_md(line):
    r"""
    Replace escaped markdown characters.
    eg "\:" --> ":"
    """
    return re.sub(match_escaped_md, "", line)


def format_md_all(line, content_start):
    """
    Replace all supported formatted markdown strings and return list of their formats.
    This should be called only after curses has initialized color.
    Strikethrough is apparently not supported by curses.
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


def format_url_one_line(urls, line_len, newline_len, color):
    """Generate format for urls in one line"""
    line_format = []
    for url in urls:
        if url[0] > line_len or url[1] < newline_len:
            continue
        if url[0] >= newline_len:
            if url[1] < line_len:
                line_format.append([color, url[0], url[1]])
            else:
                line_format.append([color, url[0], line_len])
        elif url[1] < line_len:
            line_format.append([color, newline_len, url[1]])
        else:
            line_format.append([color, newline_len, line_len])
    return line_format


def clean_type(embed_type):
    r"""
    Clean embed type string from excessive information
    eg. `image\png` ---> `image`
    """
    return embed_type.split("/")[0]


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

    chat = []
    chat_format = []
    indexes = []
    len_edited = len(edited_string)
    enable_separator = format_date and date_separator

    # load colors
    color_default = [colors[0]]
    color_blocked = [colors[2]]
    color_deleted = [colors[3]]
    color_separator = [colors[4]]
    color_chat_edited = colors_formatted[4][0]
    color_mention_chat_edited = colors_formatted[10][0]
    color_chat_url = colors_formatted[5][0][0]
    color_mention_chat_url = colors_formatted[11][0][0]
    # load formatted colors: [[id], [id, start, end]...]
    color_message = colors_formatted[0]
    color_newline = colors_formatted[1]
    color_reply = colors_formatted[2]
    color_reactions = colors_formatted[3]
    color_mention_message = colors_formatted[6]
    color_mention_newline = colors_formatted[7]
    color_mention_reply = colors_formatted[8]
    color_mention_reactions = colors_formatted[9]

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

    if format_message.find("%username") > format_message.find("%global_name"):
        end_name = pre_name_len + limit_username + 1
    else:
        end_name = pre_name_len + limit_global_name + 1

    for num, message in enumerate(messages):
        temp_chat = []   # stores only one multiline message
        temp_format = []
        mentioned = False
        edited = message["edited"]
        user_id = message["user_id"]

        # select base color
        color_base = color_default
        for mention in message["mentions"]:
            if mention["id"] == my_id:
                mentioned = True
                break
        for role in message["mention_roles"]:
            if bool([i for i in my_roles if i in message["mention_roles"]]):
                mentioned = True
                break

        # skip deleted
        disable_formatting = False
        if "deleted" in message:
            if keep_deleted:
                color_base = color_deleted
                disable_formatting = True
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
                message["embeds"] = None
                color_base = color_blocked
            else:
                indexes.append(0)
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
                    content = replace_channels(replace_roles(replace_mention(clean_emojis(replace_escaped_md(message["referenced_message"]["content"])), message["referenced_message"]["mentions"]), roles), channels)
                if reply_embeds:
                    for embed in reply_embeds:
                        if embed["url"] not in content:
                            if content:
                                content += "\n"
                            content += f"[{clean_type(embed["type"])} embed]: {embed["url"]}"
                reply_line = (
                    format_reply
                    .replace("%username", normalize_string(message["referenced_message"]["username"], limit_username))
                    .replace("%global_name", normalize_string(str(global_name_nick), limit_global_name))
                    .replace("%timestamp", generate_timestamp(message["referenced_message"]["timestamp"], format_timestamp, convert_timezone))
                    .replace("%content", content.replace("\r", "").replace("\n", ""))
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
                reply_line = reply_line[:max_length - 3] + "..."   # -3 to leave room for ""..."
            temp_chat.append(reply_line)
            if disable_formatting or reply_color_format == color_blocked:
                temp_format.append([reply_color_format])
            elif mentioned:
                temp_format.append(color_mention_reply)
            else:
                temp_format.append(color_reply)

        # main message
        if use_nick and message["nick"]:
            global_name_nick = message["nick"]
        elif message["global_name"]:
            global_name_nick = message["global_name"]
        else:
            global_name_nick = message["username"]
        embeds = message["embeds"]
        content = ""
        if message["content"]:
            content = replace_channels(replace_roles(replace_mention(clean_emojis(message["content"]), message["mentions"]), roles), channels)
        if embeds:
            for embed in embeds:
                if embed["url"] and embed["url"] not in content:
                    if content:
                        content += "\n"
                    content += f"[{clean_type(embed["type"])} embed]: {embed["url"]}"
        message_line = (
            format_message
            .replace("%username", normalize_string(message["username"], limit_username))
            .replace("%global_name", normalize_string(str(global_name_nick), limit_global_name))
            .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
            .replace("%edited", edited_string if edited else "")
            .replace("%content", content)
        )
        message_line, md_format = format_md_all(message_line, pre_content_len)
        message_line = replace_escaped_md(message_line)


        # find all urls
        urls = []
        if color_chat_url:
            for match in re.finditer(match_url, message_line):
                urls.append([match.start(), match.end()])

        # limit message_line and split to multiline
        newline_index = max_length
        if len(message_line) > max_length:
            newline_index = len(message_line[:max_length].rsplit(" ", 1)[0])   #  splits sentence on space
            if newline_index <= len(
                format_newline
                .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
                .replace("%content", ""),
                ):
                    newline_index = max_length
            # if there is \n on current line, use its position to split line
            if "\n" in message_line[:newline_index]:
                newline_index = message_line.index("\n")
            next_line = message_line[newline_index+1:]   # +1 to remove space and \n
            message_line = message_line[:newline_index]
        elif "\n" in message_line:
            newline_index = message_line.index("\n")
            next_line = message_line[newline_index+1:]
            message_line = message_line[:newline_index]
        else:
            next_line = None
        temp_chat.append(message_line)

        # formatting
        if disable_formatting:
            temp_format.append([color_base])
        elif mentioned:
            format_line = color_mention_message[:]
            format_line += md_format
            if color_chat_url:
                format_line += format_url_one_line(urls, newline_index+1, 0, color_mention_chat_url)
            if alt_role_color:
                format_line.append([alt_role_color, pre_name_len, end_name])
            if edited and not next_line:
                format_line.append(color_mention_chat_edited + [len(message_line) - len_edited, len(message_line)])
            temp_format.append(format_line)
        else:
            format_line = color_message[:]
            format_line += md_format
            if color_chat_url:
                new_format = format_url_one_line(urls, newline_index+1, 0, color_chat_url)
                format_line += new_format
            if role_color:
                format_line.append([role_color, pre_name_len, end_name])
            if edited and not next_line:
                format_line.append([*color_chat_edited, len(message_line) - len_edited, len(message_line)])
            temp_format.append(format_line)

        # newline
        line_num = 1
        while next_line:
            new_line = (
                format_newline
                .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
                .replace("%content", next_line)
            )
            new_line, md_format = format_md_all(new_line, pre_content_len)
            content_index_correction = newline_len - 1 - newline_index
            for url in urls:
                url[0] += content_index_correction
                url[1] += content_index_correction

            # limit new_line and split to next line
            if len(new_line) > max_length:
                newline_index = len(new_line[:max_length].rsplit(" ", 1)[0])
                if newline_index <= newline_len:
                    newline_index = max_length
                if "\n" in new_line[:newline_index]:
                    newline_index = new_line.index("\n")
                next_line = new_line[newline_index+1:]
                new_line = new_line[:newline_index]
            elif "\n" in new_line:
                newline_index = new_line.index("\n")
                next_line = new_line[newline_index+1:]
                new_line = new_line[:newline_index]
            else:
                next_line = None
            # formatting
            temp_chat.append(new_line)
            if disable_formatting:
                temp_format.append([color_base])
            elif mentioned:
                format_line = color_mention_newline[:]
                format_line += md_format
                if color_chat_url:
                    format_line += format_url_one_line(urls, newline_index+1, newline_len, color_mention_chat_url)
                if edited and not next_line:
                    format_line.append(color_mention_chat_edited + [len(new_line) - len_edited, len(new_line)])
                temp_format.append(format_line)
            else:
                format_line = color_newline[:]
                format_line += md_format
                if color_chat_url:
                    format_line += format_url_one_line(urls, newline_index+1, newline_len, color_chat_url)
                if edited and not next_line:
                    format_line.append([*color_chat_edited, len(new_line) - len_edited, len(new_line)])
                temp_format.append(format_line)
            line_num += 1

        # reactions
        if message["reactions"]:
            reactions = []
            for reaction in message["reactions"]:
                reactions.append(
                    format_one_reaction
                    .replace("%reaction", reaction["emoji"])
                    .replace("%count", str(reaction["count"])),
                )
            reactions = reactions_separator.join(reactions)
            reactions_line = (
                format_reactions
                .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
                .replace("%reactions", reactions)
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
        indexes.append(len(temp_chat))

        # invert message lines order and append them to chat
        # it is inverted because chat is drawn from down to upside
        chat.extend(temp_chat[::-1])
        chat_format.extend(temp_format[::-1])
    return chat, chat_format, indexes


def generate_status_line(my_user_data, my_status, unseen, typing, active_channel, action, tasks, format_status_line, format_rich, limit_typing=30, use_nick=True):
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
    Possible options for format_rich:
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
        rich = (
            format_rich
            .replace("%name", my_status["activities"][0]["name"])
            .replace("%state", state if state else "")
            .replace("%details", details if details else "")
            .replace("%small_text", sm_txt if sm_txt else "")
            .replace("%large_text", lg_txt if lg_txt else "")
        )
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
        action_string = f"Repling {ping}to {name}"
    elif action["type"] == 2:   # editing
        action_string = "Editing the message"
    elif action["type"] == 3:   # deleting
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

    if my_status["custom_status_emoji"]:
        custom_status_emoji = str(my_status["custom_status_emoji"]["name"])
    else:
        custom_status_emoji = ""

    # running long tasks
    tasks = sorted(tasks, key=lambda x:x[1], reverse=False)
    if len(tasks) == 0:
        task = ""
    elif len(tasks) == 1:
        task = tasks[0][0]
    else:
        task = f"{tasks[0][0]} (+{len(tasks) - 1})"

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
    )


def generate_prompt(my_user_data, active_channel, format_prompt):
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
        .replace("%global_name", str(my_user_data["global_name"]))
        .replace("%username", my_user_data["username"])
        .replace("%server", guild if guild else "DM")
        .replace("%channel", str(active_channel["channel_name"]))
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


def generate_tree(dms, guilds, dms_settings, guilds_settings, unseen, mentioned, guild_positions, collapsed, active_channel_id, dd_vline, dd_hline, dd_intersect, dd_corner, dd_pointer):
    """
    Generate channel tree according to provided formatting.
    tree_format keys:
        1XX - top level drop down menu (DM/Guild)
        2XX - second level drop down menu (category/forum)
        3XX - channel
        X0X - normal
        X1X - muted
        X2X - mentioned
        X3X - unread
        X4X - active channel
        X5X - active and mentioned
        XX0 - collapsed drop-down
        XX1 - uncollapsed drop-down
        1100 - end of top level drop down
        1200 - end of second level drop down
    Voice channels are ignored.
    """
    intersection = f"{dd_intersect}{dd_hline*2}"   # default: "|--"
    pass_by = f"{dd_vline}  "   # default: "|  "
    intersection_end = f"{dd_corner}{dd_hline*2}"   # default: "\\--"
    pass_by_end = f"{pass_by}{intersection_end}"   # default: "|  \\--"
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
        else:
            name = dm["recipients"][0]["username"]
        muted = False
        unseen_dm = False
        mentioned_dm = False
        if dm["id"] in unseen:
            unseen_dm = True
        if dm["id"] in mentioned:
            mentioned_dm = True
        for dm_settings in dms_settings:
            if dm_settings["id"] == dm["id"]:
                muted = dm_settings["muted"]
                break
        active = (dm["id"] == active_channel_id)
        tree.append(f"{intersection} {name}")
        code = 300
        if muted:
            code += 10
        elif active and not mentioned:
            code += 40
        elif active and mentioned:
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
    for guild_sorted_id in guild_positions:
        for num, guild in enumerate(guilds):
            if guild["guild_id"] == guild_sorted_id:
                guilds_sorted.append(guilds.pop(num))
                break
    # add unsorted guilds
    guilds_sorted = guilds_sorted + guilds

    for guild in guilds_sorted:
        # prepare data
        muted_guild = False
        unseen_guild = False
        ping_guild = False
        active_guild = False
        owned = guild["owned"]

        # search for guild and channel settings
        found_setings = False
        for guild_settings in guilds_settings:
            if guild_settings["guild_id"] == guild["guild_id"]:
                muted_guild = guild_settings["muted"]
                found_setings = True
                break

        # sort categories and channels
        categories = []
        categories_position = []
        for channel in guild["channels"]:
            if channel["type"] == 4:
                muted = False   # default settings
                collapsed_ch = False
                # categories are hidden only if they have no visible channels
                if found_setings:
                    for category_set in guild_settings["channels"]:
                        if category_set["id"] == channel["id"]:
                            muted = category_set["muted"]
                            # using local storage for collapsed
                            # collapsed = category_set["collapsed"]
                            break
                categories.append({
                    "id": channel["id"],
                    "name": channel["name"],
                    "channels": [],
                    "muted": muted,
                    "collapsed": collapsed_ch,
                    "hidden": True,
                    "unseen": False,
                    "ping": False,
                })
                categories_position.append(channel["position"])

        # separately sort channels in their categories
        bare_channels = []
        bare_channels_position = []
        for channel in guild["channels"]:
            if channel["type"] == 0:
                unseen_ch = False
                mentioned_ch = False
                if channel["id"] in unseen:
                    unseen_ch = True
                if channel["id"] in mentioned:
                    mentioned_ch = True
                done = False
                for category in categories:
                    if channel["parent_id"] == category["id"]:
                        muted_ch = False
                        hidden_ch = True   # channels not in settings are inaccessible
                        if found_setings:
                            for channel_set in guild_settings["channels"]:
                                if channel_set["id"] == channel["id"]:
                                    muted_ch = channel_set["muted"]
                                    hidden_ch = channel_set["hidden"]
                                    break
                        if owned or not found_setings:
                            hidden_ch = False   # if there are no settings - all channels are accessible
                        if not hidden_ch:
                            category["hidden"] = False
                        active = (channel["id"] == active_channel_id)
                        if active:
                            # unwrap top level guild
                            active_guild = True
                        category["channels"].append({
                            "id": channel["id"],
                            "name": channel["name"],
                            "position": channel["position"],
                            "muted": muted_ch,
                            "hidden": hidden_ch,
                            "unseen": unseen_ch,
                            "ping": mentioned_ch,
                            "active": active,
                        })
                        if not (category["muted"] or hidden_ch or muted_ch):
                            if unseen_ch:
                                category["unseen"] = True
                                unseen_guild = True

                            if mentioned_ch:
                                category["ping"] = True
                                ping_guild = True
                        done = True
                        break
                if not done:
                    # top level channles can be inaccessible
                    muted_ch = False
                    hidden_ch = True
                    if found_setings:
                        for channel_set in guild_settings["channels"]:
                            if channel_set["id"] == channel["id"]:
                                muted_ch = channel_set["muted"]
                                hidden_ch = channel_set["hidden"]
                                break
                    if owned or not found_setings:
                        hidden_ch = False   # if there are no settings - all channels are accessible
                    active = channel["id"] == active_channel_id
                    if active:
                        # unwrap top level guild
                        active_guild = True
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
        tree.append(f"{dd_pointer} {guild["name"]}")
        code = 101
        if muted_guild:
            code += 10
        elif ping_guild:
            code += 20
        elif unseen_guild:
            code += 30
        if not active_guild and guild["guild_id"] in collapsed:
            code -= 1
        tree_format.append(code)
        guild_index = len(tree_format) - 1
        tree_metadata.append({
            "id": guild["guild_id"],
            "type": -1,
            "name": guild["name"],
            "muted": muted,
            "parent_index": None,
        })

        # add channels to the tree
        for category in categories:
            if not category["hidden"]:
                category_index = len(tree_format)
                if category["channels"]:
                    # sort channels by position key
                    channels_position = []
                    for channel in category["channels"]:
                        channels_position.append(channel["position"])
                    category["channels"] = sort_by_indexes(category["channels"], sorted_indexes(channels_position))

                    # add to the tree
                    tree.append(f"{intersection}{dd_pointer} {category["name"]}")
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
                    category_channels = category["channels"]
                    for channel in category_channels:

                        if not channel["hidden"]:
                            tree.append(f"{pass_by}{intersection} {channel["name"]}")
                            code = 300
                            if channel["muted"] and not channel["active"]:
                                code += 10
                            elif channel["active"] and not channel["ping"]:
                                code += 40
                            elif channel["active"] and channel["ping"]:
                                code += 50
                            elif channel["ping"]:
                                code += 20
                            elif channel["unseen"]:
                                code += 30
                            if channel["active"]:
                                code += 1
                            tree_format.append(code)
                            tree_metadata.append({
                                "id": channel["id"],
                                "type": 0,
                                "name": channel["name"],
                                "muted": channel["muted"],
                                "parent_index": category_index,
                            })
                    tree.append(f"{pass_by}END-CATEGORY-DROP-DOWN")
                    tree_format.append(1200)
                    tree_metadata.append(None)
                else:
                    tree.append(f"{intersection} {category["name"]}")
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
            if tree[num - 1][:4] != f"{intersection}{dd_pointer}":
                if tree[num][:3] == pass_by:
                    tree[num - 1] = pass_by_end + tree[num - 1][6:]
                elif tree[num - 1][:3] == intersection:
                    tree[num - 1] = intersection_end + tree[num - 1][3:]
            if tree_format[num - 1] >= 1000:
                for back, _ in enumerate(tree_format):
                    if tree[num - back - 1][:3] == pass_by:
                        tree[num - back - 1] = "   " + tree[num - back - 1][3:]
                    else:
                        tree[num - back - 1] = intersection_end + tree[num - back - 1][3:]
                        break

    return tree, tree_format, tree_metadata


def update_tree_parents(tree_format,tree_metadata, num, code, match_conditions):
    """Update parents recursively with specified code and match_conditions"""
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


def update_tree(tree_format, tree_metadata, unseen, mentioned, active_channel_id, seen_id):
    """Update format of alread generate tree."""
    for num, code in enumerate(tree_format):
        if 300 <= code <= 399:
            entry_id = tree_metadata[num]["id"]
            second_digit = (code % 100) // 10
            first_digit = code % 10
            if entry_id in unseen:
                if second_digit == 0:
                    tree_format[num] = 330 + first_digit
                    tree_format = update_tree_parents(tree_format, tree_metadata, num, 3, (0, ))
            if entry_id in mentioned:
                if second_digit in (0, 3):
                    tree_format[num] = 320 + first_digit
                    tree_format = update_tree_parents(tree_format, tree_metadata, num, 2, (0, 3))
                elif second_digit == 4:
                    tree_format[num] = 350 + first_digit
                    tree_format = update_tree_parents(tree_format, tree_metadata, num, 3, (4, ))
            if entry_id == active_channel_id:   # set active channel
                if second_digit == 2:
                    tree_format[num] = 350 + first_digit
                else:
                    tree_format[num] = 340 + first_digit
            elif second_digit in (4, 5):   # disable previous active channel
                if tree_metadata[num]["muted"]:
                    tree_format[num] = 310 + first_digit
                else:
                    tree_format[num] = 300 + first_digit
            if entry_id == seen_id:   # remove unseen/ping
                if second_digit in (2, 3):
                    tree_format[num] = 300 + first_digit
                    tree_format = update_tree_parents(tree_format,tree_metadata, num, 0, (2, 3))
    return tree_format
