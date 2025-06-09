from datetime import datetime

PLATFORM_TYPES = ("Desktop", "Xbox", "Playstation", "IOS", "Android", "Nitendo", "Linux", "MacOS")
CONTENT_TYPES = ("Played Game", "Watched Media", "Top Game", "Listened Media", "Listened Session", "Top Artist", "Custom Status", "Launched Activity", "Leaderboard")


def get_newlined_value(embed, name):
    """Get value from embed and add newline to it"""
    value = embed.get(name)
    if value:
        return value + "\n"
    return ""


def generate_timestamp(timestamp, timestamp_format, unix=False):
    """Convert timestamp string to discord timestamp notation"""
    try:
        time_obj = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        time_obj = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")   # edge case
    if unix:
        return int(time_obj.timestamp())
    return f"<t:{int(time_obj.timestamp())}:{timestamp_format}>"


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

    # special message types
    message = prepare_special_message_types(message)
    if "poll" in message:
        poll = prepare_poll(message["poll"])
    else:
        poll = None

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
        new_content_str = new_content_str.strip("\n")
        message["content"] += new_content_str
        embeds.extend(new_embeds)

    message_dict =  {
        "id": message["id"],
        "channel_id": message["channel_id"],
        "guild_id": message.get("guild_id"),
        "timestamp": message["timestamp"],
        "edited": bool(message["edited_timestamp"]),
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
    if poll:
        message_dict["poll"] = poll
    return message_dict


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
                times_string += f"Started: {generate_timestamp(started_at, "R")}"
            if expires_at:
                times_string += f"Expires: {generate_timestamp(expires_at, "R")}"
            if ended_at:
                times_string += f"Ended: {generate_timestamp(ended_at, "R")}"
            if times_string:
                text.append(times_string)
        elif comp_type in (17, 9):   # CONTAINER and SECTION
            new_text, new_embeds = prepare_components(component.get("components"))
            text.extend(["  " + x for x in new_text])
            embeds.extend(new_embeds)
    return text, embeds


def prepare_special_message_types(message):
    """Generate message contents for all message types"""
    msg_type = message["type"]
    if msg_type == 0:   # DEFAULT
        return message
    if msg_type == 1:   # RECIPIENT_ADD
        if "guild_id" in message:
            chat = "thread"
        else:
            chat = "group"
        content = f"> *Added {message["mentions"][0]["username"]} to the {chat}.*"
    elif msg_type == 2:   # RECIPIENT_REMOVE
        if "guild_id" in message:
            chat = "thread"
        else:
            chat = "group"
        content = f"> *Removed {message["mentions"][0]["username"]} from the {chat}.*"
    elif msg_type == 3:   # CALL
        content = "> *Started a call.*"
    elif msg_type == 4:   # CHANNEL_NAME_CHANGE
        content = f"> *Changed the channel name to {message["content"]}.*"
    elif msg_type == 5:   # CHANNEL_ICON_CHANGE
        content = "> *Changed the channel icon.*"
    elif msg_type == 6:   # CHANNEL_PINNED_MESSAGE
        content = "> *Pinned a message to this channel.*"
    elif msg_type == 7:   # USER_JOIN
        content = "> *Joined the server.*"
    elif msg_type in (8, 9, 10, 11):   # PREMIUM_GUILD_SUBSCRIPTION (tiers 0-3)
        if message.get("content"):
            msg = f"Just boosted the server {message["content"]} times!"
        else:
            msg = "Just boosted the server!"
        if msg_type > 8:
            msg += f"Server has achieved Level {msg_type - 8}!"
        content = f"> *{msg}*"
    elif msg_type == 12:   # CHANNEL_FOLLOW_ADD
        content = f"> *Added {message["content"]} to this channel. Its most important updates will show up here.*"
    # 13 - removed
    elif msg_type == 14:   # GUILD_DISCOVERY_DISQUALelifIED
        content = "> *This server has been removed from Server Discovery because it no longer passes all the requirements.*"
    elif msg_type == 15:   # GUILD_DISCOVERY_REQUALelifIED
        content = "> *This server is eligible for Server Discovery again and has been automatically relisted!*"
    elif msg_type == 16:   # GUILD_DISCOVERY_GRACE_PERIOD_INITIAL_WARNING
        content = "> *This server has failed Discovery activity requirements for 1 week.*"
    elif msg_type == 17:   # GUILD_DISCOVERY_GRACE_PERIOD_FINAL_WARNING
        content = "> *This server has failed Discovery activity requirements for 3 weeks in a row.*"
    elif msg_type == 18:   # THREAD_CREATED
        content = f"> *Started a thread: {message["content"]}.*"
    # 19 - REPLY - skip
    # 20 - CHAT_INPUT_COMMAND
    elif msg_type == 21:   # THREAD_STARTER_MESSAGE
        content = "> *Start of a thread*"
    elif msg_type == 22:   # GUILD_INVITE_REMINDER
        content = "> *Kind reminder to invite more people to this server.*"
    # 23 - CONTEXT_MENU_COMMAND
    elif msg_type == 24:   # AUTO_MODERATION_ACTION
        embeds = message["embeds"]
        for num, embed in enumerate(embeds):
            if embed["type"] == "auto_moderation_message":
                break
        else:
            return message
        data = {}
        for field in embeds.pop(num)["fields"]:
            if field["name"] == "rule_name":
                data["rule_name"] = field["value"]
            elif field["name"] == "channel_id":
                data["channel_id"] = field["value"]
            elif field["name"] == "block_profile_update_type":
                data["block_profile_update_type"] = field["value"]
            elif field["name"] == "quarantine_user":
                data["quarantine_user"] = field["value"]
            elif field["name"] == "quarantine_user_action":
                data["quarantine_user_action"] = field["value"]
            elif field["name"] == "application_name":
                data["application_name"] = field["value"]
        content_list = [
            "*AUTOMOD ALERT*",
            f"Rule {data.get("rule_name")} violation detected!",
        ]
        if "channel_id" in data:
            content_list.append(f"In channel: <#{data["channel_id"]}>")
        if "block_profile_update_type" in data:
            content_list.append(f"Blocked profile update: {data["block_profile_update_type"]}")
        if "quarantine_user" in data:
            content_list.append(f"Quarantine user reason: {data["quarantine_user"]}")
        if "quarantine_user_action" in data:
            content_list.append(f"Quarantine type: {data["quarantine_user_action"]}")
        if "application_name" in data:
            content_list.append(f"Application that triggered the rule: {data["application_name"]}")
        content = ""
        for line in content_list:
            content += f"> {line}\n"
        content = content.strip("\n")
    elif msg_type == 25 and "role_subscription_data" in message:   # ROLE_SUBSCRIPTION_PURCHASE
        role_subscription_data = message["role_subscription_data"]
        content = f"> *Subscribed to {role_subscription_data["tier_name"]}!*"
    # 26 - INTERACTION_PREMIUM_UPSELL - skip
    elif msg_type == 27:   # STAGE_START
        content = f"> *Started {message["content"]}.*"
    elif msg_type == 28:   # STAGE_END
        content = f"> *Ended {message["content"]}.*"
    elif msg_type == 29:   # STAGE_SPEAKER
        content = "> *Is now a speaker.*"
    elif msg_type == 30:   # STAGE_RAISE_HAND
        content = "> *Requested to speak.*"
    elif msg_type == 31:   # STAGE_TOPIC
        content = f"> *Changed the Stage topic: {message["content"]}.*"
    elif msg_type == 32:   # GUILD_APPLICATION_PREMIUM_SUBSCRIPTION
        if "application" in message:
            app_name = message["application"]["name"]
        else:
            app_name = "a deleted application"
        content = f"> *Upgraded {app_name} to premium for this server!*"
    # 33 - removed
    # 34 - removed
    # 35 - PREMIUM_REFERRAL - skip
    elif msg_type == 36:   # GUILD_INCIDENT_ALERT_MODE_ENABLED
        content = f"> *Enabled security actions until {message["content"]}.*"
    elif msg_type == 37:   # GUILD_INCIDENT_ALERT_MODE_DISABLED
        content = "> *Disabled security actions.*"
    elif msg_type == 38:   # GUILD_INCIDENT_REPORT_RAID
        content = "> *Reported a raid.*"
    elif msg_type == 39:   # GUILD_INCIDENT_REPORT_FALSE_ALARM
        content = "> *Reported a false alarm.*"
    # 40 - GUILD_DEADCHAT_REVIVE_PROMPT - skip
    elif msg_type == 41:   # CUSTOM_GIFT
        if len(message["embeds"]) >= 1:
            content = f"> *Bought a gift: {message["embeds"].pop(0)["url"]}*"
        else:
            content = "> *Bought a gift: url not found*"
    # 42 - GUILD_GAMING_STATS_PROMPT - skip
    # 43 - removed
    elif msg_type == 44 and "purchase_notification" in message:   # PURCHASE_NOTIFICATION
        product_name = message["purchase_notification"]["guild_product_purchase"]["product_name"]
        content = f"> *Purchased {product_name}!*"
    # 45 - removed
    elif msg_type == 46:   # POLL_RESULT
        embeds = message["embeds"]
        for num, embed in enumerate(embeds):
            if embed["type"] == "poll_result":
                break
        else:
            return message
        data = {}
        for field in embeds.pop(num)["fields"]:
            if field["name"] == "poll_question_text":
                data["poll_question_text"] = field["value"]
            elif field["name"] == "victor_answer_text":
                data["victor_answer_text"] = field["value"]
            elif field["name"] == "total_votes":
                data["total_votes"] = field["value"]
            elif field["name"] == "victor_answer_votes":
                data["victor_answer_votes"] = field["value"]
        if "victor_answer_votes" in data and "total_votes" in data:
            value = round((int(data["victor_answer_votes"]) / int(data["total_votes"])) * 100)
            percent = f", {value}%"
        else:
            percent = ", 0%"
        content_list = (
            "*Poll has ended, results:*",
            data.get("poll_question_text", "???"),
            f"Winning answer: {data.get("victor_answer_text", "???")}{percent}",
            f"Votes: {data.get("victor_answer_votes", "0")} of total: {data.get("total_votes", "0")}",
        )
        content = ""
        for line in content_list:
            content += f"> {line}\n"
        content = content.strip("\n")
    # 47 - CHANGELOG - skip
    # 48 - NITRO_NOTIFICATION - skip
    # 49 - CHANNEL_LINKED_TO_LOBBY - skip
    # 50 - GIFTING_PROMPT - skip
    elif msg_type == 51 and "application" in message:   # IN_GAME_MESSAGE_NUX
        content = f"> *Messaged you from {message["application"]["name"]}*"
    # 52 - GUILD_JOIN_REQUEST_ACCEPT_NOTIFICATION - missing data: join_request
    # 53 - GUILD_JOIN_REQUEST_REJECT_NOTIFICATION - missing data: join_request
    # 54 - GUILD_JOIN_REQUEST_WITHDRAWN_NOTIFICATION - missing data: join_request
    elif msg_type == 55:   # HD_STREAMING_UPGRADED
        content = "> *Activated HD Streaming Mode*"
    else:
        return message
    message["content"] = content
    return message


def prepare_poll(poll):
    """Prepare poll data"""
    expires = 0
    if "expiry" in poll:
        expires = generate_timestamp(poll["expiry"], "R", unix=True)
    options = []
    for answer in poll["answers"]:
        answer_id = answer["answer_id"]
        me_voted = False
        answer_votes = 0
        for answer_res in poll["results"]["answer_counts"]:
            if answer_res["id"] == answer_id:
                answer_votes = answer_res["count"]
                me_voted = answer_res["me_voted"]
                break
        options.append({
            "answer": answer["poll_media"].get("text"),
            "id": answer_id,
            "count": answer_votes,
            "me_voted": me_voted,
        })
    return {
        "question": poll["question"].get("text", "???"),
        "multi": poll["allow_multiselect"],
        "options": options,
        "expires": expires,
    }
