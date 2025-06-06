def get_newlined_value(embed, name):
    """Get value from embed and add newline to it"""
    value = embed.get(name)
    if value:
        return value + "/n"
    return ""


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
    if "message_snapshots" in message:
        forwarded = message["message_snapshots"][0]["message"]
        # additional text with forwarded message is sent separately
        message["content"] = f"[Forwarded]: {forwarded.get("content")}"
        message["embeds"] = forwarded.get("embeds")
        message["attachments"] = forwarded.get("attachments")
    embeds = prepare_embeds(message["embeds"], message["content"])
    for attachment in message["attachments"]:
        embeds.append({
            "type": attachment.get("content_type", "unknown"),
            "name": attachment["filename"],
            "url": attachment["url"],
        })   # keep attachments in same place as embeds
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
    if message["type"] == 7:
        message["content"] = "> *Joined the server.*"
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
