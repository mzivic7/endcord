import json
import os

from endcord import peripherals


def hash_none(value):
    """Hash an integer value as a string and return it as a string, omitting None"""
    if value is None:
        return None
    return str(hash(str(value)))


def save_json(json_data, name, debug_path=True):
    """Save json to log path"""
    if debug_path:
        path = os.path.expanduser(os.path.join(peripherals.log_path, "Debug", name))
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
    else:
        path = name
    with open(path, "w") as f:
        json.dump(json_data, f, indent=2)


def load_json(path):
    """Load json from any path"""
    with open(path, "r") as f:
        return json.load(f)
    return None


def anonymize_guilds(guilds):
    """
    Anonymize all sensitive data in guilds.
    hash: guild_id, id
    replace text: name
    remove: description, topic
    """
    anonymized = []
    for num, guild in enumerate(guilds):
        anonymized_channels = []
        for num_ch, channel in enumerate(guild["channels"]):
            if channel["type"] == 4:
                name = f"category_{num_ch}"
            else:
                name = f"channel_{num_ch}"
            if channel["parent_id"]:
                parent_id = hash_none(channel["parent_id"])
            else:
                parent_id = "NO DATA"
            anonymized_channels.append({
                "id": hash_none(channel["id"]),
                "type": channel["type"],
                "name": name,
                "topic": "",
                "parent_id": parent_id,
                "position": channel["position"],
                "message_notifications": channel.get("message_notifications", "NO DATA"),
                "muted": channel.get("muted", "NO DATA"),
                "hidden": channel.get("hidden", "NO DATA"),
                "collapsed": channel.get("collapsed", "NO DATA"),
            })
        anonymized.append({
            "guild_id": hash_none(guild["guild_id"]),
            "owned": guild["owned"],
            "name": f"guild_{num}",
            "description": "",
            "suppress_everyone": guild.get("suppress_everyone", "NO DATA"),
            "suppress_roles": guild.get("suppress_roles", "NO DATA"),
            "message_notifications": guild.get("message_notifications", "NO DATA"),
            "muted": guild.get("muted", "NO DATA"),
            "channels": anonymized_channels,
        })
    return anonymized


def anonymize_guild_folders(guild_folders):
    """
    Anonymize all sensitive data in guild_folders.
    hash: guild_id
    """
    anonymized = []
    for folder in guild_folders:
        guilds = []
        for guild in folder["guilds"]:
            guilds.append(hash_none(guild))
        anonymized.append({
            "id": folder["id"],
            "guilds": guilds,
        })
    return anonymized


permission_names = [
    "CREATE_INSTANT_INVITE",
    "KICK_MEMBERS",
    "BAN_MEMBERS",
    "ADMINISTRATOR",
    "MANAGE_CHANNELS",
    "MANAGE_GUILD",
    "ADD_REACTIONS",
    "VIEW_AUDIT_LOG",
    "PRIORITY_SPEAKER",
    "STREAM",
    "VIEW_CHANNEL",
    "SEND_MESSAGES",
    "SEND_TTS_MESSAGES",
    "MANAGE_MESSAGES",
    "EMBED_LINKS",
    "ATTACH_FILES",
    "READ_MESSAGE_HISTORY",
    "MENTION_EVERYONE",
    "USE_EXTERNAL_EMOJIS",
    "VIEW_GUILD_INSIGHTS",
    "CONNECT",
    "SPEAK",
    "MUTE_MEMBERS",
    "DEAFEN_MEMBERS",
    "MOVE_MEMBERS",
    "USE_VAD",
    "CHANGE_NICKNAME",
    "MANAGE_NICKNAMES",
    "MANAGE_ROLES",
    "MANAGE_WEBHOOKS",
    "MANAGE_GUILD_EXPRESSIONS",
    "USE_APPLICATION_COMMANDS",
    "REQUEST_TO_SPEAK",
    "MANAGE_EVENTS",
    "MANAGE_THREADS",
    "CREATE_PUBLIC_THREADS",
    "CREATE_PRIVATE_THREADS",
    "USE_EXTERNAL_STICKERS",
    "SEND_MESSAGES_IN_THREADS",
    "USE_EMBEDDED_ACTIVITIES",
    "MODERATE_MEMBERS",
    "VIEW_CREATOR_MONETIZATION_ANALYTICS",
    "USE_SOUNDBOARD",
    "CREATE_GUILD_EXPRESSIONS",
    "CREATE_EVENTS",
    "USE_EXTERNAL_SOUNDS",
    "SEND_VOICE_MESSAGES",
    "",
    "",
    "SEND_POLLS",
    "USE_EXTERNAL_APPS",
]

def get_perms_allowed_names(permissions):
    """Return list of allowed permission names"""
    permissions = int(permissions)
    perms_allowed = []
    for i in list(range(47)) + [49, 50]:
        flag = (1 << i)
        perm = ((permissions & flag) == flag)
        if perm:
            perms_allowed.append(permission_names[i])
    return perms_allowed


def decode_flags(flags):
    """Decode flags without known names"""
    decoded_allowed = []
    for i in range(50):
        flag = (1 << i)
        decoded = ((flags & flag) == flag)
        if decoded:
            decoded_allowed.append(str(i))
    return decoded_allowed
