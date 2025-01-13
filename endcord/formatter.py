import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


match_emoji_string = re.compile(r"<.*?:.*?:\d*?>")
match_emoji_name = re.compile(r"(?<=<:).*?(?=:)")
match_a_emoji_name = re.compile(r"(?<=<a:).*?(?=:)")
match_after_slash = re.compile(r"//?(.*)")
match_mention_string = re.compile(r"<@\d*?>")
match_mention_id = re.compile(r"(?<=<@)\d*?(?=>)")
match_role_string = re.compile(r"<@&\d*?>")
match_role_id = re.compile(r"(?<=<@&)\d*?(?=>)")
match_channel_string = re.compile(r"<#\d*?>")
match_channel_id = re.compile(r"(?<=<#)\d*?(?=>)")


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


def replace_channels(line, cchanels_ids):
    """
    Transforms channels string into nicer looking one:
    `some text <#channel_id> more text` --> `some text >channel_name more text`
    """
    for string_match in re.findall(match_channel_string, line):
        text = re.search(match_channel_id, string_match)
        for channel in cchanels_ids:
            if text.group() == channel["id"]:
                line = line.replace(string_match, f">{channel["name"]}")
                break
    return line


def clean_type(embed_type):
    r"""
    Clean embed type string from excessive information
    eg. `image\png` ---> `image`
    """
    return re.sub(match_after_slash, "", embed_type)


def generate_chat(messages, roles, channels, format_message, format_newline, format_reply, format_reactions, format_one_reaction, format_timestamp, edited_string, reactions_separator, max_length, my_id, my_roles, colors, blocked, limit_username=15, limit_global_name=15, use_nick=True, convert_timezone=True, blocked_mode=1, keep_deleted=False):
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
    chat = []
    chat_format = []
    indexes = []
    for message in messages:
        temp_chat = []   # stores only one multiline message
        temp_format = []

        # select base color
        default_color_format = colors[0]
        mention_color_format = colors[1]
        blocked_color_format = colors[2]
        deleted_color_format = colors[3]
        base_color_format = default_color_format
        for mention in message["mentions"]:
            if mention["id"] == my_id:
                base_color_format = mention_color_format
                break
        for role in message["mention_roles"]:
            if bool([i for i in my_roles if i in message["mention_roles"]]):
                base_color_format = mention_color_format
                break

        # skip deleted
        if "deleted" in message:
            if keep_deleted:
                base_color_format = deleted_color_format
            else:
                continue

        reply_color_format = base_color_format

        # handle blocked messages
        if blocked_mode and message["user_id"] in blocked:
            if blocked_mode == 1:
                message["username"] = "blocked"
                message["global_name"] = "blocked"
                message["nick"] = "blocked"
                message["content"] = "Blocked message"
                base_color_format = blocked_color_format
            else:
                indexes.append(0)
                continue   # could break message to chat conversion

        # replied message line
        if message["referenced_message"]:
            if message["referenced_message"]["id"]:
                if blocked_mode and message["referenced_message"]["user_id"] in blocked:
                    message["referenced_message"]["username"] = "blocked"
                    message["referenced_message"]["global_name"] = "blocked"
                    message["referenced_message"]["nick"] = "blocked"
                    message["referenced_message"]["content"] = "Blocked message"
                    reply_color_format = blocked_color_format
                if use_nick and message["referenced_message"]["nick"]:
                    global_name_nick = message["referenced_message"]["nick"]
                elif message["referenced_message"]["global_name"]:
                    global_name_nick = message["referenced_message"]["global_name"]
                else:
                    global_name_nick = message["referenced_message"]["username"]
                reply_embeds = message["referenced_message"]["embeds"].copy()
                content = ""
                if message["referenced_message"]["content"]:
                    content = replace_channels(replace_roles(replace_mention(clean_emojis(message["referenced_message"]["content"]), message["referenced_message"]["mentions"]), roles), channels)
                if reply_embeds:
                    for embed in reply_embeds:
                        if embed["url"] not in content:
                            content = content + f"\n[{clean_type(embed["type"])} embed]: {embed["url"]}"
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
            temp_format.append([reply_color_format])

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
                    content = content + f"\n[{clean_type(embed["type"])} embed]: {embed["url"]}"
        message_line = (
            format_message
            .replace("%username", normalize_string(message["username"], limit_username))
            .replace("%global_name", normalize_string(str(global_name_nick), limit_global_name))
            .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
            .replace("%edited", edited_string if message["edited"] else "")
            .replace("%content", content)
        )

        # limit message_line and split to multiline
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
        temp_format.append([base_color_format])

        # newline
        while next_line:
            new_line = (
                format_newline
                .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
                .replace("%content", next_line)
            )
            if len(new_line) > max_length:
                newline_index = len(new_line[:max_length].rsplit(" ", 1)[0])
                if newline_index <= len(
                    format_newline
                    .replace("%timestamp", generate_timestamp(message["timestamp"], format_timestamp, convert_timezone))
                    .replace("%content", ""),
                    ):
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
            temp_chat.append(new_line)
            temp_format.append([base_color_format])

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
            temp_format.append([base_color_format])
        indexes.append(len(temp_chat))

        # invert message lines order and append them to chat
        # it is inverted because chat is drawn from down to upside
        chat.extend(temp_chat[::-1])
        chat_format.extend(temp_format[::-1])
    return chat, chat_format, indexes


def generate_status_line(my_user_data, my_status, unseen, typing, active_channel, action, task, format_status_line, format_rich, limit_typing=30, use_nick=True):
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

    # who is typing
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
    elif action["type"] == 6:   # cancel all downloads
        action_string = "Really cancel all downloads? [Y/n]"

    if my_status["custom_status_emoji"]:
        custom_status_emoji = str(my_status["custom_status_emoji"]["name"])
    else:
        custom_status_emoji = ""
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


def generate_tree(dms, guilds, dms_settings, guilds_settings, unseen, mentioned, guild_positions, collapsed, active_channel_id, dd_vline, dd_hline, dd_corner):
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
    intersection = f"{dd_vline}{dd_hline*2}"   # default: "|--"
    pass_by = f"{dd_vline}  "   # default: "|  "
    intersection_end = f"{dd_corner}{dd_hline*2}"   # default: "\\--"
    pass_by_end = f"{pass_by}{intersection_end}"   # default: "|  \\--"
    tree = []
    tree_format = []
    tree_metadata = []
    tree.append("> Direct Messages")
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

    #sort guilds:
    guilds_sorted = []
    for guild_sorted_id in guild_positions:
        for num, guild in enumerate(guilds):
            if guild["guild_id"] == guild_sorted_id:
                guilds_sorted.append(guilds[num])
                break

    for guild in guilds_sorted:
        # prepare data
        muted_guild = False
        unseen_guild = False
        ping_guild = False
        active_guild = False

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
                        if not hidden_ch:
                            category["hidden"] = False
                        active = (channel["id"] == active_channel_id)
                        if active:
                            # unwrap top level gild
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
        tree.append(f"> {guild["name"]}")
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
                    tree.append(f"{intersection}> {category["name"]}")
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
            if tree[num - 1][:4] != f"{intersection}>":
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
