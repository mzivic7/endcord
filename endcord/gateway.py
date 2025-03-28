import base64
import json
import logging
import random
import socket
import sys
import threading
import time
import urllib
import zlib
from http.client import HTTPSConnection

import websocket
from discord_protos import PreloadedUserSettings
from google.protobuf.json_format import MessageToJson

from endcord import debug, perms

CLIENT_NAME = "endcord"
DISCORD_HOST = "discord.com"
LOCAL_MEMBER_COUNT = 50   # CPU-RAM intensive
ZLIB_SUFFIX = b"\x00\x00\xff\xff"
inflator = zlib.decompressobj()
logger = logging.getLogger(__name__)


def zlib_decompress(data):
    """Decompress zlib data, if it is not zlib compressed return data instead"""
    buffer = bytearray()
    buffer.extend(data)
    if len(data) < 4 or data[-4:] != ZLIB_SUFFIX:
        return data
    try:
        return inflator.decompress(buffer)
    except zlib.error as e:
        logger.error(f"zlib error: {e}")
        return None


def reset_inflator():
    """Resets inflator object"""
    global inflator
    del inflator
    inflator = zlib.decompressobj()   # noqa


class Gateway():
    """Methods for fetching and sending data to Discord using Discord's gateway through websocket"""

    def __init__(self, host, token):
        if host:
            self.host = urllib.parse.urlparse(host).netloc
        else:
            self.host = DISCORD_HOST
        self.token = token
        self.run = True
        self.wait = False
        self.state = 0
        self.heartbeat_received = True
        self.sequence = None
        self.resume_gateway_url = ""
        self.session_id = ""
        self.clear_ready_vars()
        self.messages_buffer = []
        self.typing_buffer = []
        self.summaries_buffer = []
        self.msg_ack_buffer = []
        self.threads_buffer = []
        self.reconnect_requested = False
        self.status_changed = False
        self.activities_changed = False
        self.roles_changed = False
        self.user_settings_proto = None
        threading.Thread(target=self.thread_guard, daemon=True, args=()).start()


    def clear_ready_vars(self):
        """Clear local variables when new READY event is received"""
        self.ready = False
        self.my_status = {}
        self.activities = []
        self.guilds = []
        self.roles = []
        self.member_roles = []
        self.msg_unseen = []
        self.msg_ping = []
        self.subscribed = []
        self.dms = []
        self.dms_id = []
        self.blocked = []
        self.my_roles = []


    def thread_guard(self):
        """
        Check if reconnect is requested and run reconnect thread if its not running.
        This is one in main thread so other threads are not further recursing when
        reconnecting multiple times.
        """
        while self.run:
            if self.reconnect_requested:
                self.reconnect_requested = False
                if not self.reconnect_thread.is_alive():
                    self.reconnect_thread = threading.Thread(target=self.reconnect, daemon=True, args=())
                    self.reconnect_thread.start()
            time.sleep(0.5)


    def connect(self):
        """Create initial connection to Discord gateway"""
        connection = HTTPSConnection(self.host, 443)
        try:
            # subscribe works differently in v10
            connection.request("GET", "/api/v9/gateway")
        except (socket.gaierror, TimeoutError):
            logger.warn("No internet connection. Exiting...")
            raise SystemExit("No internet connection. Exiting...")
        response = connection.getresponse()
        if response.status == 200:
            self.gateway_url = json.loads(response.read())["url"]
        else:
            logger.error(f"Failed to get gateway url. Response code: {response.status}. Exiting...")
            raise SystemExit(f"Failed to get gateway url. Response code: {response.status}. Exiting...")
        self.ws = websocket.WebSocket()
        self.ws.connect(self.gateway_url + "/?v=9&encoding=json&compress=zlib-stream")
        self.state = 1
        self.heartbeat_interval = int(json.loads(zlib_decompress(self.ws.recv()))["d"]["heartbeat_interval"])
        self.receiver_thread = threading.Thread(target=self.receiver, daemon=True, args=())
        self.receiver_thread.start()
        self.heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True, args=())
        self.heartbeat_thread.start()
        self.reconnect_thread = threading.Thread()
        self.authenticate()


    def send(self, request):
        """Send data to gateway"""
        try:
            self.ws.send(json.dumps(request))
        except websocket._exceptions.WebSocketException:
            self.reconnect_requested = True


    def add_member_roles(self, guild_id, user_id, roles):
        """Add member-role pair to corresponding guild, number of users per guild is limited"""
        num = -1
        for num, guild in enumerate(self.member_roles):
            if guild["guild_id"] == guild_id:
                break
        else:
            self.member_roles.append({
                "guild_id": guild_id,
                "members": [],
            })
            num += 1
        for member in self.member_roles[num]["members"]:
            if member["user_id"] == user_id:
                return
        self.member_roles[num]["members"].insert(0, {
            "user_id": user_id,
            "roles": roles,
        })
        if len(self.member_roles[num]) > LOCAL_MEMBER_COUNT:
            self.member_roles[num].pop(-1)
        self.roles_changed = True


    def receiver(self):
        """Receive and handle all traffic from gateway, should be run in a thread"""
        logger.info("Receiver stared")
        while self.run and not self.wait:
            try:
                data = zlib_decompress(self.ws.recv())
                if data:
                    try:
                        response = json.loads(data)
                        opcode = response["op"]
                    except ValueError:
                        response = None
                        opcode = None
                else:
                    response = None
                    opcode = None
            except Exception as e:
                logger.warn(f"Receiver error: {e}")
                break
            logger.debug(f"Received: opcode={opcode}, optext={response["t"] if (response and "t" in response and response["t"] and "LIST" not in response["t"]) else 'None'}")

            if opcode == 11:
                self.heartbeat_received = True

            elif opcode == 10:
                self.heartbeat_interval = int(response["d"]["heartbeat_interval"])

            elif opcode == 1:
                self.send({"op": 1, "d": self.sequence})

            elif opcode == 0:
                self.sequence = int(response["s"])
                optext = response["t"]
                if optext == "READY":
                    ready_time_start = time.time()
                    self.resume_gateway_url = response["d"]["resume_gateway_url"]
                    self.session_id = response["d"]["session_id"]
                    self.clear_ready_vars()
                    time_log_string = "READY event time profile:\n"
                    last_messages = []
                    self.my_id = response["d"]["user"]["id"]
                    # guilds and channels
                    for guild in response["d"]["guilds"]:
                        guild_id = guild["id"]
                        guild_channels = []
                        # channels
                        for channel in guild["channels"]:
                            if channel["type"] in (0, 5):
                                hidden = False   # hidden by default
                            else:
                                hidden = False   # categories cant be hidden
                            guild_channels.append({
                                "id": channel["id"],
                                "type": channel["type"],
                                "name": channel["name"],
                                "topic": channel.get("topic"),
                                "parent_id": channel.get("parent_id"),
                                "position": channel["position"],
                                "permission_overwrites": channel["permission_overwrites"],
                                "hidden": hidden,
                            })
                            # build list of last mesages from each channel
                            if "last_message_id" in channel:
                                last_messages.append({
                                    "message_id": channel["last_message_id"],   # really last message id
                                    "channel_id": channel["id"],
                                })
                        guild_roles = []
                        base_permissions = 0
                        # roles
                        for role in guild["roles"]:
                            if role["id"] == guild_id:
                                base_permissions = role["permissions"]
                            guild_roles.append({
                                "id": role["id"],
                                "name": role["name"],
                                "color": role["color"],
                                "position": role["position"],   # for sorting
                                "hoist": role["hoist"],   # separated from online members
                                "permissions": role["permissions"],
                                # "flags": role["flags"],   # flags=1 - self-assign
                                # "managed": role["managed"],   # for bots
                            })
                        # sort roles
                        guild_roles = sorted(guild_roles, key=lambda x: x.get("position"), reverse=True)
                        guild_roles = sorted(guild_roles, key=lambda x: not bool(x.get("color")))
                        self.roles.append({
                            "guild_id": guild_id,
                            "roles": guild_roles,
                        })
                        self.guilds.append({
                            "guild_id": guild_id,
                            "owned": self.my_id == guild["properties"]["owner_id"],
                            "name": guild["properties"]["name"],
                            "description": guild["properties"]["description"],
                            "member_count": guild["member_count"],
                            "channels": guild_channels,
                            "base_permissions": base_permissions,
                        })
                        # threads
                        threads = []
                        for thread in guild["threads"]:
                            if thread["member"]["flags"] == 3:
                                message_notifications = 0
                            elif thread["member"]["flags"] == 5:
                                message_notifications = 1
                            else:
                                message_notifications = 2
                            threads.append({
                                "id": thread["id"],
                                "type": thread["type"],
                                "owner_id": thread["owner_id"],
                                "name": thread["name"],
                                "locked": thread["thread_metadata"]["locked"],
                                "message_count": thread["message_count"],
                                "timestamp": thread["thread_metadata"]["create_timestamp"],
                                "parent_id": thread["parent_id"],
                                "suppress_everyone": False,   # no config for threads
                                "suppress_roles": False,
                                "message_notifications": message_notifications,
                                "muted": thread["member"]["muted"],
                                "joined": True,
                            })
                            # add threads to list of last mesages from channes
                            if "last_message_id" in thread:
                                last_messages.append({
                                    "message_id": thread["last_message_id"],   # really last message id
                                    "channel_id": thread["id"],
                                })
                        self.threads_buffer.append({
                            "guild_id": guild_id,
                            "threads": threads,
                        })
                    time_log_string += f"    guilds - {round(time.time() - ready_time_start, 3)}s\n"
                    ready_time_mid = time.time()
                    # DM channels
                    for dm in response["d"]["private_channels"]:
                        recipients = []
                        for recipient_id in dm["recipient_ids"]:
                            for user in response["d"]["users"]:
                                if user["id"] == recipient_id:
                                    recipients.append({
                                        "id": recipient_id,
                                        "username": user["username"],
                                        "global_name": user["global_name"],
                                    })
                                    break
                        if "name" in dm:
                            name = dm["name"]
                        else:
                            name = recipients[0]["global_name"]
                        self.dms.append({
                            "id": dm["id"],
                            "type": dm["type"],
                            "recipients": recipients,
                            "name": name,
                            "is_spam": dm.get("is_spam"),
                            "is_request": dm.get("is_message_request"),
                        })
                        self.dms_id.append(dm["id"])
                    time_log_string += f"    DMs - {round(time.time() - ready_time_mid, 3)}s\n"
                    ready_time_mid = time.time()
                    # unread messages and pings
                    for channel in response["d"]["read_state"]["entries"]:
                        # last_message_id in unread_state is actually last_ACKED_message_id
                        if "last_message_id" in channel and "mention_count" in channel:
                            if channel["mention_count"] != 0:
                                self.msg_unseen.append(channel["id"])
                                self.msg_ping.append(channel["id"])
                            else:
                                for last_message in last_messages:
                                    if (
                                        channel["id"] == last_message["channel_id"] and
                                        channel["last_message_id"] != last_message["message_id"]
                                    ):
                                        # channel is unread
                                        self.msg_unseen.append(channel["id"])
                    time_log_string += f"    unread and mentions - {round(time.time() - ready_time_mid, 3)}s\n"
                    ready_time_mid = time.time()
                    # guild and dm setings
                    for guild in response["d"]["user_guild_settings"]["entries"]:
                        if guild["guild_id"]:
                            # find this guild in self.guilds
                            for guild_num, guild_g in enumerate(self.guilds):
                                if guild_g["guild_id"] == guild["guild_id"]:
                                    break
                            self.guilds[guild_num].update({
                                "suppress_everyone": guild["suppress_everyone"],
                                "suppress_roles": guild["suppress_roles"],
                                "message_notifications": guild["message_notifications"],
                                "muted": guild["muted"],
                            })
                            for channel in guild["channel_overrides"]:
                                found = False
                                for channel_num, channel_g in enumerate(self.guilds[guild_num]["channels"]):
                                    if channel_g["id"] == channel["channel_id"]:
                                        found = True
                                        break
                                if found:
                                    if channel_g["type"] in (0, 5):
                                        flags = int(channel.get("flags", 0))
                                        hidden = not perms.decode_flag(flags, 12)
                                    else:   # categories cant be hidden
                                        hidden = False
                                    self.guilds[guild_num]["channels"][channel_num].update({
                                        "message_notifications": channel["message_notifications"],
                                        "muted": channel["muted"],
                                        "hidden": hidden,
                                        "collapsed": channel["collapsed"],
                                    })
                        else:
                            for dm in guild["channel_overrides"]:
                                for dm_num, dm_g in enumerate(self.dms):
                                    if dm_g["id"] == dm["channel_id"]:
                                        break
                                self.dms[dm_num].update({
                                    "message_notifications": dm["message_notifications"],
                                    "muted": dm["muted"],
                                })
                    time_log_string += f"    channel settings - {round(time.time() - ready_time_mid, 3)}s\n"
                    ready_time_mid = time.time()
                    for user in response["d"]["relationships"]:
                        if user["type"] == 2 or user.get("user_ignored"):
                            self.blocked.append(user["user_id"])
                    time_log_string += f"    blocked users - {round(time.time() - ready_time_mid, 3)}s\n"
                    ready_time_mid = time.time()
                    # get proto
                    decoded = PreloadedUserSettings.FromString(base64.b64decode(response["d"]["user_settings_proto"]))
                    self.user_settings_proto = json.loads(MessageToJson(decoded))
                    time_log_string += f"    protobuf - {round(time.time() - ready_time_mid, 3)}s\n"
                    ready_time_mid = time.time()
                    # get my roles
                    for num, guild in enumerate(response["d"]["merged_members"]):
                        guild_id = self.guilds[num]["guild_id"]
                        roles = []
                        for member in guild:
                            if member["user_id"] == self.my_id:
                                roles = member["roles"]
                        self.my_roles.append({
                            "guild_id": guild_id,
                            "roles": roles,
                        })
                    time_log_string += f"    roles - {round(time.time() - ready_time_mid, 3)}s\n"
                    ready_time_mid = time.time()
                    # write debug data
                    if logger.getEffectiveLevel() == logging.DEBUG:
                        debug.save_json(debug.anonymize_guilds(self.guilds), "guilds.json")
                    # debug_guilds_tree
                    # self.guilds = debug.load_json("guilds.json")
                    # blocked users
                    time_log_string += f"    debug data - {round(time.time() - ready_time_mid, 3)}s\n"
                    # READY is huge so lets save some memory
                    del (guild, guild_channels, role, guild_roles, last_messages)
                    self.ready = True
                    time_log_string += f"    total - {round(time.time() - ready_time_start, 3)}s"
                    logger.debug(time_log_string)
                    del time_log_string

                elif optext == "READY_SUPPLEMENTAL":
                    for guild in response["d"]["merged_presences"]["guilds"]:
                        for user in guild:
                            custom_status = None
                            activities = []
                            for activity in user["activities"]:
                                if activity["type"] == 4:
                                    custom_status = activity.get("state", "")
                                elif activity["type"] == 0:
                                    assets = activity.get("assets", {})
                                    activities.append({
                                        "name": activity["name"],
                                        "state": activity.get("state"),
                                        "details": activity.get("details"),
                                        "small_text": assets.get("small_text"),
                                        "large_text": assets.get("large_text"),
                                    })
                            self.activities.append({
                                "id": user["user_id"],
                                "status": user["status"],
                                "custom_status": custom_status,
                                "activities": activities,
                            })
                    for user in response["d"]["merged_presences"]["friends"]:
                        custom_status = None
                        activities = []
                        for activity in user["activities"]:
                            if activity["type"] == 4:
                                custom_status = activity["state"]
                            elif activity["type"] == 0:
                                assets = activity.get("assets", {})
                                activities.append({
                                    "name": activity["name"],
                                    "state": activity.get("state"),
                                    "details": activity.get("details"),
                                    "small_text": assets.get("small_text"),
                                    "large_text": assets.get("large_text"),
                                })
                        self.activities.append({
                            "id": user["user_id"],
                            "status": user["status"],
                            "custom_status": custom_status,
                            "activities": activities,
                        })
                    del (guild)   # this is large dict so lets save some memory
                    self.activities_changed = True

                elif optext == "SESSIONS_REPLACE":
                    # received when new client is connected
                    custom_status = None
                    custom_status_emoji = None
                    activities = []
                    for activity in response["d"][0]["activities"]:
                        if activity["type"] == 4:
                            custom_status = activity["state"]
                            custom_status_emoji = {
                                "id": activity["emoji"].get("id"),
                                "name": activity["emoji"].get("name"),
                                "animated": activity["emoji"].get("animated", False),
                            }
                        elif activity["type"] in (0, 2):
                            if "assets" in activity:
                                small_text = activity["assets"].get("small_text")
                                large_text = activity["assets"].get("large_text")
                            else:
                                small_text = None
                                large_text = None
                            activities.append({
                                "name": activity["name"],
                                "state": activity.get("state", ""),
                                "details": activity.get("details", ""),
                                "small_text": small_text,
                                "large_text": large_text,
                            })
                    self.my_status = {
                        "status": response["d"][0]["status"],
                        "custom_status": custom_status,
                        "custom_status_emoji": custom_status_emoji,
                        "activities": activities,
                    }
                    self.status_changed = True

                elif optext == "PRESENCE_UPDATE":
                    # received when friend/DM user changes presence state (online/rich/custom)
                    user_id = response["d"]["user"]["id"]
                    custom_status = None
                    activities = []
                    for activity in response["d"]["activities"]:
                        if activity["type"] == 4:
                            custom_status = activity["state"]
                        elif activity["type"] == 0:
                            if "assets" in activity:
                                small_text =  activity["assets"].get("small_text")
                                large_text =  activity["assets"].get("large_text")
                            else:
                                small_text = None
                                large_text = None
                            activities.append({
                                "name": activity["name"],
                                "state": activity.get( "state"),
                                "details": activity.get("details"),
                                "small_text": small_text,
                                "large_text": large_text,
                            })
                    for num, user in enumerate(self.activities):
                        if user["id"] == user_id:
                            self.activities[num] = {
                                "id": user_id,
                                "status": response["d"]["status"],
                                "custom_status": custom_status,
                                "activities": activities,
                            }
                            break
                    else:
                        self.activities.append({
                            "id": response["d"]["user"]["id"],
                            "status": response["d"]["status"],
                            "custom_status": custom_status,
                            "activities": activities,
                        })
                    self.activities_changed = True

                elif optext == "TYPING_START":
                    # received when user in currently subscribed guild channel starts typing
                    if "member" in response["d"]:
                        username = response["d"]["member"]["user"]["username"]
                        global_name = response["d"]["member"]["user"]["global_name"]
                        nick = response["d"]["member"]["user"].get("nick")
                    else:
                        username = None
                        global_name = None
                        nick = None
                    self.typing_buffer.append({
                        "user_id": response["d"]["user_id"],
                        "timestamp": response["d"]["timestamp"],
                        "channel_id": response["d"]["channel_id"],
                        "username": username,
                        "global_name": global_name,
                        "nick": nick,
                    })

                elif optext == "MESSAGE_CREATE":
                    if "content" in response["d"]:
                        if "referenced_message" in response["d"]:
                            reference_nick = None
                            for mention in response["d"]["mentions"]:
                                if mention["id"] == response["d"]["referenced_message"]["id"]:
                                    if "member" in mention:
                                        reference_nick = mention["member"]["nick"]
                            ref_mentions = []
                            if response["d"]["referenced_message"]["mentions"]:
                                for ref_mention in response["d"]["referenced_message"]["mentions"]:
                                    ref_mentions.append({
                                        "username": ref_mention["username"],
                                        "id": ref_mention["id"],
                                    })
                            if "message_snapshots" in response["d"]["referenced_message"]:
                                forwarded = response["d"]["referenced_message"]["message_snapshots"][0]["message"]
                                # additional text with forwarded message is sent separately
                                response["d"]["referenced_message"]["content"] = f"[Forwarded]: {forwarded.get("content")}"
                                response["d"]["referenced_message"]["embeds"] = forwarded.get("embeds")
                                response["d"]["referenced_message"]["attachments"] = forwarded.get("attachments")
                            reference_embeds = []
                            for embed in response["d"]["referenced_message"]["embeds"]:
                                content = embed.get("url")
                                if "video" in embed and "url" in embed["video"]:
                                    content = embed["video"]["url"]
                                elif "image" in embed and "url" in embed["image"]:
                                    content = embed["image"]["url"]
                                elif "fields" in embed:
                                    content = f"{embed["fields"][0]["name"]}\n{embed["fields"][0]["value"]}"
                                else:
                                    content = None
                                if content:
                                    reference_embeds.append({
                                        "type": embed["type"],
                                        "name": None,
                                        "url": content,
                                    })
                            for attachment in response["d"]["referenced_message"]["attachments"]:
                                reference_embeds.append({
                                    "type": attachment.get("content_type", "unknown"),
                                    "name": attachment["filename"],
                                    "url": attachment["url"],
                                })   # keep attachments in same place as embeds
                            reference = {
                                "id": response["d"]["referenced_message"]["id"],
                                "timestamp": response["d"]["referenced_message"]["timestamp"],
                                "content": response["d"]["referenced_message"]["content"],
                                "mentions": ref_mentions,
                                "user_id": response["d"]["referenced_message"]["author"]["id"],
                                "username": response["d"]["referenced_message"]["author"]["username"],
                                "global_name": response["d"]["referenced_message"]["author"]["global_name"],
                                "nick": reference_nick,
                                "embeds": reference_embeds,
                                "stickers": response["d"]["referenced_message"].get("sticker_items", []),
                            }
                        else:
                            reference = None
                        nick = None
                        if "member" in response["d"]:
                            nick = response["d"]["member"]["nick"]
                        embeds = []
                        if "message_snapshots" in response["d"]:
                            forwarded = response["d"]["message_snapshots"][0]["message"]
                            # additional text with forwarded message is sent separately
                            response["d"]["content"] = f"[Forwarded]: {forwarded.get("content")}"
                            response["d"]["embeds"] = forwarded.get("embeds")
                            response["d"]["attachments"] = forwarded.get("attachments")
                        for embed in response["d"]["embeds"]:
                            content = embed.get("url")
                            if "video" in embed and "url" in embed["video"]:
                                content = embed["video"]["url"]
                            elif "image" in embed and "url" in embed["image"]:
                                content = embed["image"]["url"]
                            elif "fields" in embed:
                                content = ""
                                if "url" in embed:
                                    content = embed["url"]
                                for field in embed["fields"]:
                                    content = content + "\n" + field["name"] + "\n" + field["value"] + "\n"
                                content = content.strip("\n")
                            else:
                                content = None
                            if content and content not in response["d"]["content"]:
                                embeds.append({
                                    "type": embed["type"],
                                    "name": None,
                                    "url": content,
                                })
                        for attachment in response["d"]["attachments"]:
                            embeds.append({
                                "type": attachment.get("content_type", "unknown"),
                                "name": attachment["filename"],
                                "url": attachment["url"],
                            })   # keep attachments in same place as embeds
                        mentions = []
                        if response["d"]["mentions"]:
                            for mention in response["d"]["mentions"]:
                                mentions.append({
                                    "username": mention["username"],
                                    "id": mention["id"],
                                })
                        if "member" in response["d"] and "roles" in response["d"]["member"]:
                            if response["d"]["member"]["roles"]:
                                # for now, saving only first role, used for username color
                                self.add_member_roles(
                                    guild_id,
                                    response["d"]["author"]["id"],
                                    response["d"]["member"]["roles"],
                                )
                        self.messages_buffer.append({
                            "op": "MESSAGE_CREATE",
                            "d": {
                                "id": response["d"]["id"],
                                "channel_id": response["d"]["channel_id"],
                                "guild_id": response["d"].get("guild_id"),
                                "timestamp": response["d"]["timestamp"],
                                "edited": False,
                                "content": response["d"]["content"],
                                "mentions": mentions,
                                "mention_roles": response["d"]["mention_roles"],
                                "mention_everyone": response["d"]["mention_everyone"],
                                "user_id": response["d"]["author"]["id"],
                                "username": response["d"]["author"]["username"],
                                "global_name": response["d"]["author"]["global_name"],
                                "nick": nick,
                                "referenced_message": reference,
                                "reactions": [],
                                "embeds": embeds,
                                "stickers": response["d"].get("sticker_items", []),   # {name, id, format_type}
                            },
                        })

                elif optext == "MESSAGE_UPDATE":
                    embeds = []
                    for embed in response["d"]["embeds"]:
                        content = embed.get("url")
                        if "video" in embed and "url" in embed["video"]:
                            content = embed["video"]["url"]
                        elif "image" in embed and "url" in embed["image"]:
                            content = embed["image"]["url"]
                        elif "fields" in embed:
                            content = ""
                            if "url" in embed:
                                content = embed["url"]
                            for field in embed["fields"]:
                                content = content + "\n" + field["name"] + "\n" + field["value"] + "\n"
                            content = content.strip("\n")
                        else:
                            content = None
                        if content and content not in response["d"]["content"]:
                            embeds.append({
                                "type": embed["type"],
                                "name": None,
                                "url": content,
                            })
                    for attachment in response["d"]["attachments"]:
                        embeds.append({
                            "type": attachment.get("content_type", "unknown"),
                            "name": attachment["filename"],
                            "url": attachment["url"],
                        })   # keep attachments in same place as embeds
                    mentions = []
                    if response["d"]["mentions"]:
                        for mention in response["d"]["mentions"]:
                            mentions.append({
                                "username": mention["username"],
                                "id": mention["id"],
                            })
                    data = {
                        "id": response["d"]["id"],
                        "channel_id": response["d"]["channel_id"],
                        "guild_id": response["d"].get("guild_id"),
                        "edited": True,
                        "content": response["d"]["content"],
                        "mentions": mentions,
                        "mention_roles": response["d"]["mention_roles"],
                        "mention_everyone": response["d"]["mention_everyone"],
                        "embeds": embeds,
                        "stickers": response["d"].get("sticker_items", []),
                    }
                    self.messages_buffer.append({
                        "op": "MESSAGE_UPDATE",
                        "d": data,
                    })

                elif optext == "MESSAGE_DELETE":
                    data = {
                        "id": response["d"]["id"],
                        "channel_id": response["d"]["channel_id"],
                        "guild_id": response["d"].get("guild_id"),
                    }
                    self.messages_buffer.append({
                        "op": "MESSAGE_DELETE",
                        "d": data,
                    })

                elif optext == "MESSAGE_REACTION_ADD":
                    if "member" in response["d"]:
                        user_id = response["d"]["member"]["user"]["id"]
                        username = response["d"]["member"]["user"]["username"]
                        global_name = response["d"]["member"]["user"]["global_name"]
                        nick = response["d"]["member"]["user"].get("nick")
                    else:
                        user_id = response["d"]["user_id"]
                        username = None
                        global_name = None
                        nick = None
                    data = {
                        "id": response["d"]["message_id"],
                        "channel_id": response["d"]["channel_id"],
                        "guild_id": response["d"].get("guild_id"),
                        "emoji": response["d"]["emoji"]["name"],
                        "emoji_id": response["d"]["emoji"]["id"],
                        "user_id": user_id,
                        "username": username,
                        "global_name": global_name,
                        "nick": nick,
                    }
                    self.messages_buffer.append({
                        "op": "MESSAGE_REACTION_ADD",
                        "d": data,
                    })

                elif optext == "MESSAGE_REACTION_ADD_MANY":
                    channel_id = response["d"]["channel_id"]
                    guild_id = response["d"].get("guild_id")
                    message_id = response["d"]["message_id"]
                    for reaction in response["d"]["reactions"]:
                        for user_id in reaction["users"]:
                            data = {
                                "id": message_id,
                                "channel_id": channel_id,
                                "guild_id": guild_id,
                                "emoji": reaction["emoji"]["name"],
                                "emoji_id": reaction["emoji"]["id"],
                                "user_id": user_id,
                                "username": None,
                                "global_name": None,
                                "nick": None,
                            }
                            self.messages_buffer.append({
                                "op": "MESSAGE_REACTION_ADD",
                                "d": data,
                            })

                elif optext == "MESSAGE_REACTION_REMOVE":
                    data = {
                        "id": response["d"]["message_id"],
                        "channel_id": response["d"]["channel_id"],
                        "guild_id": response["d"].get("guild_id"),
                        "emoji": response["d"]["emoji"]["name"],
                        "emoji_id": response["d"]["emoji"]["id"],
                        "user_id": response["d"]["user_id"],
                    }
                    self.messages_buffer.append({
                        "op": "MESSAGE_REACTION_REMOVE",
                        "d": data,
                    })

                elif optext == "CONVERSATION_SUMMARY_UPDATE":
                    # received when new conversation summary is generated
                    for summary in response["d"]["summaries"]:
                        self.summaries_buffer.append({
                            "channel_id": response["d"]["channel_id"],
                            "guild_id": response["d"].get("guild_id"),
                            "topic": summary["topic"],
                            "description": summary["summ_short"],

                        })

                elif optext == "MESSAGE_ACK":
                    # received when other client ACKs messages
                    self.msg_ack_buffer.append({
                        "message_id": response["d"]["message_id"],
                        "channel_id": response["d"]["channel_id"],
                    })

                elif optext == "GUILD_MEMBERS_CHUNK":
                    # received when requesting members (op 8)
                    guild_id = response["d"]["guild_id"]
                    members = response["d"]["members"]
                    for member in members:
                        if "roles" in member and member["roles"]:
                            # for now, saving only first role, used for username color
                            self.add_member_roles(
                                guild_id,
                                member["user"]["id"],
                                member["roles"],
                            )

                elif optext == "THREAD_LIST_SYNC":
                    threads = []
                    for thread in response["d"]["threads"]:
                        threads.append({
                            "id": thread["id"],
                            "type": thread["type"],
                            "owner_id": thread["owner_id"],
                            "name": thread["name"],
                            "locked": thread["thread_metadata"]["locked"],
                            "message_count": thread["message_count"],
                            "timestamp": thread["thread_metadata"]["create_timestamp"],
                            "parent_id": thread["parent_id"],
                            "suppress_everyone": False,   # no config for threads
                            "suppress_roles": False,
                            "message_notifications": None,
                            "muted": False,
                            "joined": False,
                        })
                    self.threads_buffer.append({
                        "guild_id": guild_id,
                        "threads": threads,
                    })

                elif optext == "THREAD_UPDATE":
                    self.threads_buffer.append({
                        "guild_id": guild_id,
                        "threads": [{
                            "id": response["d"]["id"],
                            "type": response["d"]["type"],
                            "owner_id": response["d"]["owner_id"],
                            "name": response["d"]["name"],
                            "locked": response["d"]["thread_metadata"]["locked"],
                            "message_count": response["d"]["message_count"],
                            "timestamp": response["d"]["thread_metadata"]["create_timestamp"],
                            "parent_id": response["d"]["parent_id"],
                            "suppress_everyone": False,   # no config for threads
                            "suppress_roles": False,
                            "message_notifications": None,
                            "muted": False,
                            "joined": False,
                        }],
                    })

            elif opcode == 7:
                logger.info("Discord requested reconnect")
                break
            # debug_events
            # if "t" in response and response["t"]:
            #     debug.save_json(response, f"{response["t"]}.json", False)
        self.state = 0
        logger.info("Receiver stopped")
        self.reconnect_requested = True
        self.heartbeat_running = False


    def send_heartbeat(self):
        """Send heatbeat to gateway, if response is not received, triggers reconnect, should be run in a thread"""
        logger.info(f"Heartbeater started, interval={self.heartbeat_interval/1000}")
        self.heartbeat_running = True
        self.heartbeat_received = True
        # wait for ready event for some time
        sleep_time = 0
        while not self.ready:
            if sleep_time >= self.heartbeat_interval / 100:
                logger.error("Ready event could not be processed in time, probably because of too many servers. Exiting...")
                raise SystemExit("Ready event could not be processed in time, probably because of too many servers. Exiting...")
            time.sleep(0.5)
            sleep_time += 5
        heartbeat_interval_rand = self.heartbeat_interval * (0.8 - 0.6 * random.random()) / 1000
        heartbeat_sent_time = time.time()
        while self.run and not self.wait and self.heartbeat_running:
            if time.time() - heartbeat_sent_time >= heartbeat_interval_rand:
                self.send({"op": 1, "d": self.sequence})
                heartbeat_sent_time = time.time()
                logger.debug("Heartbeat sent")
                if not self.heartbeat_received:
                    logger.warn("Heartbeat reply not received")
                    break
                self.heartbeat_received = False
                heartbeat_interval_rand = self.heartbeat_interval * (0.8 - 0.6 * random.random()) / 1000
            # sleep(heartbeat_interval * jitter), but jitter is limited to (0.1 - 0.9)
            # in this time heartbeat ack should be received from discord
            time.sleep(0.5)
        self.state = 0
        logger.info("Heartbeater stopped")
        self.reconnect_requested = True


    def authenticate(self):
        """Authenticate client with discord gateway"""
        if sys.platform == "linux":
            op_sys = "linux"
        elif sys.platform == "win32":
            op_sys = "windows"
        else:
            op_sys = "mac"
        payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 30717,
                "properties": {
                    "os": op_sys,
                    "browser": CLIENT_NAME,
                    "device": CLIENT_NAME,
                },
                "presence": {
                    "activities": [],
                    "status": "online",
                    "since": None,
                    "afk": False,
                },
            },
        }
        self.send(payload)


    def resume(self):
        """
        Tries to resume discord gateway session on url provided by Discord in READY event.
        Returns gateway response code, 9 means resumming has failed
        """
        self.ws.close(timeout=0)   # this will stop receiver
        time.sleep(1)   # so receiver ends before opening new socket
        reset_inflator()   # otherwise decompression wont work
        self.ws = websocket.WebSocket()
        self.ws.connect(self.resume_gateway_url + "/?v=9&encoding=json&compress=zlib-stream")
        _ = zlib_decompress(self.ws.recv())
        logger.info("Trying to resume connection")
        payload = {"op": 6, "d": {"token": self.token, "session_id": self.session_id, "sequence": self.sequence}}
        self.send(payload)
        try:
            return json.loads(zlib_decompress(self.ws.recv()))["op"]
        except json.decoder.JSONDecodeError:
            return 9


    def reconnect(self):
        """Try to resume session, if failed, create new one"""
        if not self.wait:
            self.state = 2
            logger.info("Trying to reconnect")
        try:
            code = self.resume()
            if code == 9:
                self.ws.close(timeout=0)   # this will stop receiver
                time.sleep(1)   # so receiver ends before opening new socket
                reset_inflator()   # otherwise decompression wont work
                self.ready = False   # will receive new ready event
                self.ws = websocket.WebSocket()
                self.ws.connect(self.gateway_url + "/?v=9&encoding=json&compress=zlib-stream")
                self.authenticate()
                logger.info("restarting connection")
            self.wait = False
            # restarting threads
            if not self.receiver_thread.is_alive():
                self.receiver_thread = threading.Thread(target=self.receiver, daemon=True, args=())
                self.receiver_thread.start()
            if not self.heartbeat_thread.is_alive():
                self.heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True, args=())
                self.heartbeat_thread.start()
            self.state = 1
            logger.info("Connection restart done")
        except websocket._exceptions.WebSocketAddressException:
            if not self.wait:   # if not running from wait_oline
                logger.warn("No internet connection")
                self.ws.close()
                threading.Thread(target=self.wait_online, daemon=True, args=()).start()


    def wait_online(self):
        """Wait for network, try to recconect every 5s"""
        self.wait = True
        while self.run and self.wait:
            self.reconnect_requested = True
            time.sleep(5)


    def get_state(self):
        """
        Return current state of gateway:
        0 - gateway is disconnected
        1 - gateway is connected
        2 - gateway is reconecting
        """
        return self.state


    def update_presence(self, status, custom_status=None, custom_status_emoji=None, rpc=None):
        """Update client status. Statuses: 'online', 'idle', 'dnd', 'invisible', 'offline'"""
        activities = []
        if custom_status:
            activities.append({
                "name": "Custom Status",
                "type": 4,
                "state": custom_status,
            })
            if custom_status_emoji:
                activities[0]["emoji"] = custom_status_emoji
        if rpc:
            for activity in rpc:
                activities.append(activity)
        payload = {
            "op": 3,
            "d": {
                "status": status,
                "afk": "false",
                "since": 0,
                "activities": activities,
            },
        }
        self.send(payload)
        logger.debug("Updated presence")


    def subscribe(self, channel_id, guild_id):
        """Subscribe to the channel to receive "typing" events from gateway for specified channel"""
        if guild_id:
            # when subscribing, add channel to list of subscribed channels
            # then send whole list
            # if channel is already in list send nothing
            # when subscribing to guild for the first time, send extra config
            done = False
            for num, guild in enumerate(self.subscribed):
                if guild["guild_id"] == guild_id:
                    if channel_id in guild["channels"]:
                        logger.debug("Already subscribed to the channel")
                    else:
                        logger.debug("Adding channel to subscribed")
                        guild["channels"].append(channel_id)
                        channels = {}
                        for channel in guild["channels"]:
                            channels[channel] = [[0, 99]]   # what is [[0, 99]]?
                        payload = {
                            "op": 37,   # changed in gateway v10
                            "d": {
                                "subscriptions": {
                                    guild_id: {
                                        "channels": channels,
                                    },
                                },
                            },
                        }
                        self.send(payload)
                    done = True
            if not done:
                logger.debug("Adding guild to subscribed")
                self.subscribed.append({
                    "guild_id": guild_id,
                    "channels": [channel_id],
                })
                payload = {
                    "op": 37,   # changed in gateway v10
                    "d": {
                        "subscriptions": {
                            guild_id: {
                                "typing": True,
                                "activities": False,
                                "threads": True,
                                "channels": {
                                    channel_id: [[0, 99]],
                                },
                            },
                        },
                    },
                }
                self.send(payload)
        else:
            payload = {
                "op": 13,
                "d": {
                    "channel_id": channel_id,
                },
            }
            self.send(payload)
            logger.debug("Subscribed to a DM")


    def request_members(self, guild_id, members):
        """
        Request update chunk for specified members in this guild.
        GUILD_MEMBERS_CHUNK event will be received after this.
        """
        if members:
            payload = {
                "op": 8,
                "d": {
                    "guild_id": [guild_id],
                    "query": None,
                    "limit": None,
                    "presences": False,
                    "user_ids": members,
                },
            }
            self.send(payload)
            logger.debug("Requesting guild members chunk")


    def get_ready(self):
        """Return wether gateway processed entire READY event"""
        return self.ready


    def get_unseen(self):
        """Get list of channels with unseen messages ater connecting"""
        return self.msg_unseen


    def get_pings(self):
        """Get list of channels with mentions ater connecting"""
        return self.msg_ping


    def get_dms(self):
        """
        Get list of open DMs with their recipient
        DM types:
        1 - single person DM
        3 - group DM (name is not None)
        """
        return self.dms, self.dms_id

    def get_guilds(self):
        """
        Get list of guilds and channels with their metadata, updated only when reconnecting
        Channel types:
        0 - text
        2 - voice
        4 - category
        5 - announcements
        11/12 - thread
        15 - forum (contains only threads)
        message_notifications:
        0 - all messages
        1 - only mentions
        2 - nothing
        3 - category defaults
        """
        return self.guilds


    def get_roles(self):
        """Get list of roles for all guilds with their metadata, updated only when reconnecting"""
        return self.roles


    def get_blocked(self):
        """Get list of blocked user ids"""
        return self.blocked


    def get_settings_proto(self):
        """Get account settings, only proto 1"""
        return self.user_settings_proto


    def get_my_roles(self):
        """Get list of my roles for all servers"""
        return self.my_roles


    def get_my_id(self):
        """Get my discord user ID"""
        return self.my_id


    def get_my_status(self):
        """Get my activity status, including rich presence, updated regularly"""
        if self.status_changed:
            self.status_changed = False
            return self.my_status
        return None


    def get_activities(self):
        """Get list of friends with their activity status, including rich presence, updated regularly"""
        if self.activities_changed:
            self.activities_changed = False
            return self.activities
        return None


    def get_member_roles(self):
        """Get member roles, updated regularly."""
        if self.roles_changed:
            self.roles_changed = False
            return self.member_roles
        return None


    # all following "get_*" work like this:
    # internally:
    #    get events and append them to list
    #    when get_messages() is called, remove event from list and return it
    # externally:
    #    in main get initial values
    #    thread in app runs get_*() functions:
    #    if returned value:
    #       if value is for current channel:
    #           update it in initial message list
    #       run it again,
    #    if returned None:
    #       continue to other code in main


    def get_messages(self):
        """
        Get message CREATE, EDIT, DELETE and ACK events for every guild and channel.
        Returns 1 by 1 event as an update for list of messages.
        """
        if len(self.messages_buffer) == 0:
            return None
        return self.messages_buffer.pop(0)


    def get_typing(self):
        """
        Get typing accross guilds.
        Returns 1 by 1 event as an update for list of typing.
        """
        if len(self.typing_buffer) == 0:
            return None
        return self.typing_buffer.pop(0)


    def get_summaries(self):
        """
        Get summaries.
        Returns 1 by 1 event as an update for list of summaries.
        """
        if len(self.summaries_buffer) == 0:
            return None
        return self.summaries_buffer.pop(0)


    def get_message_ack(self):
        """
        Get messages seen by other clients.
        Returns 1 by 1 ack event.
        """
        if len(self.msg_ack_buffer) == 0:
            return None
        return self.msg_ack_buffer.pop(0)


    def get_threads(self):
        """
        Get threads.
        Returns 1 by 1 update for list of threads.
        """
        if len(self.threads_buffer) == 0:
            return None
        return self.threads_buffer.pop(0)
