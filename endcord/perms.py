def decode_permission(permission, flag):
    """
    Return value for specified permission flag
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
    # check if guild is already parsed
    if "permitted" in guild["channels"][0]:
        return guilds

    # check if this guild owned by this user
    if guild["owned"]:
        for num, channel in enumerate(guild["channels"]):
            guild["channels"][num]["permitted"] = True
            guild["channels"][num]["allow_attach"] = True

    # base permissions
    base_permissions = int(guild["base_permissions"])
    for role in this_guild_roles:
        if role["id"] in my_roles:
            base_permissions |= int(role["permissions"])

    for num, channel in enumerate(guild["channels"]):
        permissions = base_permissions
        # @everyone role overwrite
        for overwrite in channel.get("permission_overwrites", []):
            if overwrite["id"] == this_guild_id:
                permissions &= ~int(overwrite["deny"])
                permissions |= int(overwrite["allow"])
                break
        allow = 0
        deny = 0

        # role overwrites
        for overwrite in channel.get("permission_overwrites", []):
            if overwrite["type"] == 0 and overwrite["id"] in my_roles:
                allow |= int(overwrite["allow"])
                deny |= int(overwrite["deny"])
        permissions &= ~deny
        permissions |= allow

        # member overwrites
        for overwrite in channel.pop("permission_overwrites", []):
            if overwrite["type"] == 1 and overwrite["id"] == my_id:
                permissions &= ~int(overwrite["deny"])
                permissions |= int(overwrite["allow"])

        # read and store selected permissions
        guild["channels"][num]["permitted"] = (
            decode_permission(permissions, 0x400)    # VIEW_CHANNEL
            or decode_permission(permissions, 0x8)   # ADMINISTRATOR
        )
        guild["channels"][num]["allow_attach"] = (
            decode_permission(permissions, 0x8000)   # ATTACH_FILES
            or decode_permission(permissions, 0x8)   # ADMINISTRATOR
        )
    return guilds
