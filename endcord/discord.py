import base64
import http
import json
import logging
import socket
import time
import urllib.parse

from discord_protos import PreloadedUserSettings
from google.protobuf.json_format import MessageToJson

CLIENT_NAME = "endcord"
DISCORD_EPOCH = 1420070400
logger = logging.getLogger(__name__)


def none_dict_extract(input_dict, key):
    """Returns value from dict, if that key is invalid, returns None"""
    if key in input_dict:
        return input_dict[key]
    return None


def ceil(x):
    """
    Return the ceiling of x as an integral.
    Equivalent to math.ceil().
    """
    # lets not import whole math just for math.ceil()
    return -int(-1 * x // 1)


class Discord():
    """Methods for fetching and sending data to Discord using REST API"""

    def __init__(self, token):
        self.token = token
        self.header = {"content-type": "application/json", "user-agent": CLIENT_NAME, "authorization": self.token}
        self.my_id = self.get_my_id(exit_on_error=True)
        self.cache_proto_1 = None
        self.cache_proto_2 = None


    def get_my_id(self, exit_on_error=False):
        """Get my discord user ID"""
        message_data = None
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("GET", "/api/v10/users/@me", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            if exit_on_error:
                logger.warn("No internet connection. Exiting...")
                raise SystemExit("No internet connection. Exiting...")
            return None
        if response.status == 200:
            return json.loads(response.read())["id"]
        if response.status == 401:   # unauthorized
            logger.error("unauthorized access. Probably invalid token. Exiting...")
            raise SystemExit("unauthorized access. Probably invalid token. Exiting...")
        logger.error(f"Failed to get my id. Response code: {response.status}")
        return None


    def get_user(self, user_id):
        """Get relevant informations about specified user"""
        message_data = None
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("GET", f"/api/v10/users/{user_id}/profile", message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            return None
        if response.status == 200:
            data = json.loads(response.read())
            if "guild_member" in data:
                nick = data["guild_member"]["nick"]
            else:
                nick = None
            return {
                "id": data["user"]["id"],
                "username": data["user"]["username"],
                "global_name": data["user"]["global_name"],
                "nick": nick,
                "bio": data["user"]["bio"],
                "pronouns": data["user_profile"]["pronouns"],
                "roles": None,
            }
        logger.error(f"Failed to fetch user data. Response code: {response.status}")
        return None


    def get_user_guild(self, user_id, guild_id):
        """Get relevant informations about specified user in a guild"""
        message_data = None
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("GET", f"/api/v10/users/{user_id}/profile?with_mutual_guilds=true&with_mutual_friends=true&guild_id={guild_id}", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status == 200:
            data = json.loads(response.read())
            if "guild_member" in data:
                nick = data["guild_member"]["nick"]
                roles = data["guild_member"]["roles"]
            else:
                nick = None   # just in case
                roles = None
            return {
                "id": data["user"]["id"],
                "username": data["user"]["username"],
                "global_name": data["user"]["global_name"],
                "nick": nick,
                "bio": data["user"]["bio"],
                "pronouns": data["user_profile"]["pronouns"],
                "roles": roles,
            }
        logger.error(f"Failed to fetch user data. Response code: {response.status}")
        return None


    def get_dms(self):
        """
        Get list of open DMs with their recipient
        DM types:
        1 - single person text
        3 - group DM (name is not None)
        """
        message_data = None
        connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
        connection.request("GET", f"/api/v10/users/{self.my_id}/channels", message_data, self.header)
        response = connection.getresponse()
        if response.status == 200:
            data = json.loads(response.read())
            dms = []
            for dm in data:
                recipients = []
                for recipient in dm["recipients"]:
                    recipients.append({
                        "id": recipient["id"],
                        "username": recipient["username"],
                        "global_name": recipient["global_name"],
                    })
                if "name" in dm:
                    name = dm["name"]
                else:
                    name = recipients[0]["global_name"]
                dms.append({
                    "id": dm["id"],
                    "type": dm["type"],
                    "recipients": recipients,
                    "name": name,
                })
            return dms
        logger.error(f"Failed to fetch dm list. Response code: {response.status}")
        return None


    def get_channels(self, guild_id):
        """
        Get channels belonging to specified guild
        Channel types:
        0 - text
        2 - voice
        4 - category
        5 - announcement
        11/12 - thread
        15 - forum (contains only threads)
        """
        message_data = None
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("GET", f"/api/v10/guilds/{guild_id}/channels", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status == 200:
            data = json.loads(response.read())
            channels = []
            for channel in data:
                channels.append({
                    "id": channel["id"],
                    "type": channel["type"],
                    "name": channel["name"],
                    "topic": none_dict_extract(channel, "topic"),
                    "parent_id": none_dict_extract(channel, "parent_id"),
                    "position": channel["position"],
                })
            return channels
        logger.error(f"Failed to fetch guild channels. Response code: {response.status}")
        return None


    def get_messages(self, channel_id, num=50, before=None, after=None):
        """Get specified number of messages, optionally number before and after message ID"""
        message_data = None
        url = f"/api/v10/channels/{channel_id}/messages?limit={num}"
        if before:
            url += f"&before={before}"
        if after:
            url += f"&after={after}"
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status == 200:
            data = json.loads(response.read())
            messages = []
            for message in data:
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
                        reference_embeds = []
                        for embed in message["referenced_message"]["embeds"]:
                            reference_embeds.append({
                                "type": embed["type"].replace("rich", "url"),
                                "name": None,
                                "url": none_dict_extract(embed, "url"),

                            })
                        for attachment in message["referenced_message"]["attachments"]:
                            reference_embeds.append({
                                "type": attachment["content_type"],
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
                if "member" in message:
                    nick = response["d"]["member"]["nick"]
                else:
                    nick = None
                embeds = []
                for embed in message["embeds"]:
                    if "url" in embed:
                        content = embed["url"]
                    elif "fields" in embed:
                        content = f"{embed["fields"][0]["name"]}\n{embed["fields"][0]["value"]}"
                    else:
                        content = None
                    embeds.append({
                        "type": embed["type"].replace("rich", "url"),
                        "name": None,
                        "url": content,
                    })
                for attachment in message["attachments"]:
                    embeds.append({
                        "type": attachment["content_type"],
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
                messages.append({
                    "id": message["id"],
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
                })
            return messages
        logger.error(f"Failed to fetch messages. Response code: {response.status}")
        return None


    def get_reactions(self, emoji_name, emoji_id, message_id, channel_id):
        """Get reactions belonging to {message_id} inside specified channel"""
        message_data = None
        emoji_name_enc = urllib.parse.quote(emoji_name)
        url = f"/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{emoji_name_enc}"
        if emoji_id:
            url += f"%3A{emoji_id}"
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status == 200:
            data = json.loads(response.read())
            reactions = []
            for user in data:
                reactions.append({
                    "emoji_id": user["id"],
                    "username": user["username"],
                    "global_name": user["global_name"],
                })
            return reactions
        logger.error(f"Failed to fetch reactions. Response code: {response.status}")
        return None


    def get_mentions(self, num=25, roles=True, everyone=True):
        """Get specified number of mentions, optionally including role and everyone mentions"""
        url = f"/api/v10/users/@me/mentions?limit={num}"
        if roles:
            url += "&roles=true"
        if everyone:
            url += "&everyone=true"
        message_data = None
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status == 200:
            data = json.loads(response.read())
            mentions = []
            for mention in data:
                mentions.append({
                    "id": mention["id"],
                    "channel_id": mention["channel_id"],
                    "timestamp": mention["timestamp"],
                    "content": mention["content"],
                    "user_id": mention["author"]["id"],
                    "username": mention["author"]["username"],
                    "global_name": mention["author"]["global_name"],
                })
            return mentions
        logger.error(f"Failed to fetch mentions. Response code: {response.status}")
        return None


    def get_settings_proto(self, num):
        """
        Get account settings:
        num=1 - General Discord user settings
        num=2 - Frecency and favorites storage for various things
        """
        if num == 1 and self.cache_proto_1:
            return self.cache_proto_1
        if num == 2 and self.cache_proto_1:
            return self.cache_proto_2
        message_data = None
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("GET", f"/api/v10/users/@me/settings-proto/{num}", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status == 200:
            data = json.loads(response.read())["settings"]
            decoded = PreloadedUserSettings.FromString(base64.b64decode(data))
            if num == 1:
                self.cache_proto_1 = json.loads(MessageToJson(decoded))
                return self.cache_proto_1
            if num == 2:
                self.cache_proto_2 = json.loads(MessageToJson(decoded))
                return self.cache_proto_2
        logger.error(f"Failed to fetch settings. Response code: {response.status}")
        return None


    def send_message(self, channel_id, message_text, reply_id=None, reply_channel_id=None, reply_guild_id=None, reply_ping=True):
        """Send a message in the channel with reply with or without ping"""
        message_dict = {
            "content": message_text,
            "tts": "false",
            "flags": 0,
        }
        if reply_id and reply_channel_id:
            message_dict["message_reference"] = {
                "message_id": reply_id,
                "channel_id": reply_channel_id,
            }
            if reply_guild_id:
                message_dict["message_reference"]["guild_id"] = reply_guild_id
            if not reply_ping:
                if reply_guild_id:
                    message_dict["allowed_mentions"] = {
                        "parse": ["users", "roles", "everyone"],
                    }
                else:
                    message_dict["allowed_mentions"] = {
                        "parse": ["users", "roles", "everyone"],
                        "replied_user": False,
                    }
        message_data = json.dumps(message_dict)
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("POST", f"/api/v10/channels/{channel_id}/messages", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status == 200:
            data = json.loads(response.read())
            if "referenced_message" in data:
                reference = {
                    "id": data["referenced_message"]["id"],
                    "timestamp": data["referenced_message"]["timestamp"],
                    "content": data["referenced_message"]["content"],
                    "user_id": data["referenced_message"]["author"]["id"],
                    "username": data["referenced_message"]["author"]["username"],
                    "global_name": data["referenced_message"]["author"]["global_name"],
                }
            else:
                reference = None
            return {
                "id": data["id"],
                "channel_id": data["channel_id"],
                "guild_id": none_dict_extract(data, "guild_id"),
                "timestamp": data["timestamp"],
                "edited": False,
                "content": data["content"],
                "mentions": data["mentions"],
                "mention_roles": data["mention_roles"],
                "mention_everyone": data["mention_everyone"],
                "user_id": data["author"]["id"],
                "username": data["author"]["username"],
                "global_name": data["author"]["global_name"],
                "referenced_message": reference,
                "reactions": [],
                "embeds": data["embeds"],
            }
        logger.error(f"Failed to send message. Response code: {response.status}")
        return None


    def send_update_message(self, channel_id, message_id, message_content):
        """Update the message in the channel"""
        message_data = json.dumps({"content": message_content})
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("PATCH", f"/api/v10/channels/{channel_id}/messages/{message_id}", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status == 200:
            data = json.loads(response.read())
            mentions = []
            if data["mentions"]:
                for mention in data["mentions"]:
                    mentions.append({
                        "username": mention["username"],
                        "id": mention["id"],
                    })
            return {
                "id": data["id"],
                "channel_id": data["channel_id"],
                "guild_id": none_dict_extract(data, "guild_id"),
                "edited": True,
                "content": data["content"],
                "mentions": mentions,
                "mention_roles": data["mention_roles"],
                "mention_everyone": data["mention_everyone"],
                "embeds": data["embeds"],
            }

        logger.error(f"Failed to edit the message. Response code: {response.status}")
        return None


    def send_delete_message(self, channel_id, message_id):
        """Delete the message from the channel"""
        message_data = None
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("DELETE", f"/api/v10/channels/{channel_id}/messages/{message_id}", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status != 204:
            logger.error(f"Failed to delete the message. Response code: {response.status}")
            return False
        return True


    def send_ack_message(self, channel_id, message_id):
        """Send discord information that this channel has been seen up to this message"""
        last_viewed = ceil((time.time() - DISCORD_EPOCH) / 86400)   # days since first second of 2015 (discord epoch)
        message_data = json.dumps({
            "last_viewed": last_viewed,
            "token": None,
        })
        logger.debug("Sending message ack")
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("POST", f"/api/v10/channels/{channel_id}/messages/{message_id}/ack", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status != 200:
            logger.error(f"Failed to set the message as seen. Response code: {response.status}")
            return False
        return True


    def send_typing(self, channel_id):
        """Set '[username] is typing...' status on specified channel"""
        message_data = None
        try:
            connection = http.client.HTTPSConnection("discord.com", 443, timeout=5)
            connection.request("POST", f"/api/v10/channels/{channel_id}/typing", message_data, self.header)
            response = connection.getresponse()
        except socket.gaierror:
            return None
        if response.status != 204:
            logger.error(f"Failed to set typing. Response code: {response.status}")
            return False
        return True
