import datetime

PLATFORM_TYPES = ("Desktop", "Xbox", "Playstation", "IOS", "Android", "Nitendo", "Linux", "MacOS")
CONTENT_TYPES = ("Played Game", "Watched Media", "Top Game", "Listened Media", "Listened Session", "Top Artist", "Custom Status", "Launched Activity", "Leaderboard")

def get_newlined_value(embed, name):
    """Get value from embed and add newline to it"""
    value = embed.get(name)
    if value:
        return value + "/n"
    return ""


def generate_discord_timestamp(timestamp, timestamp_format):
    """Convert timestamp string to discord timestamp notation"""
    try:
        time_obj = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        time_obj = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")   # edge case
    return f"<t:{time_obj.timestamp()}:{timestamp_format}>"


def prepare_embeds(embeds, message_content):
    """Perepare message embeds"""
    ready_embeds = []
    for embed in embeds:
        content = ""
        content += get_newlined_value(embed, "url")
        content += get_newlined_value(embed, "title")
        content += get_newlined_value(embed, "description")
        if "fields" in embed:
            for field in embed["fields"]:
                content += "\n" + field["name"] + "\n" + field["value"]  + "\n"
        if "video" in embed and "url" in embed["video"]:
            content += embed["video"]["url"] + "\n"
        if "image" in embed and "url" in embed["image"]:
            content += embed["image"]["url"] + "\n"
        if "title" in embed:
            content += embed["title"] + "\n"
        if "footer" in embed:
            content += get_newlined_value(embed["footer"], "text")
        content = content.strip("\n")
        if content and content not in message_content:
            ready_embeds.append({
                "type": embed["type"],
                "name": None,
                "url": content,
            })
    return ready_embeds


def prepare_message(message):
    """Prepare message dict"""
    # replied message
    if "referenced_message" in message:
        if message["referenced_message"]:
            reference_nick = None
            for mention in message["mentions"]:
                if mention["id"] == message["referenced_message"]["id"]:
                    if "member" in mention:
                        reference_nick = mention["member"]["nick"]
            ref_mentions = []
            if message["referenced_message"]["mentions"]:
                for ref_mention in message["referenced_message"]["mentions"]:
                    ref_mentions.append({
                        "username": ref_mention["username"],
                        "id": ref_mention["id"],
                    })
            if "message_snapshots" in message["referenced_message"]:
                forwarded = message["referenced_message"]["message_snapshots"][0]["message"]
                # additional text with forwarded message is sent separately
                message["referenced_message"]["content"] = f"[Forwarded]: {forwarded.get("content")}"
                message["referenced_message"]["embeds"] = forwarded.get("embeds")
                message["referenced_message"]["attachments"] = forwarded.get("attachments")
            reference_embeds = prepare_embeds(message["referenced_message"]["embeds"], "")
            for attachment in message["referenced_message"]["attachments"]:
                reference_embeds.append({
                    "type": attachment.get("content_type", "unknown"),
                    "name": attachment["filename"],
                    "url": attachment["url"],
                })   # keep attachments in same place as embeds
            reference = {
                "id": message["referenced_message"]["id"],
                "timestamp": message["referenced_message"]["timestamp"],
                "content": message["referenced_message"]["content"],
                "mentions": ref_mentions,
                "user_id": message["referenced_message"]["author"]["id"],
                "username": message["referenced_message"]["author"]["username"],
                "global_name": message["referenced_message"]["author"]["global_name"],
                "nick": reference_nick,
                "embeds": reference_embeds,
                "stickers": message["referenced_message"].get("sticker_items", []),
            }
        else:   # reference message is deleted
            reference = {
                "id": None,
                "content": "Deleted message",
            }
    else:
        reference = None
    # reactions
    if "reactions" in message:
        reactions = []
        for reaction in message["reactions"]:
            reactions.append({
                "emoji": reaction["emoji"]["name"],
                "emoji_id": reaction["emoji"]["id"],
                "count": reaction["count"],
                "me": reaction["me"],
            })
    else:
        reactions = []
    nick = None
    if "member" in message:
        nick = message["member"]["nick"]
    # forwarded messgaes
    if "message_snapshots" in message:
        forwarded = message["message_snapshots"][0]["message"]
        # additional text with forwarded message is sent separately
        message["content"] = f"[Forwarded]: {forwarded.get("content")}"
        message["embeds"] = forwarded.get("embeds")
        message["attachments"] = forwarded.get("attachments")
    # embeds and attachments
    embeds = prepare_embeds(message["embeds"], message["content"])
    for attachment in message["attachments"]:
        embeds.append({
            "type": attachment.get("content_type", "unknown"),
            "name": attachment["filename"],
            "url": attachment["url"],
        })   # keep attachments in same place as embeds
    # mentions
    mentions = []
    if message["mentions"]:
        for mention in message["mentions"]:
            mentions.append({
                "username": mention["username"],
                "id": mention["id"],
            })
    # interactions
    if "interaction" in message:
        interaction = {
            "username": message["interaction"]["user"]["username"],
            "command": message["interaction"]["name"],
        }
    else:
        interaction = None
    # components
    if "components" in message:
        new_content, new_embeds = prepare_components(message["components"])
        new_content_str = ""
        for line in new_content:
            new_content_str += f"> {line}\n"
        message["content"] += new_content_str
        embeds.extend(new_embeds)
    # special message types
    message["content"] = prepare_special_message_types(message)
    return {
        "id": message["id"],
        "channel_id": message["channel_id"],
        "guild_id": message.get("guild_id"),
        "timestamp": message["timestamp"],
        "edited": False,
        "content": message["content"],
        "mentions": mentions,
        "mention_roles": message["mention_roles"],
        "mention_everyone": message["mention_everyone"],
        "user_id": message["author"]["id"],
        "username": message["author"]["username"],
        "global_name": message["author"]["global_name"],
        "nick": nick,
        "referenced_message": reference,
        "reactions": reactions,
        "embeds": embeds,
        "stickers": message.get("sticker_items", []),   # {name, id, format_type}
        "interaction": interaction,
    }


def prepare_messages(data, have_channel_id=False):
    """Prepare list of messages"""
    messages = []
    for message in data:
        messages.append(prepare_message(message))
        if have_channel_id:
            messages[-1]["channel_id"] = message["channel_id"]
    return messages


def prepare_components(components):
    """Convert mesage components into message, urls and embeds, recursive"""
    text = []
    embeds = []
    for component in components:
        comp_type = component["type"]
        if comp_type == 1:   # ACTION_ROW
            new_text, new_embeds = prepare_components(component.get("components"))
            text.extend(" | ".join(new_text))
            embeds.extend(new_embeds)
        elif comp_type == 2:   # BUTTON
            if component.get("style", "") == 5:   # LINK
                text.append(f"Button: {component["url"]}")
            else:
                text.append("*unknown_butotn*")
        elif comp_type == 3:   # STRING_SELECT
            text.append("*Unimplemented component: string_select*")
        elif comp_type == 4:   # TEXT_INPUT
            text.append("*Unimplemented component: text_input*")
        elif comp_type == 5:   # USER_SELECT
            text.append("*Unimplemented component: user_select*")
        elif comp_type == 6:   # ROLE_SELECT
            text.append("*Unimplemented component: role_select*")
        elif comp_type == 7:   # MENTIONABLE_SELECT
            text.append("*Unimplemented component: mentionable_select*")
        elif comp_type == 8:   # CHANNEL_SELECT
            text.append("*Unimplemented component: channel_select*")
        # 9 - SECTION - same as CONTAINER
        elif comp_type == 10:   # TEXT_DISPLAY
            text.append(component["content"])
        # 11 - THUMBNAIL - unused
        elif comp_type == 12:   # MEDIA_GALLERY
            for item in component["items"]:
                media = item["media"]
                media_str = "File: "
                if media.get("type"):
                    media_str += f"[{media["type"]}]"
                media_str += f" {media["url"]}"
                text.append(media_str)
                if item.get("description"):
                    text.append(f"*{item["description"]}*")
                media["hidden"] = True
                embeds.append(media)
        elif comp_type == 13:   # FILE
            file = component["file"]
            file_type = file.get("type")
            file_str = "File: "
            if file_type:
                file_str += f"[{file_type}]"
            file_str += f" {file["url"]}"
            text.append(file_str)
            file["hidden"] = True
            embeds.append(file)
        elif comp_type == 14:   # SEPARATOR
            text.append("------------")
        # 15 - ???
        elif comp_type == 16:   # CONTENT_INVENTORY_ENTRY
            content_inventory_entry = component["content_inventory_entry"]
            content_type = content_inventory_entry["content_type"]
            # there is some info in "traits"
            metadata = content_inventory_entry["extra"]
            started_at = content_inventory_entry.get("started_at")
            expires_at = content_inventory_entry.get("expires_at")
            ended_at = content_inventory_entry.get("ended_at")
            # title
            text.append(CONTENT_TYPES[content_type-1])
            # body
            game_string = ""
            if metadata.get("game_name"):
                game_string += f"Game: {metadata["game_name"]}"
                if metadata.get("platform"):
                    game_string += f"({PLATFORM_TYPES[metadata["platform"]]})"
                text.append(game_string)
            listened_media_string = ""
            if metadata.get("media_type") == 1 and metadata.get("title"):
                artist = metadata.get("artist", "Unknown Artist")
                album = metadata.get("parent_title", "Unknown Album")
                listened_media_string += f"{artist} - {album} - {metadata["title"]}"
                if metadata.get("media_provider") == 1:
                    listened_media_string += "(Spotify)"
            if metadata.get("artist"):
                text.append(f"Artist: {metadata["artist"]["name"]}")
            watched_media_string = ""
            if metadata.get("media_title"):
                watched_media_string += metadata["media_title"]
            if metadata.get("media_subtitle"):
                watched_media_string += f"({metadata["media_subtitle"]})"
            if metadata.get("media_assets_large_text"):
                watched_media_string += f" - {metadata["media_assets_large_text"]}"
            if metadata.get("media_assets_small_text"):
                watched_media_string += f" - {metadata["media_assets_small_text"]}"
            if watched_media_string:
                text.append(watched_media_string)
            if metadata.get("url"):
                text.append(f"Url: {metadata["url"]}")
            if metadata.get("activity_name"):
                text.append(f"Activity: {metadata["activity_name"]}")
            # times
            times_string = ""
            if started_at:
                times_string += f"Started: {generate_discord_timestamp(started_at, "R")}"
            if expires_at:
                times_string += f"Expires: {generate_discord_timestamp(expires_at, "R")}"
            if ended_at:
                times_string += f"Ended: {generate_discord_timestamp(ended_at, "R")}"
            if times_string:
                text.append(times_string)
        elif comp_type in (17, 9):   # CONTAINER and SECTION
            new_text, new_embeds = prepare_components(component.get("components"))
            text.extend(["  " + x for x in new_text])
            embeds.extend(new_embeds)
    return text, embeds


def prepare_special_message_types(message):
    """Generate message contents for all message types"""
    if message["type"] == 7:
        return "> *Joined the server.*"
    return message["content"]
