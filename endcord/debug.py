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
            anonymized_channels.append({
                "id": hash_none(channel["id"]),
                "type": channel["type"],
                "name": name,
                "topic": "",
                "parent_id": parent_id,
                "position": channel["position"],
            })
        anonymized.append({
            "guild_id": hash_none(guild["guild_id"]),
            "owned": guild["owned"],
            "name": f"guild_{num}",
            "description": "",
            "channels": anonymized_channels,
        })
    return anonymized


def anonymize_guilds_settings(guilds_settings):
    """
    Anonymize all sensitive data in guilds_settings.
    hash: guild_id, id
    """
    anonymized = []
    for num, guild in enumerate(guilds_settings):
        anonymized_channels = []
        for num_ch, channel in enumerate(guild["channels"]):
            anonymized_channels.append({
                "id": hash_none(channel["id"]),
                "message_notifications": channel["message_notifications"],
                "muted": channel["muted"],
                "hidden": channel["hidden"],
                "collapsed": channel["collapsed"],
            })
        anonymized.append({
            "guild_id": hash_none(guild["guild_id"]),
            "suppress_everyone": guild["suppress_everyone"],
            "suppress_roles": guild["suppress_roles"],
            "message_notifications": guild["message_notifications"],
            "muted": guild["muted"],
            "channels": anonymized_channels,
        })
    return anonymized


def anonymize_guild_positions(guild_positions):
    """
    Anonymize all sensitive data in guild_positions.
    hash: guild_id
    """
    anonymized = []
    for guild in guild_positions:
        anonymized.append(hash_none(guild))
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
    perms_allowed = []
    for i in list(range(47)) + [49, 50]:
        flag = (1 << i)
        perm = ((permissions & flag) == flag)
        if perm:
            perms_allowed.append(permission_names[i])
    return perms_allowed
