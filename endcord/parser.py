import logging
import re
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
DISCORD_EPOCH_MS = 1420070400000
STATUS_STRINGS = ("online", "idle", "dnd", "invisible")
TIME_FORMATS = ("%Y-%m-%d", "%Y-%m-%d-%H-%M", "%H:%M:%S", "%H:%M")
NOTIFICATION_VALUES = (
    "all",
    "mention",
    "nothing",
    "suppress_everyone",
    "suppress_roles",
)

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

match_command_arguments = re.compile(r"--(\S+)=(\w+|\"[^\"]+\")?")

match_string_select = re.compile(r"string_select(?: (\d+))?\s+(.+)")


def date_to_snowflake(date, end=False):
    """Convert date to discord snowflake, rounded to day start, if end=True then is rounded to day end"""
    try:
        time_obj = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        time_obj = datetime.now()
        time_obj = time_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    # timestamp cant be larger than now
    if int(time_obj.timestamp()) > time.time():
        time_obj = datetime.now()
        time_obj = time_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        time_obj = time_obj.replace(tzinfo=timezone.utc)
    if end:
        time_obj += timedelta(days=1)
    return (int(time_obj.timestamp()) * 1000 - DISCORD_EPOCH_MS) << 22


def date_to_timestamp(date):
    """Convert date to discord snowflake, rounded to day start, if end=True then is rounded to day end"""
    time_obj = None
    # try various time formats
    for time_format in TIME_FORMATS:
        try:
            time_obj = datetime.strptime(date, time_format)
        except ValueError:
            continue

    if not time_obj:
        time_obj = datetime.now()
        time_obj = time_obj.replace(hour=0, minute=0, second=0, microsecond=0)

    # set current date if its unset
    if time_obj.year == 1900:
        now = datetime.now()
        time_obj = time_obj.replace(year=now.year, month=now.month, day=now.day)

    return int(time_obj.timestamp())


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


def check_start_command(text, my_commands, guild_commands, permitted_guild_commands):
    """Check if string is valid start of command"""
    app_name = text.split(" ")[0][1:].lower()
    if not app_name:
        return False
    for command in my_commands:
        if command["app_name"].lower().replace(" ", "_") == app_name:
            return True
    for num, command in enumerate(guild_commands):
        if (
            permitted_guild_commands[num]
            and command["app_name"].lower().replace(" ", "_") == app_name
        ):
            return True
    return False


def verify_option_type(option_value, option_type, roles, channels):
    """Check if option value is of corect type"""
    if option_type in (1, 2):  # SUB_COMMAND and SUB_COMMAND_GROUP
        if not option_value:
            return False  # skip subcommands
    if option_type == 3:  # STRING
        return not (
            bool(re.search(match_profile, option_value))
            or bool(re.search(match_channel, option_value))
        )
    if option_type == 4:  # INTEGER
        try:
            int(option_value)
            return True
        except ValueError:
            pass
    elif option_type == 5:  # BOOLEAN
        try:
            bool(option_value)
            return True
        except ValueError:
            pass
    elif option_type == 6:  # USER
        return bool(re.search(match_profile, option_value))
    elif option_type == 7:  # CHANNEL
        match = re.search(match_channel, option_value)
        if match:
            channel_id = match.group(1)
            for channel in channels:
                if channel["id"] == channel_id:
                    return True
    elif option_type == 8:  # ROLE
        match = re.search(match_profile, option_value)
        if match:
            role_id = match.group(1)
            for role in roles:
                if role["id"] == role_id:
                    return True
    elif option_type == 9:  # MENTIONABLE
        return bool(re.search(match_profile, option_value))
    elif option_type == 10:  # NUMBER
        try:
            float(option_value)
            return True
        except ValueError:
            pass
    elif option_type == 11:  # ATTACHMENT
        if option_value == 0:
            return True
    return False


def app_command_string(
    text,
    my_commands,
    guild_commands,
    permitted_guild_commands,
    roles,
    channels,
    dm,
    autocomplete,
):
    """Parse app command string and prepare data payload"""
    app_name = text.split(" ")[0][1:].lower()
    if not app_name:
        return None, None, None

    #  verify command
    command_name = text.split(" ")[1]
    if command_name.startswith("--"):
        return None, None, None
    for num, command in enumerate(guild_commands):
        if (
            permitted_guild_commands[num]
            and command["name"] == command_name
            and command["app_name"].lower().replace(" ", "_") == app_name
        ):
            app_id = command["app_id"]
            break
    else:
        for command in my_commands:
            if (
                command["name"] == command_name
                and command["app_name"].lower().replace(" ", "_") == app_name
            ):
                if dm and not command.get("dm"):
                    return None, None, None  # command not allowed in dm
                app_id = command["app_id"]
                break
        else:
            return None, None, None

    # get subcommands
    try:
        subcommand_group_name = text.split(" ")[2]
        if subcommand_group_name.startswith("--"):
            subcommand_group_name = None
    except IndexError:
        subcommand_group_name = None
    if subcommand_group_name:
        try:
            subcommand_name = text.split(" ")[3]
            if subcommand_name.startswith("--"):
                subcommand_name = None
        except IndexError:
            subcommand_name = None
    else:
        subcommand_name = None

    command_options = []
    for match in re.finditer(match_command_arguments, text):
        if len(match.groups()) == 2:
            value = match.group(2)
        else:
            value = 0
        command_options.append((match.group(1), value))  # (name, value)
    context_options = command.get("options", [])

    # verify subcommands and groups
    subcommand = None
    subcommand_group = None
    if subcommand_group_name:
        for subcmd in context_options:
            if (
                subcmd["type"] == 1 and subcmd["name"] == subcommand_group_name
            ):  # subcommand
                subcommand = subcmd
                context_options = subcmd.get("options", [])
                break
            elif (
                subcmd["type"] == 2 and subcmd["name"] == subcommand_group_name
            ):  # group
                subcommand_group = subcmd
                break
    if subcommand_group and subcommand_name:  # subcommand after group
        for subcmd in subcommand_group.get("options", []):
            if subcmd["type"] == 1 and subcmd["name"] == subcommand_name:
                subcommand = subcmd
                context_options = subcmd.get("options", [])
                break

    # add and verify options
    need_attachment = False
    options = []
    required = True
    for num, (option_name, option_value) in enumerate(command_options):
        for option in context_options:
            if option["name"] == option_name:
                break
        option_value_clean = option_value
        if option["type"] == 11:
            need_attachment = True
            option_value_clean = 0
        if not autocomplete and not (
            option_value_clean
            and verify_option_type(option_value_clean, option["type"], roles, channels)
        ):
            return None, None, None
        option_dict = {
            "type": option["type"],
            "name": option["name"],
            "value": option_value_clean,
        }
        if autocomplete and num == len(command_options) - 1:  # if its last option
            option_dict["focused"] = True  # what "focused" means ?
        options.append(option_dict)

    # check for required
    for option in context_options:
        if option.get("required"):
            for option_name, _ in command_options:
                if option["name"] == option_name:
                    break
            else:
                return None, None, None  # missing required option

    # dont allow command with options but none is set
    if not options and not subcommand_group_name and context_options and required:
        return None, None, None

    # add subcommands and groups
    if subcommand:
        options = [
            {
                "type": subcommand["type"],
                "name": subcommand["name"],
                "options": options,
            }
        ]
        if not options[0]["options"]:
            options[0].pop("options")
    if subcommand_group:
        options = [
            {
                "type": subcommand_group["type"],
                "name": subcommand_group["name"],
                "options": options,
            }
        ]
        if not options[0]["options"]:
            options[0].pop("options")
            return None, None, None  # cant have group without subcommand

    command_data = {
        "version": command["version"],
        "id": command["id"],
        "name": command["name"],
        "type": 1,  # only slash commands
        "options": options,
        "attachments": [],
    }
    return command_data, app_id, need_attachment


def command_string(text):
    """Parse command string"""

    # 0 - UNKNOWN
    cmd_type = 0
    cmd_args = {}

    # 1 - SET
    if text.lower().startswith("set "):
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

    # 28 - PASTE_CLIPBOARD_IMAGE
    elif text.lower().startswith("paste_clipboard_image"):
        cmd_type = 28

    # 29 - TOGGLE_MUTE
    elif text.lower().startswith("toggle_mute"):
        cmd_type = 29
        match = re.search(match_channel, text)
        if match:
            cmd_args = {"channel_id": match.group(1)}

    # 30 - TOGGLE_TAB
    elif text.lower().startswith("toggle_tab"):
        cmd_type = 30

    # 31 - SWITCH_TAB
    elif text.lower().startswith("switch_tab"):
        cmd_type = 31
        try:
            num = int(text.split(" ")[1])
            cmd_args = {"num": num}
        except (IndexError, ValueError):
            cmd_type = 0

    # 32 - MARK_AS_READ
    elif text.lower().startswith("mark_as_read"):
        cmd_type = 32
        match = re.search(match_channel, text)
        if match:
            cmd_args = {"channel_id": match.group(1)}

    # 33 - INSERT_TIMESTAMP
    elif text.lower().startswith("insert_timestamp"):
        cmd_type = 33
        try:
            date_string = text.split(" ")[1]
            timestamp = date_to_timestamp(date_string)
            cmd_args = {"timestamp": timestamp}
        except (IndexError, ValueError):
            cmd_type = 0

    # 34 - VOTE
    elif text.lower().startswith("vote"):
        cmd_type = 34
        try:
            num = int(text.split(" ")[1])
            cmd_args = {"num": num}
        except (IndexError, ValueError):
            cmd_type = 0

    # 35 - SHOW_PINNED
    elif text.lower().startswith("show_pinned"):
        cmd_type = 35

    # 36 - PIN_MESSAGE
    elif text.lower().startswith("pin_message"):
        cmd_type = 36

    # 37 - PUSH_BUTTON
    elif text.lower().startswith("push_button"):
        cmd_type = 37
        try:
            num = int(text.split(" ")[1])
            cmd_args = {"num": num}
        except ValueError:
            name = text.split(" ")[1]
            cmd_args = {"name": name}
        except IndexError:
            cmd_type = 0

    # 38 - STRING_SELECT
    elif text.lower().startswith("string_select"):
        cmd_type = 38
        match = re.search(match_string_select, text.lower())
        if match:
            num = match.group(1)
            string = match.group(2)
            cmd_args = {"num": num, "text": string}
        else:
            cmd_type = 0

    # 39 - DUMP_CHAT
    elif text.lower().startswith("dump_chat"):
        cmd_type = 39

    # 40 - SET_NOTIFICATIONS
    elif text.lower().startswith("set_notifications"):
        cmd_type = 40
        cmd_split = text.split(" ")
        have_id = False
        cmd_args = {"id": None, "setting": ""}
        if len(cmd_split) > 1:
            match = re.search(match_channel, cmd_split[1])
            if match:
                cmd_args["channel_id"] = match.group(1)
                have_id = True
        if len(cmd_split) > 1 + have_id:
            if cmd_split[1 + have_id].lower() in NOTIFICATION_VALUES:
                cmd_args["setting"] = cmd_split[1 + have_id].lower()
            else:
                cmd_type = 0

    # 41 - GIF
    elif text.lower().startswith("gif"):
        cmd_type = 41
        search_text = text[4:].strip(" ")
        cmd_args = {"search_text": search_text}

    # 42 - REDRAW
    elif text.lower().startswith("redraw"):
        cmd_type = 42

    return cmd_type, cmd_args
