import base64
import http.client
import json
import logging
import os
import socket
import ssl
import time
import urllib.parse

import socks
from discord_protos import FrecencyUserSettings, PreloadedUserSettings
from google.protobuf.json_format import MessageToDict, ParseDict

from endcord import peripherals

CLIENT_NAME = "endcord"
DISCORD_HOST = "discord.com"
DISCORD_CDN_HOST = "cdn.discordapp.com"
DISCORD_EPOCH = 1420070400
SEARCH_PARAMS = ("content", "channel_id", "author_id", "mentions", "has", "max_id", "min_id", "pinned", "offset")
SEARCH_HAS_OPTS = ("link", "embed", "poll", "file", "video", "image", "sound", "sticker", "forward")
logger = logging.getLogger(__name__)


def ceil(x):
    """
    Return the ceiling of x as an integral.
    Equivalent to math.ceil().
    """
    # lets not import whole math just for this
    return -int(-1 * x // 1)


def get_sticker_url(sticker):
    """Generate sticker download url from its type and id, lottie stickers will return None"""
    sticker_type = sticker["format_type"]
    if sticker_type == 1:   # png - downloaded as webp
        return f"https://media.discordapp.net/stickers/{sticker["id"]}.webp"
    if sticker_type == 2:   # apng
        return f"https://media.discordapp.net/stickers/{sticker["id"]}.png"
    if sticker_type == 4:   # gif
        return f"https://media.discordapp.net/stickers/{sticker["id"]}.gif"
    return None   # lottie


def generate_nonce():
    """Generate nonce string - current UTC time as discord snowflake"""
    return str((int(time.time() * 1000) - DISCORD_EPOCH * 1000) << 22)


def prepare_messages(data, have_channel_id=False):
    """Prepare list of messages"""
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
                if "message_snapshots" in message["referenced_message"]:
                    forwarded = message["referenced_message"]["message_snapshots"][0]["message"]
                    # additional text with forwarded message is sent separately
                    message["referenced_message"]["content"] = f"[Forwarded]: {forwarded.get("content")}"
                    message["referenced_message"]["embeds"] = forwarded.get("embeds")
                    message["referenced_message"]["attachments"] = forwarded.get("attachments")
                reference_embeds = []
                for embed in message["embeds"]:
                    content = ""
                    content += embed.get("url", "")  + "\n"
                    if "video" in embed and "url" in embed["video"]:
                        content = embed["video"]["url"] + "\n"
                    elif "image" in embed and "url" in embed["image"]:
                        content = embed["image"]["url"] + "\n"
                    elif "fields" in embed:
                        for field in embed["fields"]:
                            content += "\n" + field["name"] + "\n" + field["value"]  + "\n"
                        content = content.strip("\n")
                    elif "title" in embed:
                        content += embed["title"] + "\n"
                        content += embed.get("description", "") + "\n"
                    content = content.strip("\n")
                    if content and content not in message["content"]:
                        reference_embeds.append({
                            "type": embed["type"],
                            "name": None,
                            "url": content,
                        })
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
        if "member" in message:
            nick = message["member"]["nick"]
        else:
            nick = None
        if "message_snapshots" in message:
            forwarded = message["message_snapshots"][0]["message"]
            # additional text with forwarded message is sent separately
            message["content"] = f"[Forwarded]: {forwarded.get("content")}"
            message["embeds"] = forwarded.get("embeds")
            message["attachments"] = forwarded.get("attachments")
        embeds = []
        for embed in message["embeds"]:
            content = ""
            content += embed.get("url", "")  + "\n"
            if "video" in embed and "url" in embed["video"]:
                content = embed["video"]["url"] + "\n"
            elif "image" in embed and "url" in embed["image"]:
                content = embed["image"]["url"] + "\n"
            elif "fields" in embed:
                for field in embed["fields"]:
                    content += "\n" + field["name"] + "\n" + field["value"]  + "\n"
                content = content.strip("\n")
            elif "title" in embed:
                content += embed["title"] + "\n"
                content += embed.get("description", "") + "\n"
            content = content.strip("\n")
            if content and content not in message["content"]:
                embeds.append({
                    "type": embed["type"],
                    "name": None,
                    "url": content,
                })
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
        if message["type"] == 7:
            message["content"] = "> *Joined the server.*"
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
            "stickers": message.get("sticker_items", []),   # {name, id, format_type}
        })
        if have_channel_id:
            messages[-1]["channel_id"] = message["channel_id"]
        # sticker types: 1 - png, 2 - apng, 3 - lottie, 4 - gif
    return messages


class Discord():
    """Methods for fetching and sending data to Discord using REST API"""

    def __init__(self, token, host, proxy=None):
        if host:
            self.host = urllib.parse.urlparse(host).netloc
            self.cdn_host = f"cdn.{urllib.parse.urlparse(host).netloc}"
        else:
            self.host = DISCORD_HOST
            self.cdn_host = DISCORD_CDN_HOST
        self.token = token
        self.header = {
            "content-type": "application/json",
            "user-agent": CLIENT_NAME,
            "authorization": self.token,
        }
        self.proxy = urllib.parse.urlparse(proxy)
        self.my_id = self.get_my_id(exit_on_error=True)
        self.protos = [[], []]
        self.stickers = []
        self.uploading = []


    def get_connection(self, host, port):
        """Get connection object and handle proxying"""
        if self.proxy.scheme:
            if self.proxy.scheme.lower() == "http":
                logger.info((self.proxy.hostname, self.proxy.port))
                connection = http.client.HTTPSConnection(self.proxy.hostname, self.proxy.port)
                connection.set_tunnel(host, port=port)
            elif "socks" in self.proxy.scheme.lower():
                proxy_sock = socks.socksocket()
                proxy_sock.set_proxy(socks.SOCKS5, self.proxy.hostname, self.proxy.port)
                proxy_sock.settimeout(10)
                proxy_sock.connect((host, port))
                proxy_sock = ssl.create_default_context().wrap_socket(proxy_sock, server_hostname=host)
                # proxy_sock.do_handshake()   # seems like its not needed
                connection = http.client.HTTPSConnection(host, port, timeout=10)
                connection.sock = proxy_sock
            else:
                connection = http.client.HTTPSConnection(host, port)
        else:
            connection = http.client.HTTPSConnection(host, port, timeout=5)
        return connection


    def get_my_id(self, exit_on_error=False):
        """Get my discord user ID"""
        message_data = None
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", "/api/v9/users/@me", message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            if exit_on_error:
                logger.warn("No internet connection. Exiting...")
                raise SystemExit("No internet connection. Exiting...")
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            return data["id"]
        if response.status == 401:   # unauthorized
            logger.error("unauthorized access. Probably invalid token. Exiting...")
            raise SystemExit("unauthorized access. Probably invalid token. Exiting...")
        logger.error(f"Failed to get my id. Response code: {response.status}")
        connection.close()
        return None


    def get_user(self, user_id, extra=False):
        """Get relevant informations about specified user"""
        message_data = None
        url = f"/api/v9/users/{user_id}/profile"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            if "guild_member" in data:
                nick = data["guild_member"]["nick"]
            else:
                nick = None
            if extra:   # extra data for rpc
                extra_data = {
                    "avatar": data["user"]["avatar"],
                    "avatar_decoration_data": data["user"]["avatar_decoration_data"],
                    "discriminator": data["user"]["discriminator"],
                    "flags": data["user"]["flags"],
                    "premium_type": data["premium_type"],
                }
            else:
                extra_data = None
            bio = data["user"].get("bio")
            pronouns = data["user"].get("pronouns")
            if data["user_profile"]:
                if data["user_profile"].get("bio"):
                    bio = data["user_profile"].get("bio")
                if data["user_profile"].get("pronouns"):
                    pronouns = data["user_profile"].get("pronouns")
            tag = None
            if data["user"]["primary_guild"] and "tag" in data["user"]["primary_guild"]:
                tag = data["user"]["primary_guild"]["tag"]
            return {
                "id": data["user"]["id"],
                "guild_id": None,
                "username": data["user"]["username"],
                "global_name": data["user"]["global_name"],
                "nick": nick,
                "bio": bio,
                "pronouns": pronouns,
                "joined_at": None,
                "tag": tag,
                "extra": extra_data,
                "roles": None,
            }
        logger.error(f"Failed to fetch user data. Response code: {response.status}")
        connection.close()
        return None


    def get_user_guild(self, user_id, guild_id):
        """Get relevant informations about specified user in a guild"""
        message_data = None
        url = f"/api/v9/users/{user_id}/profile?with_mutual_guilds=true&with_mutual_friends=true&guild_id={guild_id}"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            if "guild_member" in data:
                nick = data["guild_member"]["nick"]
                roles = data["guild_member"]["roles"]
                joined_at = data["guild_member"]["joined_at"][:10]
            else:
                nick = None   # just in case
                roles = None
                joined_at = None
            bio = data["user"].get("bio")
            pronouns = data["user"].get("pronouns")
            if data["user_profile"]:
                if data["user_profile"].get("bio"):
                    bio = data["user_profile"].get("bio")
                if data["user_profile"].get("pronouns"):
                    pronouns = data["user_profile"].get("pronouns")
            if data["guild_member_profile"]:
                guild_profile = data["guild_member_profile"]
                if "pronouns" in guild_profile and guild_profile["pronouns"]:
                    pronouns = data["guild_member_profile"]["pronouns"]
                if "bio" in guild_profile and guild_profile["bio"]:
                    bio = data["guild_member_profile"]["bio"]
            tag = None
            if data["user"]["primary_guild"] and "tag" in data["user"]["primary_guild"]:
                tag = data["user"]["primary_guild"]["tag"]
            return {
                "id": data["user"]["id"],
                "guild_id": guild_id,
                "username": data["user"]["username"],
                "global_name": data["user"]["global_name"],
                "nick": nick,
                "bio": bio,
                "pronouns": pronouns,
                "joined_at": joined_at,
                "tag": tag,
                "roles": roles,
            }
        logger.error(f"Failed to fetch user data. Response code: {response.status}")
        connection.close()
        return None


    def get_dms(self):
        """
        Get list of open DMs with their recipient.
        Same as gateway.get_dms()
        DM types:
        1 - single person text
        3 - group DM (name is not None)
        """
        message_data = None
        url = f"/api/v9/users/{self.my_id}/channels"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            dms = []
            dms_id = []
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
                dms_id.append(dm["id"])
            return dms, dms_id
        logger.error(f"Failed to fetch dm list. Response code: {response.status}")
        connection.close()
        return None, None


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
        url = f"/api/v9/guilds/{guild_id}/channels"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            channels = []
            for channel in data:
                channels.append({
                    "id": channel["id"],
                    "type": channel["type"],
                    "name": channel["name"],
                    "topic": channel.get("topic"),
                    "parent_id": channel.get("parent_id"),
                    "position": channel["position"],
                })
            return channels
        logger.error(f"Failed to fetch guild channels. Response code: {response.status}")
        connection.close()
        return None


    def get_messages(self, channel_id, num=50, before=None, after=None, around=None):
        """Get specified number of messages, optionally number before and after message ID"""
        message_data = None
        url = f"/api/v9/channels/{channel_id}/messages?limit={num}"
        if before:
            url += f"&before={before}"
        if after:
            url += f"&after={after}"
        if around:
            url += f"&around={around}"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            # debug
            # with open("messages.json", "w") as f:
            #     json.dump(data, f, indent=2)
            return prepare_messages(data)
        logger.error(f"Failed to fetch messages. Response code: {response.status}")
        connection.close()
        return None


    def get_reactions(self, channel_id, message_id, reaction):
        """Get reaction for specified message"""
        encoded_reaction = urllib.parse.quote(reaction)
        message_data = None
        url = f"/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_reaction}?limit=50&type=0"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            reaction = []
            for user in data:
                reaction.append({
                    "id": user["id"],
                    "username": user["username"],
                })
            return reaction
        logger.error(f"Failed to fetch reaction details: {reaction}. Response code: {response.status}")
        connection.close()
        return False


    def get_mentions(self, num=25, roles=True, everyone=True):
        """Get specified number of mentions, optionally including role and everyone mentions"""
        url = f"/api/v9/users/@me/mentions?limit={num}"
        if roles:
            url += "&roles=true"
        if everyone:
            url += "&everyone=true"
        message_data = None
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
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
        connection.close()
        return None


    def get_stickers(self):
        """Get default discord stickers and cache them"""
        if self.stickers:
            return self.stickers
        url = "/api/v9/sticker-packs?locale=en-US"
        message_data = None
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            for pack in data["sticker_packs"]:
                pack_stickers = []
                for sticker in pack["stickers"]:
                    pack_stickers.append({
                        "id": sticker["id"],
                        "name": sticker["name"],
                    })
                self.stickers.append({
                    "pack_id": pack["id"],
                    "pack_name": pack["name"],
                    "stickers": pack_stickers,
                })
            del (data, pack_stickers)
            return self.stickers
        logger.error(f"Failed to fetch stickers. Response code: {response.status}")
        connection.close()
        return None


    def get_settings_proto(self, num):
        """
        Get account settings:
        num=1 - General user settings
        num=2 - Frecency and favorites storage for various things
        """
        if self.protos[num-1]:
            return self.protos[num-1]
        message_data = None
        url = f"/api/v9/users/@me/settings-proto/{num}"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())["settings"]
            connection.close()
            if num == 1:
                decoded = PreloadedUserSettings.FromString(base64.b64decode(data))
            elif num == 2:
                decoded = FrecencyUserSettings.FromString(base64.b64decode(data))
            else:
                return {}
            self.protos[num-1] = MessageToDict(decoded)
            return self.protos[num-1]
        logger.error(f"Failed to fetch settings. Response code: {response.status}")
        connection.close()
        return None


    def patch_settings_proto(self, num, data):
        """
        Patch acount settings
        num=1 - General user settings
        num=2 - Frecency and favorites storage for various things"""
        if not self.protos[num-1]:
            self.get_settings_proto(num)
        self.protos[num-1].update(data)
        if num == 1:
            encoded = base64.b64encode(ParseDict(data, PreloadedUserSettings()).SerializeToString()).decode("utf-8")
        elif num == 2:
            encoded = base64.b64encode(ParseDict(data, FrecencyUserSettings()).SerializeToString()).decode("utf-8")
        else:
            return False

        message_data = json.dumps({"settings": encoded})
        url = f"/api/v9/users/@me/settings-proto/{num}"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("PATCH", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return False
        if response.status == 200:
            connection.close()
            return True
        logger.error(f"Failed to patch protobuf {num}. Response code: {response.status}")
        connection.close()
        return False


    def get_rpc_app(self, app_id):
        """Get data about Discord RPC application"""
        message_data = None
        url = f"/api/v9/oauth2/applications/{app_id}/rpc"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            return {
                "id": data["id"],
                "name": data["name"],
                "description": data["description"],
            }
        logger.error(f"Failed to fetch application rpc data. Response code: {response.status}")
        connection.close()
        return None


    def get_rpc_app_assets(self, app_id):
        """Get Discord application assets list"""
        message_data = None
        url = f"/api/v9/oauth2/applications/{app_id}/assets"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            assets = []
            for asset in data:
                assets.append({
                    "id": asset["id"],
                    "name": asset["name"],
                })
            return assets
        logger.error(f"Failed to fetch application assets. Response code: {response.status}")
        connection.close()
        return None


    def get_rpc_app_external(self, app_id, asset_url):
        """Get Discord application external assets"""
        url = f"/api/v9/applications/{app_id}/external-assets"
        message_data = json.dumps({"urls": [asset_url]})
        try:
            connection = self.get_connection(self.host, 443)
            # no oauth2 here
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            return data
        logger.error(f"Failed to fetch application external assets. Response code: {response.status}")
        connection.close()
        return None


    def get_file(self, url, save_path):
        """Download file from discord with proper header"""
        message_data = None
        url_object = urllib.parse.urlparse(url)
        filename = os.path.basename(url_object.path)
        connection = self.get_connection(url_object.netloc, 443)
        connection.request("GET", url_object.path + "?" + url_object.query, message_data, self.header)
        response = connection.getresponse()
        extension = response.getheader("Content-Type").split("/")[-1].replace("jpeg", "jpg")
        destination = os.path.join(save_path, filename)
        if os.path.splitext(destination)[-1] == "":
            destination = destination + "." + extension
        with open(destination, mode="wb") as file:
            file.write(response.read())


    def send_message(self, channel_id, message_text, reply_id=None, reply_channel_id=None, reply_guild_id=None, reply_ping=True, attachments=None, stickers=None):
        """Send a message in the channel with reply with or without ping"""
        message_dict = {
            "content": message_text,
            "tts": "false",
            "flags": 0,
            "nonce": generate_nonce(),
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
        if attachments:
            for attachment in attachments:
                if attachment["upload_url"]:
                    if "attachments" not in message_dict:
                        message_dict["attachments"] = []
                        message_dict["type"] = 0
                        message_dict["sticker_ids"] = []
                        message_dict["channel_id"] = channel_id
                        message_dict.pop("tts")
                        message_dict.pop("flags")
                    message_dict["attachments"].append({
                        "id": len(message_dict["attachments"]),
                        "filename": attachment["name"],
                        "uploaded_filename": attachment["upload_filename"],
                    })
        if stickers:
            message_dict["sticker_ids"] = stickers
        message_data = json.dumps(message_dict)
        url = f"/api/v9/channels/{channel_id}/messages"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
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
                "guild_id": data.get("guild_id"),
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
                "stickers": data.get("sticker_items", []),
            }
        logger.error(f"Failed to send message. Response code: {response.status}")
        connection.close()
        return None


    def send_update_message(self, channel_id, message_id, message_content):
        """Update the message in the channel"""
        message_data = json.dumps({"content": message_content})
        url = f"/api/v9/channels/{channel_id}/messages/{message_id}"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("PATCH", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
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
                "guild_id": data.get("guild_id"),
                "edited": True,
                "content": data["content"],
                "mentions": mentions,
                "mention_roles": data["mention_roles"],
                "mention_everyone": data["mention_everyone"],
                "stickers": data.get("sticker_items", []),
            }

        logger.error(f"Failed to edit the message. Response code: {response.status}")
        connection.close()
        return None


    def send_delete_message(self, channel_id, message_id):
        """Delete the message from the channel"""
        message_data = None
        url = f"/api/v9/channels/{channel_id}/messages/{message_id}"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("DELETE", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status != 204:
            logger.error(f"Failed to delete the message. Response code: {response.status}")
            connection.close()
            return False
        connection.close()
        return True


    def send_ack_message(self, channel_id, message_id):
        """Send information that this channel has been seen up to this message"""
        last_viewed = ceil((time.time() - DISCORD_EPOCH) / 86400)   # days since first second of 2015 (discord epoch)
        message_data = json.dumps({
            "last_viewed": last_viewed,
            "token": None,
        })
        url = f"/api/v9/channels/{channel_id}/messages/{message_id}/ack"
        logger.debug("Sending message ack")
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status != 200:
            logger.error(f"Failed to set the message as seen. Response code: {response.status}")
            connection.close()
            return False
        connection.close()
        return True


    def send_typing(self, channel_id):
        """Set '[username] is typing...' status on specified channel"""
        message_data = None
        url = f"/api/v9/channels/{channel_id}/typing"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status != 204:
            logger.error(f"Failed to set typing. Response code: {response.status}")
            connection.close()
            return False
        connection.close()
        return True


    def send_reaction(self, channel_id, message_id, reaction):
        """Send reaction to specified message"""
        encoded_reaction = urllib.parse.quote(reaction)
        message_data = None
        url = f"/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_reaction}/%40me?location=Message%20Reaction%20Picker&type=0"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("PUT", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status != 204:
            logger.error(f"Failed to send reaction: {reaction}. Response code: {response.status}")
            connection.close()
            return False
        connection.close()
        return True


    def remove_reaction(self, channel_id, message_id, reaction):
        """Remove reaction from specified message"""
        encoded_reaction = urllib.parse.quote(reaction)
        message_data = None
        url = f"/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_reaction}/0/%40me?location=Message%20Inline%20Button&burst=false"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("DELETE", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status != 204:
            logger.error(f"Failed to delete reaction: {reaction}. Response code: {response.status}")
            connection.close()
            return False
        connection.close()
        return True


    def send_mute_guild(self, mute, guild_id):
        """Mute/unmute channel, category, server or DM"""
        guild_id = str(guild_id)

        message_dict = {
            "guilds": {
                guild_id: {
                    "muted": bool(mute),
                },
            },
        }

        if mute:
            message_dict["guilds"][guild_id]["mute_config"] = {
                "end_time": None,
                "selected_time_window": -1,
            }

        url = "/api/v9/users/@me/guilds/settings"
        message_data = json.dumps(message_dict)
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("PATCH", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            connection.close()
            return True
        logger.error(f"Failed to set guild mute config. Response code: {response.status}")
        connection.close()
        return False


    def send_mute_channel(self, mute, channel_id, guild_id):
        """Mute/unmute channel, category, server or DM"""
        channel_id = str(channel_id)
        guild_id = str(guild_id)

        channel_overrides = {
            channel_id: {
                "muted": mute,
            },
        }

        if mute:
            channel_overrides[channel_id]["mute_config"] = {
                "end_time": None,
                "selected_time_window": -1,
            }

        message_dict = {
            "guilds": {
                guild_id: {
                    "channel_overrides": channel_overrides,
                },
            },
        }

        url = "/api/v9/users/@me/guilds/settings"
        message_data = json.dumps(message_dict)
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("PATCH", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            connection.close()
            return True
        logger.error(f"Failed to set guild mute config. Response code: {response.status}")
        connection.close()
        return False


    def send_mute_dm(self, mute, dm_id):
        """Mute/unmute channel, category, server or DM"""
        dm_id = str(dm_id)

        message_dict = {
            "channel_overrides": {
                dm_id: {
                    "muted": bool(mute),
                },
            },
        }

        if mute:
            message_dict["channel_overrides"][dm_id]["mute_config"] = {
                "end_time": None,
                "selected_time_window": -1,
            }

        url = "/api/v9/users/@me/guilds/%40me/settings"
        logger.info(message_dict)
        message_data = json.dumps(message_dict)
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("PATCH", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            connection.close()
            return True
        logger.error(f"Failed to set DM mute config. Response code: {response.status}")
        connection.close()
        return False


    def join_thread(self, thread_id):
        """Join a thread"""
        message_data = None
        # location is not necesarily "Sidebar Overflow"
        url = f"/api/v9/channels/{thread_id}/thread-members/@me?location=Sidebar%20Overflow"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status != 204:
            logger.error(f"Failed to join a thread. Response code: {response.status}")
            connection.close()
            return False
        connection.close()
        return True


    def leave_thread(self, thread_id):
        """Leave a thread"""
        message_data = None
        # location is not necesarily "Sidebar Overflow"
        url = f"/api/v9/channels/{thread_id}/thread-members/@me?location=Sidebar%20Overflow"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("DELETE", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status != 204:
            logger.error(f"Failed to leave a thread. Response code: {response.status}")
            connection.close()
            return False
        connection.close()
        return True


    def search(self, guild_id, content=None, channel_id=None, author_id=None, mentions=None, has=None, max_id=None, min_id=None, pinned=None, offset=None):
        """
        Search in specified guild
        author_id   - (from) user_id
        mentions    - user_id
        has         - link, embed, poll, file, video, image, sound, sticker, forward
        max_id      - (before) convert date to (floor) snowflake
        min_id      - (after) convert date to (ceil) snowflake
        channel_id  - (in) channel_id
        pinned      - true, false
        content     - search text
        offset      - starting number
        """
        message_data = None
        url = f"/api/v9/guilds/{guild_id}/messages/search?"
        if "true" in pinned:
            pinned = "true"
        elif "false" in pinned:
            pinned = "false"
        for one_has in has:
            if one_has not in SEARCH_HAS_OPTS:
                return 0, []
        content = [content]
        offset = [offset]
        for num, items in enumerate([content, channel_id, author_id, mentions, has, max_id, min_id, pinned, offset]):
            for item in items:
                if item:
                    url += f"{SEARCH_PARAMS[num]}={urllib.parse.quote(item)}&"
        url = url.rstrip("&")
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return 0, []
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            messages = []
            total = data["total_results"]
            for message in data["messages"]:
                messages.append(message[0])
            return total, prepare_messages(messages, have_channel_id=True)
        logger.error(f"Failed to perform a message search. Response code: {response.status}")
        connection.close()
        return 0, []


    def request_attachment_link(self, channel_id, path, custom_name=None):
        """
        Request attachment upload link.
        If file is too large - will return None.
        Return codes:
        0 - OK
        1 - Failed
        2 - File too large
        """
        if custom_name:
            filename = custom_name
        else:
            filename = os.path.basename(path)
        message_data = json.dumps({
            "files": [{
                "file_size": peripherals.get_file_size(path),
                "filename": filename,
                "id": None,   # should not be None, but works
                "is_clip": peripherals.get_is_clip(path),
            }],
        })
        url = f"/api/v9/channels/{channel_id}/attachments"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None, 1
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            return data["attachments"][0], 0
        if response.status == 413:
            logger.warn("Failed to get attachment upload link: 413 - File too large.")
            connection.close()
            return None, 2   # file too large
        logger.error(f"Failed to get attachment upload link. Response code: {response.status}")
        connection.close()
        return None, 1


    def upload_attachment(self, upload_url, path):
        """
        Upload a file to provided url
        """
        # will load whole file into RAM, but discord limits upload size anyways
        # and this function wont be run if request_attachment_link() is not successful
        header = {
            "Content-Type": "application/octet-stream",
            "Origin": "https://discord.com",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "user-agent": CLIENT_NAME,
        }
        url = urllib.parse.urlparse(upload_url)
        upload_url_path = f"{url.path}?{url.query}"
        with open(path, "rb") as f:
            try:
                connection = self.get_connection(url.netloc, 443)
                self.uploading.append((upload_url, connection))
                connection.request("PUT", upload_url_path, f, header)
                response = connection.getresponse()
                self.uploading.remove((upload_url, connection))
            except (socket.gaierror, TimeoutError):
                connection.close()
                return False
            if response.status == 200:
                connection.close()
                return True
            # discord client is also performing OPTIONS request, idk why, not needed here
            logger.error(f"Failed to upload attachment. Response code: {response.status}")
            connection.close()
            return False


    def cancel_uploading(self, url=None):
        """Stop specified upload, or all running uploads"""
        if url:
            for upload in self.uploading:
                upload_url, connection = upload
                if upload_url == url:
                    self.uploading.remove(upload)
        else:
            for upload in self.uploading:
                upload_url, connection = upload
                try:
                    connection.sock.shutdown()
                    connection.sock.close()
                except Exception:
                    logger.debug("Cancel upload: upload socket already closed.")
                self.uploading.remove(upload)


    def cancel_attachment(self, attachment_name):
        """Cancel uploaded attachments"""
        attachment_name = urllib.parse.quote(attachment_name, safe="")
        message_data = None
        url = f"/api/v9/attachments/{attachment_name}"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("DELETE", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 204:
            connection.close()
            return True
        if response.status == 429:
            # discord usually returns 429 for this request, but original client does not retry after some time
            # so this wont retry either, file wont be sent in the message anyway
            logger.debug("Failed to delete attachemnt. Response code: 429 - Too Many Requests")
            connection.close()
            return True
        logger.error(f"Failed to delete attachemnt. Response code: {response.status}")
        connection.close()
        return None


    def send_voice_message(self, channel_id, path, reply_id=None, reply_channel_id=None, reply_guild_id=None, reply_ping=None):
        """Send voice message from file path, file must be ogg"""
        waveform, duration = peripherals.get_audio_waveform(path)
        if not duration:
            logger.warn(f"Couldnt read voice message file: {path}")
        upload_data, status = self.request_attachment_link(channel_id, path, custom_name="voice-message.ogg")
        if status != 0:
            logger.warn("Cant send voice message, attachment error")
        uploaded = self.upload_attachment(upload_data["upload_url"], path)
        if not uploaded:
            logger.warn("Cant upload voice message, upload error")
        message_dict = {
            "channel_id": channel_id,
            "content": "",
            "attachments": [{
                "id": "0",
                "filename": "voice-message.ogg",
                "uploaded_filename": upload_data["upload_filename"],
                "duration_secs": duration,
                "waveform": waveform,
            }],
            "message_reference": None,
            "flags": 8192,
            "type": 0,
            "sticker_ids": [],
            "nonce": generate_nonce(),
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
        url = f"/api/v9/channels/{channel_id}/messages"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return False
        if response.status == 200:
            connection.close()
            return True
        logger.error(f"Failed to send voice message. Response code: {response.status}")
        connection.close()
        return False


    def get_pfp(self, user_id, pfp_id, size=80):
        """Download pfp for specified user"""
        message_data = None
        url = f"/avatars/{user_id}/{pfp_id}.webp?size={size}"
        header = {
            "Origin": "https://discord.com",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
            "user-agent": CLIENT_NAME,
        }
        try:
            connection = self.get_connection(self.cdn_host, 443)
            connection.request("GET", url, message_data, header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            destination = os.path.join(peripherals.temp_path, f"{pfp_id}.webp")
            with open(destination, "wb") as f:
                f.write(response.read())
            connection.close()
            return destination
        logger.error(f"Failed to download pfp. Response code: {response.status}")
        connection.close()
        return None


    def get_my_standing(self):
        """Get my account standing"""
        message_data = None
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", "/api/v9/safety-hub/@me", message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            return data["account_standing"]["state"]
        logger.error(f"Failed to fetch account standing. Response code: {response.status}")
        connection.close()
        return None
