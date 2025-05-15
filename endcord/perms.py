def decode_flag(flags, flag_num):
    """Return value for specified flag number (int)"""
    flag = (1 << flag_num)
    return (flags & flag) == flag

def decode_permission(permission, flag):
    """
    Return value for specified permission flag (binary shifted)
    Some useful flags:
    ADMINISTRATOR   0x8
    ADD_REACTIONS   0x40
    VIEW_CHANNEL    0x400
    SEND_MESSAGES   0x800
    EMBED_LINKS     0x4000
    ATTACH_FILES    0x8000
    MENTION_EVERYONE    0x20000
    USE_EXTERNAL_EMOJIS 0x40000
    """
    return (permission & flag) == flag


def compute_permissions(guilds, this_guild_roles, this_guild_id, my_roles, my_id):
    """Read channel permissions and add permitted and allowed_embeds to each channel"""
    # select guild
    guild = {}
    for guild in guilds:
        if guild["guild_id"] == this_guild_id:
            break
    if not guild:
        return guilds

    # check if this guild is owned by this user
    if guild["owned"]:
        for num, channel in enumerate(guild["channels"]):
            guild["channels"][num]["permitted"] = True
            guild["channels"][num]["allow_attach"] = True
            guild["channels"][num]["allow_write"] = True
            guild["channels"][num].pop("permission_overwrites", None)
        return guilds

    # base permissions
    base_permissions = int(guild["base_permissions"])
    for role in this_guild_roles:
        if role["id"] in my_roles:
            base_permissions |= int(role["permissions"])

    for num, channel in enumerate(guild["channels"]):

        # check if channel is already parsed
        if "permitted" in channel:
            continue

        permission_overwrites = guild["channels"][num].pop("permission_overwrites", [])

        # @everyone role overwrite
        permissions = base_permissions
        for overwrite in permission_overwrites:
            if overwrite["id"] == this_guild_id:
                permissions &= ~int(overwrite["deny"])
                permissions |= int(overwrite["allow"])
                break
        allow = 0
        deny = 0

        # role overwrites
        for overwrite in permission_overwrites:
            if overwrite["type"] == 0 and overwrite["id"] in my_roles:
                allow |= int(overwrite["allow"])
                deny |= int(overwrite["deny"])
        permissions &= ~deny
        permissions |= allow

        # member overwrites
        for overwrite in permission_overwrites:
            if overwrite["type"] == 1 and overwrite["id"] == my_id:
                permissions &= ~int(overwrite["deny"])
                permissions |= int(overwrite["allow"])

        # read and store selected permissions
        guild["channels"][num]["permitted"] = (
            decode_permission(permissions, 0x400)    # VIEW_CHANNEL
            or decode_permission(permissions, 0x8)   # ADMINISTRATOR
        )
        guild["channels"][num]["allow_write"] = (
            decode_permission(permissions, 0x800)    # SEND_MESSAGES
            or decode_permission(permissions, 0x8)   # ADMINISTRATOR
        )
        guild["channels"][num]["allow_attach"] = (
            decode_permission(permissions, 0x8000)   # ATTACH_FILES
            or decode_permission(permissions, 0x8)   # ADMINISTRATOR
        )
    return guilds
