import importlib.util
import logging
import os
import re
import shutil
import sys
import threading
import time
import webbrowser

import emoji

from endcord import (
    color,
    debug,
    discord,
    downloader,
    formatter,
    gateway,
    peripherals,
    perms,
    rpc,
    tui,
)

support_media = (
    importlib.util.find_spec("PIL") is not None and
    importlib.util.find_spec("av") is not None and
    importlib.util.find_spec("pyaudio") is not None and
    importlib.util.find_spec("numpy") is not None
)
if support_media:
    from endcord import media

logger = logging.getLogger(__name__)
APP_NAME = "endcord"
MESSAGE_UPDATE_ELEMENTS = ("id", "edited", "content", "mentions", "mention_roles", "mention_everyone", "embeds")
MEDIA_EMBEDS = ("image", "gifv", "video", "rich")
MSG_NUM = 50   # number of messages downloaded when switching channel
MSG_MIN = 3   # minimum number of messages that must be sent in official client

download = downloader.Downloader()
match_url = re.compile(r"(https?:\/\/\w+(\.\w+)+[^\r\n\t\f\v )\]>]*)")


class Endcord:
    """Main app class"""

    def __init__(self, screen, config, keybindings):
        self.screen = screen
        self.config = config

        # load often used values from config
        self.enable_rpc = config["rpc"] and sys.platform == "linux"
        self.limit_chat_buffer = max(min(config["limit_chat_buffer"], 1000), 50)
        self.limit_typing = max(config["limit_typing_string"], 25)
        self.send_my_typing = config["send_typing"]
        self.ack_throttling = max(config["ack_throttling"], 3)
        self.format_title_line_l = config["format_title_line_l"]
        self.format_title_line_r = config["format_title_line_r"]
        self.format_status_line_l = config["format_status_line_l"]
        self.format_status_line_r = config["format_status_line_r"]
        self.format_title_tree = config["format_title_tree"]
        self.reply_mention = config["reply_mention"]
        self.cache_typed = config["cache_typed"]
        self.enable_notifications = config["desktop_notifications"]
        self.notification_sound = config["linux_notification_sound"]
        self.hide_spam = config["hide_spam"]
        self.keep_deleted = config["keep_deleted"]
        self.deleted_cache_limit = config["deleted_cache_limit"]
        self.ping_this_channel = config["notification_in_active"]
        self.username_role_colors = config["username_role_colors"]
        downloads_path = config["downloads_path"]
        if not downloads_path:
            downloads_path = peripherals.downloads_path
        self.downloads_path = os.path.expanduser(downloads_path)
        self.tenor_gif_type = config["tenor_gif_type"]
        self.colors = peripherals.extract_colors(config)
        self.colors_formatted = peripherals.extract_colors_formatted(config)
        self.default_msg_color = self.colors_formatted[0][0][:]
        self.default_msg_alt_color = self.colors[1]
        self.cached_downloads = []
        self.color_cache = []

        # variables
        self.run = False
        self.active_channel = {
            "guild_id": None,
            "channel_id": None,
            "guild_name": None,
            "channel_name": None,
        }
        self.guilds = []
        self.all_roles = []
        self.current_roles = []
        self.current_channels = []
        self.current_channel = {}
        self.summaries = []
        self.input_store = []
        self.running_tasks = []

        # initialize stuff
        self.discord = discord.Discord(config["token"])
        self.gateway = gateway.Gateway(config["token"])
        self.tui = tui.TUI(self.screen, self.config, keybindings)
        self.colors = self.tui.init_colors(self.colors)
        self.colors_formatted = self.tui.init_colors_formatted(self.colors_formatted, self.default_msg_alt_color)
        self.tui.update_chat(["Connecting to Discord"], [[[self.colors[0]]]] * 1)
        self.tui.update_status_line("CONNECTING")
        self.my_id = self.discord.get_my_id()
        self.my_user_data = self.discord.get_user(self.my_id, extra=True)
        self.reset()
        self.gateway.connect()
        self.gateway_state = self.gateway.get_state()
        self.chat_dim, self.tree_dim, _  = self.tui.get_dimensions()
        self.state = {
            "last_guild_id": None,
            "last_channel_id": None,
            "collapsed": [],
        }
        self.tree = []
        self.tree_format = []
        self.tree_metadata = []
        self.my_roles = []
        self.deleted_cache = []
        self.reset_actions()
        # threading.Thread(target=self.profiling_auto_exit, daemon=True).start()
        self.main()


    def profiling_auto_exit(self):
        """Thread that waits then exits cleanly, so profiler (vprof) can process data"""
        time.sleep(20)
        self.run = False


    def reset(self):
        """Reset stored data from discord, should be run on startup and reconnect"""
        self.messages = []
        self.chat = []
        self.chat_format = []
        self.unseen_scrolled = False
        self.chat_indexes = []
        self.update_prompt()
        self.typing = []
        self.unseen = []
        self.pings = []
        self.notifications = []
        self.typing_sent = int(time.time())
        self.sent_ack_time = time.time()
        self.pending_ack = False
        self.last_message_id = 0
        self.my_rpc = []
        self.chat_end = False
        download.cancel()
        self.download_threads = []
        self.upload_threads = []
        self.ready_attachments = []
        self.selected_attachment = 0
        self.member_roles = []
        self.current_member_roles = []
        self.disable_sending = False


    def reconnect(self):
        """Fetch updated data from gateway and rebuild chat after reconnecting"""
        self.add_running_task("Reconnecting", 1)
        self.reset()
        self.guilds = self.gateway.get_guilds()
        # not initializing role colors again to avoid issues with media colors
        self.dms, self.dms_id = self.gateway.get_dms()
        if self.hide_spam:
            for dm in self.dms:
                if dm["is_spam"]:
                    self.dms_id.remove(dm["id"])
                    self.dms.remove(dm)
        self.pings = []
        for channel_id in self.gateway.get_pings():
            self.pings.append({
                "channel_id": channel_id,
                "message_id": None,
            })

        self.unseen = []
        for channel_id in self.gateway.get_unseen():
            guild_id = None
            for guild in self.guilds:
                for channel in guild["channels"]:
                    if channel["id"] == channel_id:
                        guild_id = guild["guild_id"]
                if guild_id:
                    break
            self.unseen.append({
                "channel_id": channel_id,
                "guild_id": guild_id,
            })
        self.blocked = self.gateway.get_blocked()
        self.current_roles = []   # dm has no roles
        for roles in self.all_roles:
            if roles["guild_id"] == self.active_channel["guild_id"]:
                self.current_roles = roles["roles"]
                break
        self.select_current_member_roles()
        self.my_roles = self.gateway.get_my_roles()
        self.current_my_roles = []   # user has no roles in dm
        for roles in self.my_roles:
            if roles["guild_id"] == self.active_channel["guild_id"]:
                self.current_my_roles = roles["roles"]
                break
        self.compute_permissions()
        self.current_channels = []   # dm has no multiple channels
        for guild_channels in self.guilds:
            if guild_channels["guild_id"] == self.active_channel["guild_id"]:
                self.current_channels = guild_channels["channels"]
                break
        self.current_channel = {}
        for channel in self.current_channels:
            if channel["id"] == self.active_channel["channel_id"]:
                self.current_channel = channel
                break
        self.gateway.update_presence(
            self.my_status["status"],
            custom_status=self.my_status["custom_status"],
            custom_status_emoji=self.my_status["custom_status_emoji"],
            rpc=self.my_rpc,
        )

        self.messages =self.get_messages_with_members()
        if self.messages:
            self.last_message_id = self.messages[0]["id"]

        self.typing = []
        self.chat_end = False
        self.gateway.subscribe(self.active_channel["channel_id"], self.active_channel["guild_id"])
        self.update_chat(keep_selected=False)
        self.update_tree()

        self.remove_running_task("Reconnecting", 1)
        logger.info("Reconnect complete")


    def switch_channel(self, channel_id, channel_name, guild_id, guild_name):
        """
        All that should be done when switching channel.
        If it is DM, guild_id and guild_name should be None.
        """

        # dont switch when offline
        if self.my_status["client_state"] in ("OFFLINE", "connecting"):
            return

        # save deleted
        if self.keep_deleted:
            self.cache_deleted()

        # update active channel
        self.active_channel["guild_id"] = guild_id
        self.active_channel["guild_name"] = guild_name
        self.active_channel["channel_id"] = channel_id
        self.active_channel["channel_name"] = channel_name
        self.add_running_task("Switching channel", 1)

        # fetch messages
        self.messages = self.get_messages_with_members(num=MSG_NUM)
        if self.messages is not None:
            self.last_message_id = self.messages[0]["id"]
        else:
            self.remove_running_task("Switching channel", 1)
            logger.warn("Channel switching failed")
            return
        # update list of this guild channels
        self.current_channels = []
        for guild_channels in self.guilds:
            if guild_channels["guild_id"] == self.active_channel["guild_id"]:
                self.current_channels = guild_channels["channels"]
                break
        self.current_channel = {}
        for channel in self.current_channels:
            if channel["id"] == self.active_channel["channel_id"]:
                self.current_channel = channel
                break

        # if this is dm, check if user has sent minimum number of messages
        # this is to prevent triggering discords spam filter
        if not self.active_channel["guild_id"] and len(self.messages) < MSG_NUM:
            # if there is less than MSG_NUM messages, this is the start of conversation
            # so count all messages sent from this user
            my_messages = 0
            for message in self.messages:
                if message["user_id"] == self.my_id:
                    my_messages += 1
                    if my_messages >= MSG_MIN:
                        break
            if my_messages < MSG_MIN:
                self.disable_sending = True
                self.tui.draw_extra_line(f"Cant send a message: please send at least {MSG_MIN} messages with the official client")
        else:
            self.disable_sending = False
            self.tui.draw_extra_line()

        # misc
        self.typing = []
        self.chat_end = False
        self.selected_attachment = 0
        self.gateway.subscribe(self.active_channel["channel_id"], self.active_channel["guild_id"])
        self.set_seen(self.active_channel["channel_id"])

        # manage roles
        self.all_roles = self.tui.init_role_colors(
            self.all_roles,
            self.default_msg_color[1],
            self.default_msg_alt_color[1],
            guild_id=self.active_channel["guild_id"],
        )
        self.current_roles = []   # dm has no roles
        for roles in self.all_roles:
            if roles["guild_id"] == self.active_channel["guild_id"]:
                self.current_roles = roles["roles"]
                break
        self.current_my_roles = []   # user has no roles in dm
        for roles in self.my_roles:
            if roles["guild_id"] == self.active_channel["guild_id"]:
                self.current_my_roles = roles["roles"]
                break
        self.select_current_member_roles()

        # update UI
        self.update_chat(keep_selected=False)
        self.update_extra_line()
        self.update_prompt()
        self.update_tree()

        # save state
        if self.config["remember_state"]:
            self.state["last_guild_id"] = guild_id
            self.state["last_channel_id"] = channel_id
            peripherals.save_state(self.state)

        self.remove_running_task("Switching channel", 1)
        logger.debug("Channel switching complete")


    def open_guild(self, guild_id, select=False, restore=False):
        """When opening guild in tree"""
        guild = {}
        for guild_index, guild in enumerate(self.guilds):
            if guild["guild_id"] == guild_id:
                break

        # check in tree_format if it should be un-/collapsed
        collapse = False
        for num, obj in enumerate(self.tree_metadata):
            if obj and obj["id"] == guild_id:
                collapse = bool(self.tree_format[num] % 10)   # get first digit
                break

        # keep dms, collapsed and all guilds except one at cursor position
        self.check_tree_format(save=False)
        # copy over dms
        if 0 in self.state["collapsed"]:
            collapsed = [0]
        else:
            collapsed = []
        guild_ids = []

        if self.config["only_one_open_server"]:
            # collapse all othre guilds
            for guild_1 in self.guilds:
                if collapse or guild_1["guild_id"] != guild_id:
                    collapsed.append(guild_1["guild_id"])
                guild_ids.append(guild_1["guild_id"])
            # copy over categories
            for collapsed_id in self.state["collapsed"]:
                if collapsed_id not in guild_ids:
                    collapsed.append(collapsed_id)
        elif restore:
            # copy over all
            collapsed = self.state["collapsed"]
        # toggle only this guild
        elif collapse and guild_id not in self.state["collapsed"]:
            collapsed = self.state["collapsed"]
            collapsed.append(guild_id)
        elif not collapse and guild_id in self.state["collapsed"]:
            collapsed = self.state["collapsed"]
            collapsed.remove(guild_id)

        self.update_tree(collapsed=collapsed)

        # keep this guild selected
        if select:
            for tree_pos, obj in enumerate(self.tree_metadata):
                if obj and obj["id"] == guild_id:
                    break
            self.tui.tree_select(tree_pos)


    def select_current_member_roles(self):
        """Select member-roles for currently active guild and check for missing primary role colors"""
        if not self.active_channel["guild_id"]:
            self.current_member_roles = []
            return
        for guild in self.member_roles:
            if guild["guild_id"] == self.active_channel["guild_id"]:
                if self.username_role_colors:
                    for member in guild["members"]:
                        if "primary_role_color" not in member:
                            member_roles = member["roles"]
                            for role in self.current_roles:
                                if role["id"] in member_roles:
                                    member["primary_role_color"] = role.get("color_id")
                                    member["primary_role_alt_color"] = role.get("alt_color_id")
                                    break
                self.current_member_roles = guild["members"]
                break


    def add_to_store(self, channel_id, text):
        """Adds entry to input line store"""
        if self.cache_typed:
            done = False
            for num, channel in enumerate(self.input_store):
                if channel["id"] == channel_id:
                    self.input_store[num]["content"] = text
                    done = True
                    break
            if not done:
                self.input_store.append({
                    "id": channel_id,
                    "content": text,
                })


    def reset_actions(self):
        """Reset all actions"""
        self.replying = {
            "id": None,
            "content": None,
            "username": None,
            "global_name": None,
            "mention": None,
        }
        self.editing = {
            "id": None,
            "content": None,
        }
        self.deleting = {
            "id": None,
            "content": None,
        }
        self.warping = None
        self.going_to = None
        self.downloading_file = {
            "content": None,
            "urls": None,
            "web": False,
            "open": False,
        }
        self.cancel_download = None
        self.uploading = False


    def add_running_task(self, task, priority=5):
        """Add currently running long task with priority (lower number = higher priority)"""
        self.running_tasks.append([task, priority])
        self.update_status_line()


    def remove_running_task(self, task, priority):
        """Remove currently running long task"""
        try:
            self.running_tasks.remove([task, priority])
            self.update_status_line()
        except ValueError:
            pass


    def wait_input(self):
        """Thread that handles getting input, formatting, sending, replying, editing, deleting message and switching channel"""
        logger.info("Input handler loop started")

        while self.run:
            if self.editing["id"]:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.editing["content"], reset=False)
            elif self.replying["content"]:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.replying["content"], reset=False, keep_cursor=True)
            elif self.deleting["content"] or self.cancel_download:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt)
            elif self.warping is not None:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.warping, reset=False, keep_cursor=True, scroll_bot=True)
            elif self.going_to is not None:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.going_to, reset=False, keep_cursor=True)
            elif self.downloading_file["urls"]:
                if len(self.downloading_file["urls"]) == 1:
                    input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.downloading_file["content"], reset=False, keep_cursor=True)
                else:
                    input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt)
            elif self.uploading:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, autocomplete=True)
            else:
                restore_text = None
                if self.cache_typed:
                    for num, channel in enumerate(self.input_store):
                        if channel["id"] == self.active_channel["channel_id"]:
                            restore_text = self.input_store.pop(num)["content"]
                            break
                if restore_text:
                    input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=restore_text, reset=False, clear_delta=True)
                else:
                    input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, clear_delta=True)

            # switch channel
            if action == 4:
                if input_text and input_text != "\n":
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                sel_channel = self.tree_metadata[tree_sel]
                guild_id = None
                guild_name = None
                parent_index = self.tree_metadata[tree_sel]["parent_index"]
                for i in range(3):   # avoid infinite loops, there can be max 3 nest levels
                    if parent_index is None:
                        break
                    guild_id = self.tree_metadata[parent_index]["id"]
                    guild_name = self.tree_metadata[parent_index]["name"]
                    parent_index = self.tree_metadata[parent_index]["parent_index"]
                self.switch_channel(sel_channel["id"], sel_channel["name"], guild_id, guild_name)
                self.reset_actions()
                self.update_status_line()

            # set reply
            elif action == 1 and self.messages:
                self.reset_actions()
                msg_index = self.lines_to_msg(chat_sel)
                if "deleted" not in self.messages[msg_index]:
                    if self.messages[msg_index]["user_id"] == self.my_id:
                        mention = None
                    else:
                        mention = self.reply_mention
                    self.replying = {
                        "id": self.messages[msg_index]["id"],
                        "content": input_text,
                        "username": self.messages[msg_index]["username"],
                        "global_name": self.messages[msg_index]["global_name"],
                        "mention": mention,
                    }
                    self.update_status_line()

            # set edit
            elif action == 2 and self.messages:
                msg_index = self.lines_to_msg(chat_sel)
                if self.messages[msg_index]["user_id"] == self.my_id:
                    if "deleted" not in self.messages[msg_index]:
                        self.reset_actions()
                        self.editing = {
                            "id": self.messages[msg_index]["id"],
                            "content": self.messages[msg_index]["content"],
                        }
                        self.update_status_line()

            # set delete
            elif action == 3 and self.messages:
                msg_index = self.lines_to_msg(chat_sel)
                if self.messages[msg_index]["user_id"] == self.my_id:
                    if "deleted" not in self.messages[msg_index]:
                        self.add_to_store(self.active_channel["channel_id"], input_text)
                        self.reset_actions()
                        self.deleting = {
                            "id": self.messages[msg_index]["id"],
                            "content": input_text,
                        }
                        self.update_status_line()

            # toggle mention ping
            elif action == 6:
                self.replying["content"] = input_text
                self.replying["mention"] = None if self.replying["mention"] is None else not self.replying["mention"]
                self.update_status_line()

            # warping to chat bottom
            elif action == 7 and self.messages:
                self.warping = input_text
                if self.messages[0]["id"] != self.last_message_id:
                    self.add_running_task("Downloading chat", 4)
                    self.messages = self.get_messages_with_members()
                    self.update_chat()
                    self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
                    self.remove_running_task("Downloading chat", 4)

            # go to replied message
            elif action == 8 and self.messages:
                self.going_to = input_text
                msg_index = self.lines_to_msg(chat_sel)
                if self.messages[msg_index]["referenced_message"]:
                    reference_id = self.messages[msg_index]["referenced_message"]["id"]
                    if reference_id:
                        self.go_to_message(reference_id)

            # download file
            elif action == 9:
                msg_index = self.lines_to_msg(chat_sel)
                urls = []
                for embed in self.messages[msg_index]["embeds"]:
                    if embed["url"]:
                        urls.append(embed["url"])
                if len(urls) == 1:
                    self.downloading_file = {
                        "content": input_text,
                        "urls": urls,
                        "web": False,
                        "open": False,
                    }
                    self.download_threads.append(threading.Thread(target=self.download_file, daemon=True, args=(urls[0], )))
                    self.download_threads[-1].start()
                elif len(urls) > 1:
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.downloading_file = {
                        "content": input_text,
                        "urls": urls,
                        "web": False,
                        "open": False,
                    }
                    self.update_status_line()

            # open link in browser
            elif action == 10:
                msg_index = self.lines_to_msg(chat_sel)
                urls = []
                for url in re.findall(match_url, self.messages[msg_index]["content"]):
                    urls.append(url[0])
                for embed in self.messages[msg_index]["embeds"]:
                    if embed["url"]:
                        urls.append(embed["url"])
                if len(urls) == 1:
                    self.downloading_file = {
                        "content": input_text,
                        "urls": urls,
                        "web": False,
                        "open": False,
                    }
                    webbrowser.open(urls[0], new=0, autoraise=True)
                elif len(urls) > 1:
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.downloading_file = {
                        "content": input_text,
                        "urls": urls,
                        "web": True,
                        "open": False,
                    }
                    self.update_status_line()

            # download and open media attachment
            elif action == 17 and support_media:
                msg_index = self.lines_to_msg(chat_sel)
                urls = []
                media_type = None
                for embed in self.messages[msg_index]["embeds"]:
                    media_type = embed["type"].split("/")[0]
                    if embed["url"] and media_type in MEDIA_EMBEDS:
                        urls.append(embed["url"])
                for sticker in self.messages[msg_index]["stickers"]:
                    media_type = f"sticker_{sticker["format_type"]}"
                    sticker_url = discord.get_sticker_url(sticker)
                    if sticker_url:
                        urls.append(sticker_url)
                if len(urls) == 1:
                    logger.debug(f"Trying to play attachment with type: {media_type}")
                    self.downloading_file = {
                        "content": input_text,
                        "urls": urls,
                        "web": False,
                        "open": True,
                    }
                    self.download_threads.append(threading.Thread(target=self.download_file, daemon=True, args=(urls[0], False, True)))
                    self.download_threads[-1].start()
                elif len(urls) > 1:
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.downloading_file = {
                        "content": input_text,
                        "urls": urls,
                        "web": False,
                        "open": True,
                    }
                    self.update_status_line()


            # cancel all downloads and uploads
            elif action == 11:
                self.add_to_store(self.active_channel["channel_id"], input_text)
                self.reset_actions()
                self.cancel_download = True
                self.update_status_line()

            # copy message to clipboard
            elif action == 12 and self.messages:
                msg_index = self.lines_to_msg(chat_sel)
                self.going_to = input_text   # reusing variable
                peripherals.copy_to_clipboard(self.messages[msg_index]["content"])

            # upload attachment
            elif action == 13 and self.messages and not self.disable_sending:
                if self.current_channel.get("allow_attach", True):
                    self.uploading = True
                self.add_to_store(self.active_channel["channel_id"], input_text)
                self.update_status_line()

            # moving left/right through attachments
            elif action == 14:
                self.going_to = input_text   # reusing variable
                if self.selected_attachment > 0:
                    self.selected_attachment -= 1
                    self.update_extra_line()
            elif action == 15:
                self.going_to = input_text   # reusing variable
                num_attachments = 0
                for attachments in self.ready_attachments:
                    if attachments["channel_id"] == self.active_channel["channel_id"]:
                        num_attachments = len(attachments["attachments"])
                if self.selected_attachment + 1 < num_attachments:
                    self.selected_attachment += 1
                    self.update_extra_line()

            # cancel selected attachment
            elif action == 16:
                self.going_to = input_text   # reusing variable
                self.cancel_attachment()
                self.update_extra_line()

            # reveal one-by-one spoiler in a message
            elif action == 18:
                msg_index = self.lines_to_msg(chat_sel)
                self.going_to = input_text   # reusing variable
                if "spoiled" in self.messages[msg_index]:
                    self.messages[msg_index]["spoiled"] += 1
                else:
                    self.messages[msg_index]["spoiled"] = 1
                self.update_chat(keep_selected=True)

            # open guild in tree
            elif action == 19:
                self.going_to = input_text   # reusing variable
                guild_id = self.tree_metadata[tree_sel]["id"]
                self.open_guild(guild_id, select=True)

            # copy/cut on input line
            elif action == 20:
                self.going_to = input_text   # reusing variable
                peripherals.copy_to_clipboard(self.tui.get_input_selected())

            # escape key in main UI
            elif action == 5:
                if self.replying["id"]:
                    self.reset_actions()
                    self.replying["content"] = input_text
                else:
                    self.reset_actions()
                self.update_status_line()

            # escape key in media viewer
            elif action == 101:
                self.curses_media.stop()

            # enter
            elif action == 0 and input_text and input_text != "\n" and self.active_channel["channel_id"]:
                # message will be received from gateway and then added to self.messages
                if self.editing["id"]:
                    self.discord.send_update_message(
                        channel_id=self.active_channel["channel_id"],
                        message_id=self.editing["id"],
                        message_content=input_text,
                    )
                elif self.deleting["id"] and input_text.lower() == "y":
                    self.discord.send_delete_message(
                        channel_id=self.active_channel["channel_id"],
                        message_id=self.deleting["id"],
                    )
                elif self.downloading_file["urls"] and len(self.downloading_file["urls"]) > 1:
                    if self.downloading_file["web"]:
                        try:
                            num = max(int(input_text) - 1, 0)
                            if num <= len(self.downloading_file["urls"]):
                                webbrowser.open(urls[num], new=0, autoraise=True)
                        except ValueError:
                            pass
                    elif self.downloading_file["open"]:
                        try:
                            logger.debug("Trying to play attachment from seletion")
                            num = max(int(input_text) - 1, 0)
                            if num <= len(self.downloading_file["urls"]):
                                self.download_threads.append(threading.Thread(target=self.download_file, daemon=True, args=(urls[num], False, True)))
                                self.download_threads[-1].start()
                        except ValueError:
                            pass
                    else:
                        try:
                            num = max(int(input_text) - 1, 0)
                            if num <= len(self.downloading_file["urls"]):
                                self.download_threads.append(threading.Thread(target=self.download_file, daemon=True, args=(urls[num], )))
                                self.download_threads[-1].start()
                        except ValueError:
                            pass
                elif self.cancel_download and input_text.lower() == "y":
                    download.cancel()
                    self.download_threads = []
                    self.cancel_upload()
                    self.upload_threads = []
                elif self.uploading:
                    self.upload_threads.append(threading.Thread(target=self.upload, daemon=True, args=(input_text, )))
                    self.upload_threads[-1].start()
                else:
                    this_attachments = None
                    for num, attachments in enumerate(self.ready_attachments):
                        if attachments["channel_id"] == self.active_channel["channel_id"]:
                            this_attachments = self.ready_attachments.pop(num)["attachments"]
                            self.update_extra_line()
                            break
                    if not self.disable_sending:
                        text_to_send = emoji.emojize(input_text, language="alias", variant="emoji_type")
                        self.discord.send_message(
                            self.active_channel["channel_id"],
                            text_to_send,
                            reply_id=self.replying["id"],
                            reply_channel_id=self.active_channel["channel_id"],
                            reply_guild_id=self.active_channel["guild_id"],
                            reply_ping=self.replying["mention"],
                            attachments=this_attachments,
                        )
                self.reset_actions()
                self.update_status_line()

            # enter with no text
            elif input_text == "":
                if self.deleting["id"]:
                    self.discord.send_delete_message(
                        channel_id=self.active_channel["channel_id"],
                        message_id=self.deleting["id"],
                    )
                elif self.cancel_download:
                    download.cancel()
                    self.download_threads = []
                    self.cancel_upload()
                    self.upload_threads = []
                elif self.ready_attachments:
                    this_attachments = None
                    for attachments in self.ready_attachments:
                            this_attachments = self.ready_attachments.pop(num)["attachments"]
                            self.update_extra_line()
                            break
                    self.discord.send_message(
                        self.active_channel["channel_id"],
                        "",
                        reply_id=self.replying["id"],
                        reply_channel_id=self.active_channel["channel_id"],
                        reply_guild_id=self.active_channel["guild_id"],
                        reply_ping=self.replying["mention"],
                        attachments=this_attachments,
                    )
                self.reset_actions()
                self.update_status_line()


    def download_file(self, url, move=True, open_media=False):
        """Thread that downloads and moves file to downloads dir"""
        if "https://media.tenor.com/" in url:
            url = downloader.convert_tenor_gif_type(url, self.tenor_gif_type)
        destination = None
        from_cache = False

        # check if file is already downloaded
        if open_media:
            for file in self.cached_downloads:
                if url == file[0] and os.path.exists(file[1]):
                    destination = file[1]
                    break

        # downlaod
        if not open_media or not destination:
            self.add_running_task("Downloading file", 2)
            try:
                path = download.download(url)
                if path:
                    if move:
                        if not os.path.exists(self.downloads_path):
                            os.makedirs(os.path.expanduser(os.path.dirname(self.downloads_path)), exist_ok=True)
                        destination = os.path.join(self.downloads_path, os.path.basename(path))
                        shutil.move(path, destination)
                    else:
                        destination = path
            except Exception as e:
                logger.error(f"Failed downloading file: {e}")

        self.remove_running_task("Downloading file", 2)

        # open media
        if open_media:
            self.media_thread = threading.Thread(target=self.open_media, daemon=True, args=(destination, ))
            self.media_thread.start()
            if not from_cache and destination:
                self.cached_downloads.append([url, destination])


    def upload(self, path):
        """Thread that uploads file to curently open channel"""
        path = os.path.expanduser(path)
        if os.path.exists(path) and not os.path.isdir(path):

            # add attachment to list
            found = False
            for ch_index, channel in enumerate(self.ready_attachments):
                if channel["channel_id"] == self.active_channel["channel_id"]:
                    found = True
                    break
            if not found:
                self.ready_attachments.append({
                    "channel_id": self.active_channel["channel_id"],
                    "attachments": [],
                })
                ch_index = len(self.ready_attachments) - 1
            self.ready_attachments[ch_index]["attachments"].append({
                "path": path,
                "name": os.path.basename(path),
                "upload_url": None,
                "upload_filename": None,
                "state": 0,
            })
            at_index = len(self.ready_attachments[ch_index]["attachments"]) - 1

            self.add_running_task("Uploading file", 2)
            self.update_extra_line()
            upload_data, code = self.discord.request_attachment_link(self.active_channel["channel_id"], path)
            if upload_data:
                uploaded = self.discord.upload_attachment(upload_data["upload_url"], path)
                if uploaded:
                    self.ready_attachments[ch_index]["attachments"][at_index]["upload_url"] = upload_data["upload_url"]
                    self.ready_attachments[ch_index]["attachments"][at_index]["upload_filename"] = upload_data["upload_filename"]
                    self.ready_attachments[ch_index]["attachments"][at_index]["state"] = 1
                else:
                    self.ready_attachments[ch_index]["attachments"][at_index]["path"] = None
                    self.ready_attachments[ch_index]["attachments"][at_index]["state"] = 4
            else:
                self.ready_attachments[ch_index]["attachments"][at_index]["path"] = None
                if code == 1:
                    self.ready_attachments[ch_index]["attachments"][at_index]["state"] = 4
                elif code == 2:
                    self.ready_attachments[ch_index]["attachments"][at_index]["state"] = 2
            self.update_extra_line()
            self.remove_running_task("Uploading file", 2)


    def cancel_upload(self):
        """Cancels and removes all uploaded attachments from list"""
        for num, attachments_ch in enumerate(self.ready_attachments):
            if attachments_ch["channel_id"] == self.active_channel["channel_id"]:
                attachments = self.ready_attachments.pop(num)["attachments"]
                if not attachments:
                    break
                for attachment in attachments:
                    self.discord.cancel_uploading(url=attachment["upload_url"])
                    self.discord.cancel_attachment(attachment["upload_filename"])
                    self.selected_attachment = 0
                    self.update_extra_line()
                break


    def cancel_attachment(self):
        """Cancel currently selected attachment"""
        for num, attachments_ch in enumerate(self.ready_attachments):
            if attachments_ch["channel_id"] == self.active_channel["channel_id"]:
                attachments = self.ready_attachments[num]["attachments"]
                if attachments:
                    attachment = attachments.pop(self.selected_attachment)["upload_filename"]
                    if not len(attachments):
                        self.ready_attachments.pop(num)
                    self.discord.cancel_attachment(attachment)
                    if self.selected_attachment >= 1:
                        self.selected_attachment -= 1
                    self.update_extra_line()
                break


    def get_messages_with_members(self, num=50, before=None, after=None, around=None):
        """Get messages, check for missing members, request and wait for member chunk, and update local member list"""
        channel_id = self.active_channel["channel_id"]
        messages = self.discord.get_messages(channel_id, num, before, after, around)
        if messages is None:
            return None   # network error
        # restore deleted
        if self.restore_deleted:
            messages = self.restore_deleted(messages)
        missing_members = []
        if not self.active_channel["guild_id"]:
            # skipping DMs
            return messages
        # find missing members
        for message in messages:
            found = False
            message_user_id = message["user_id"]
            if message_user_id in missing_members:
                continue
            for member in self.current_member_roles:
                if member["user_id"] == message_user_id:
                    found = True
                    break
            if not found:
                missing_members.append(message_user_id)
        # request missing members
        if missing_members:
            self.gateway.request_members(self.active_channel["guild_id"], missing_members)
            for _ in range(10):   # wait max 1s
                new_member_roles = self.gateway.get_member_roles()
                if new_member_roles:
                    # update member list
                    self.member_roles = new_member_roles
                    self.select_current_member_roles()
                else:
                    # wait to receive
                    time.sleep(0.1)
        return messages


    def get_chat_chunk(self, past=True):
        """Get chunk of chat in specified direction and add it to existing chat, trim chat to limited size and trigger update_chat"""
        self.add_running_task("Downloading chat", 4)
        start_id = self.messages[-int(past)]["id"]

        if past:
            logger.debug(f"Requesting chat chunk before {start_id}")
            new_chunk = self.get_messages_with_members(before=start_id)
            self.messages = self.messages + new_chunk
            all_msg = len(self.messages)
            selected_line = len(self.chat) - 1
            selected_msg = self.lines_to_msg(selected_line)
            self.messages = self.messages[-self.limit_chat_buffer:]
            if new_chunk:
                self.update_chat(keep_selected=None)
                # when messages are trimmed, keep same selecteed position
                if len(self.messages) != all_msg:
                    selected_msg_new = selected_msg - (all_msg - len(self.messages))
                    selected_line = self.msg_to_lines(selected_msg_new)
                self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
                self.tui.set_selected(selected_line)
            elif new_chunk == []:   # if its None - its network error
                self.chat_end = True

        else:
            logger.debug(f"Requesting chat chunk after {start_id}")
            new_chunk = self.get_messages_with_members(after=start_id)
            if new_chunk is not None:   # if its None - its network error
                selected_line = 0
                selected_msg = self.lines_to_msg(selected_line)
                self.messages = new_chunk + self.messages
                all_msg = len(self.messages)
                self.messages = self.messages[:self.limit_chat_buffer]
                self.update_chat(keep_selected=True)
                # keep same selecteed position
                selected_msg_new = selected_msg + len(new_chunk)
                selected_line = self.msg_to_lines(selected_msg_new)
                self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
                self.tui.set_selected(selected_line)
        self.remove_running_task("Downloading chat", 4)


    def go_to_message(self, message_id):
        """Check if message is in current chat buffer, if not: load chunk around specified message id and select message"""
        found = False
        for num, message in enumerate(self.messages):
            if message["id"] == message_id:
                self.tui.set_selected(self.msg_to_lines(num))
                found = True
                break

        if not found:
            logger.debug(f"Requesting chat chunk around {message_id}")
            new_messages = self.get_messages_with_members(around=message_id)
            if new_messages:
                self.messages = new_messages
            self.update_chat(keep_selected=False)

            for num, message in enumerate(self.messages):
                if message["id"] == message_id:
                    self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
                    self.tui.set_selected(self.msg_to_lines(num))
                    break


    def cache_deleted(self):
        """Cache all deleted messages from current channel"""
        if not self.active_channel["channel_id"]:
            return
        found = False
        for channel in self.deleted_cache:
            if channel["channel_id"] == self.active_channel["channel_id"]:
                this_channel_cache = channel["messages"]
                found = True
                break
        if not found:
            self.deleted_cache.append({
                "channel_id": self.active_channel["channel_id"],
                "messages": [],
            })
            this_channel_cache = self.deleted_cache[-1]["messages"]
        for message in self.messages:
            if message.get("deleted"):
                found = False
                for message_c in this_channel_cache:
                    if message_c["id"] == message["id"]:
                        found = True
                if not found:
                    this_channel_cache.append(message)
                    if len(this_channel_cache) > self.deleted_cache_limit:
                        this_channel_cache.pop(0)


    def restore_deleted(self, messages):
        """Restore all cached deleted messages for this channels in the correct position"""
        found = False
        for channel in self.deleted_cache:
            if channel["channel_id"] == self.active_channel["channel_id"]:
                this_channel_cache = channel["messages"]
                found = True
                break
        if not found:
            return messages
        for message_c in this_channel_cache:
            message_c_id = message_c["id"]
            # ids are discord snowflakes containing unix time so it can be used message sent time
            if message_c_id < messages[-1]["id"]:
                # if message_c date is before last message date
                continue
            if message_c_id > messages[0]["id"]:
                # if message_c date is after first message date
                continue
            for num, message in enumerate(messages):
                try:
                    if message["id"] > message_c_id > messages[num+1]["id"]:
                        # if message_c date is between this and next message dates
                        messages.insert(num+1, message_c)
                        break
                except IndexError:
                    break
        return messages


    def open_media(self, path):
        """Prevent other UI updates, draw media and wait for input, after quitting - update UI"""
        if support_media:
            self.tui.lock_ui(True)
            self.curses_media.play(path)
            # restore first 255 colors, attributes were not modified
            self.tui.restore_colors()
            self.tui.lock_ui(False)


    def update_chat(self, keep_selected=True, change_amount=0):
        """Generate chat and update it in TUI"""
        if keep_selected:
            selected_line, text_index = self.tui.get_selected()
            if selected_line == -1:
                keep_selected = False
            if change_amount > 0:
                self.unseen_scrolled = bool(text_index)
                self.update_status_line()
            selected_msg = self.lines_to_msg(selected_line)
        else:
            self.unseen_scrolled = False
            self.update_status_line()
        self.chat, self.chat_format, self.chat_indexes = formatter.generate_chat(
            self.messages,
            self.current_roles,
            self.current_channels,
            self.chat_dim[1],
            self.my_id,
            self.my_roles,
            self.current_member_roles,
            self.colors,
            self.colors_formatted,
            self.blocked,
            self.config,
        )
        if keep_selected:
            selected_msg = selected_msg + change_amount
            selected_line_new = self.msg_to_lines(selected_msg)
            change_amount_lines = selected_line_new - selected_line
            self.tui.set_selected(selected_line_new, change_amount=change_amount_lines)
        elif keep_selected is not None:
            self.tui.set_selected(-1)   # return to bottom
        self.tui.update_chat(self.chat, self.chat_format)


    def update_status_line(self):
        """Generate status and title lines and update them in TUI"""
        action_type = 0
        if self.replying["id"]:
            action_type = 1
        elif self.editing["id"]:
            action_type = 2
        elif self.deleting["id"]:
            action_type = 3
        elif self.downloading_file["urls"] and len(self.downloading_file["urls"]) > 1:
            if self.downloading_file["web"]:
                action_type = 4
            elif self.download_file["open"]:
                action_type = 6
            else:
                action_type = 5
        elif self.cancel_download:
            action_type = 7
        elif self.uploading:
            action_type = 8
        action = {
            "type": action_type,
            "username": self.replying["username"],
            "global_name": self.replying["global_name"],
            "mention": self.replying["mention"],
        }
        if self.format_status_line_r:
            status_line_r = formatter.generate_status_line(
                self.my_user_data,
                self.my_status,
                self.unseen_scrolled,
                self.typing,
                self.active_channel,
                action,
                self.running_tasks,
                self.format_status_line_r,
                self.config["format_rich"],
                limit_typing=self.limit_typing,
        )
        else:
            status_line_r = None
        status_line_l = formatter.generate_status_line(
            self.my_user_data,
            self.my_status,
            self.unseen_scrolled,
            self.typing,
            self.active_channel,
            action,
            self.running_tasks,
            self.format_status_line_l,
            self.config["format_rich"],
            limit_typing=self.limit_typing,
        )
        self.tui.update_status_line(status_line_l, status_line_r)

        if self.format_title_line_r:
            title_line_r = formatter.generate_status_line(
                self.my_user_data,
                self.my_status,
                self.unseen_scrolled,
                self.typing,
                self.active_channel,
                action,
                self.running_tasks,
                self.format_title_line_r,
                self.config["format_rich"],
                limit_typing=self.limit_typing,
            )
        else:
            title_line_r = None
        if self.format_title_line_l:
            title_line_l = formatter.generate_status_line(
                self.my_user_data,
                self.my_status,
                self.unseen_scrolled,
                self.typing,
                self.active_channel,
                action,
                self.running_tasks,
                self.format_title_line_l,
                self.config["format_rich"],
                limit_typing=self.limit_typing,
            )
            self.tui.update_title_line(title_line_l, title_line_r)
        if self.format_title_tree:
            title_tree = formatter.generate_status_line(
                self.my_user_data,
                self.my_status,
                self.unseen_scrolled,
                self.typing,
                self.active_channel,
                action,
                self.running_tasks,
                self.format_title_tree,
                self.config["format_rich"],
                limit_typing=self.limit_typing,
            )
        else:
            title_tree = None
        self.tui.update_title_tree(title_tree)


    def update_prompt(self):
        """Generate prompt for input line"""
        self.prompt = formatter.generate_prompt(
            self.my_user_data,
            self.active_channel,
            self.config["format_prompt"],
        )


    def update_extra_line(self):
        """Genearate extra line and update it in TUI"""
        attachments = None
        for attachments in self.ready_attachments:
            if attachments["channel_id"] == self.active_channel["channel_id"]:
                break
        if attachments:
            statusline_w = self.tui.get_dimensions()[2][1]
            extra_line = formatter.generate_extra_line(attachments["attachments"], self.selected_attachment, statusline_w)
            self.tui.draw_extra_line(extra_line)
        else:
            self.tui.remove_extra_line()


    def update_tree(self, collapsed=None, init_uncollapse=False):
        """Generate channel tree"""
        if collapsed is None:
            collapsed = self.state["collapsed"]
        self.tree, self.tree_format, self.tree_metadata = formatter.generate_tree(
            self.dms,
            self.guilds,
            [x["channel_id"] for x in self.unseen],
            [x["channel_id"] for x in self.pings],
            self.guild_positions,
            collapsed,
            self.active_channel["channel_id"],
            self.config["tree_drop_down_vline"],
            self.config["tree_drop_down_hline"],
            self.config["tree_drop_down_intersect"],
            self.config["tree_drop_down_corner"],
            self.config["tree_drop_down_pointer"],
            init_uncollapse=init_uncollapse,
            safe_emoji=self.config["emoji_as_text"],
        )
        # debug_guilds_tree
        # debug.save_json(self.tree, "tree.json", False)
        # debug.save_json(self.tree_format, "tree_format.json", False)
        # debug.save_json(self.tree_metadata, "tree_metadata.json", False)
        self.tui.update_tree(self.tree, self.tree_format)


    def lines_to_msg(self, lines):
        """Convert line index from formatted chat to message index"""
        total_len = 0
        for num, msg_len in enumerate(self.chat_indexes):
            total_len += msg_len
            if total_len >= lines + 1:
                return num
        return 0


    def msg_to_lines(self, msg):
        """Convert message index to line index from formatted chat"""
        return sum(self.chat_indexes[:msg + 1]) - 1


    def set_seen(self, channel_id, force=False):
        """Set channel as seen if it is not already seen.
        Force will send even if its not marked as unseen, used for active channel."""
        for num_1, unseen_channel in enumerate(self.unseen):
            if unseen_channel["channel_id"] == channel_id or force:   # find this unseen chanel
                if not force:
                    self.unseen.pop(num_1)
                self.update_tree()
                self.discord.send_ack_message(channel_id, self.messages[0]["id"])
                for num, pinged_channel in enumerate(self.pings):
                    if channel_id == pinged_channel["channel_id"]:
                        self.pings.pop(num)
                        break
                if self.enable_notifications:
                    for num, notification in enumerate(self.notifications):
                        if notification["channel_id"] == channel_id:
                            notification_id = self.notifications.pop(num)["notification_id"]
                            peripherals.notify_remove(notification_id)
                            break
                break


    def compute_permissions(self):
        """Compute permissions for all guilds. Run after roles have been obtained."""
        for guild in self.guilds:
            guild_id = guild["guild_id"]
            my_roles = None   # user has no roles in dm
            for roles in self.my_roles:
                if roles["guild_id"] == guild_id:
                    my_roles = roles["roles"]
                    break
            if my_roles is None:
                return
            # get permissions
            self.guilds = perms.compute_permissions(
                self.guilds,
                self.current_roles,
                guild_id,
                my_roles,
                self.my_id,
            )


    def check_tree_format(self, save=True):
        """Check tree format for collapsed guilds and categories and save it"""
        new_tree_format = self.tui.get_tree_format()
        if new_tree_format:
            self.tree_format = new_tree_format
            # get all collapsed channels/guilds and save them
            collapsed = []
            for num, code in enumerate(self.tree_format):
                if code < 300 and (code % 10) == 0:
                    collapsed.append(self.tree_metadata[num]["id"])
            if self.state["collapsed"] != collapsed:
                self.state["collapsed"] = collapsed
                if save:
                    peripherals.save_state(self.state)


    def send_desktop_notification(self, new_message):
        """
        Send desktop notification, and handle its ID so it can be removed.
        Send only one notification per channel.
        """
        if self.enable_notifications:
            skip = False
            for notification in self.notifications:
                if notification["channel_id"] == new_message["d"]["channel_id"]:
                    skip = True
            if not skip:
                notification_id = peripherals.notify_send(
                    APP_NAME,
                    f"{new_message["d"]["global_name"]}:\n{new_message["d"]["content"]}",
                    sound=self.notification_sound,
                )
                self.notifications.append({
                    "notification_id": notification_id,
                    "channel_id": new_message["d"]["channel_id"],
                })


    def main(self):
        """Main app method"""
        logger.info("Main started")
        logger.info("Waiting for ready signal from gateway")
        while not self.gateway.get_ready():
            time.sleep(0.2)

        # guild positions
        self.discord_settings = self.gateway.get_settings_proto()
        self.guild_positions = []
        for folder in self.discord_settings["guildFolders"]["folders"]:
            self.guild_positions += folder["guildIds"]
        if logger.getEffectiveLevel() == logging.DEBUG:
            debug.save_json(debug.anonymize_guild_positions(self.guild_positions), "guild_positions.json")
        # debug_guilds_tree
        # debug.save_json(self.guild_positions, "guild_positions.json", False)
        # self.guild_positions = debug.load_json("guild_positions.json")

        # custom status
        custom_status_emoji = None
        custom_status = None
        if "customStatus" in self.discord_settings["status"]:
            custom_status_emoji = {
                "id": self.discord_settings["status"]["customStatus"].get("emojiID"),
                "name": self.discord_settings["status"]["customStatus"].get("emojiName"),
                "animated": self.discord_settings["status"]["customStatus"].get("animated", False),
            }
            custom_status = self.discord_settings["status"]["customStatus"]["text"]
        if custom_status_emoji and not (custom_status_emoji["name"] or custom_status_emoji["id"]):
            custom_status_emoji = None
        self.my_status = {
            "status": self.discord_settings["status"]["status"],
            "custom_status": custom_status,
            "custom_status_emoji": custom_status_emoji,
            "activities": [],
            "client_state": "online",
        }
        self.gateway_state = 1
        logger.info("Gateway is ready")
        self.tui.update_chat(["Loading channels", "Connecting to Discord"], [[[self.colors[0]]]] * 2)

        # get data from gateway
        self.guilds = self.gateway.get_guilds()
        self.all_roles = self.gateway.get_roles()
        self.all_roles = color.convert_role_colors(self.all_roles)
        self.color_cache = self.tui.get_color_cache()
        last_free_color_id = self.tui.get_last_free_color_id()

        # get my roles
        self.my_roles = self.gateway.get_my_roles()
        self.current_my_roles = []
        for roles in self.my_roles:
            if roles["guild_id"] == self.active_channel["guild_id"]:
                self.current_my_roles = roles["roles"]
                break
        self.compute_permissions()

        # init media
        if support_media:
            # must be run after all colors are initialized in endcord.tui
            logger.info("Media is supported")
            self.curses_media = media.CursesMedia(self.screen, self.config, last_free_color_id)
        else:
            self.curses_media = None
            logger.info("Media is not supported")

        # load dms
        self.dms, self.dms_id = self.gateway.get_dms()
        if self.hide_spam:
            for dm in self.dms:
                if dm["is_spam"]:
                    self.dms_id.remove(dm["id"])
                    self.dms.remove(dm)

        # load pings, unseen and blocked
        self.pings = []
        for channel_id in self.gateway.get_pings():
            self.pings.append({
                "channel_id": channel_id,
                "message_id": None,
            })
        self.unseen = []
        for channel_id in self.gateway.get_unseen():
            guild_id = None
            for guild in self.guilds:
                for channel in guild["channels"]:
                    if channel["id"] == channel_id:
                        guild_id = guild["guild_id"]
                if guild_id:
                    break
            self.unseen.append({
                "channel_id": channel_id,
                "guild_id": guild_id,
            })
        self.blocked = self.gateway.get_blocked()
        self.run = True

        # restore last state
        if self.config["remember_state"]:
            self.state = peripherals.load_state()
            if self.state is None:
                self.state = {
                    "last_guild_id": None,
                    "last_channel_id": None,
                    "collapsed": [],
                }

        # open uncollapsed guilds
        self.open_guild(guild["guild_id"], restore=True)

        # load messages
        if self.state["last_channel_id"]:
            self.tui.update_chat(["Loading messages", "Loading channels", "Connecting to Discord"], [[[self.colors[0]]]] * 3)
            guild_id = self.state["last_guild_id"]
            channel_id = self.state["last_channel_id"]
            channel_name = None
            guild_name = None
            if guild_id:
                for guild in self.guilds:
                    if guild["guild_id"] == guild_id:
                        guild_name = guild["name"]
                        break
                for channel in guild["channels"]:
                    if channel["id"] == channel_id:
                        channel_name = channel["name"]
                        break
            else:
                for channel in self.dms:
                    if channel["id"] == channel_id:
                        channel_name = channel["name"]
                        break
            if channel_name:
                self.switch_channel(channel_id, channel_name, guild_id, guild_name)
                self.tui.tree_select_active()

        # generate and draw tree
        if not self.tree_format:
            self.update_tree(init_uncollapse=True)
            self.tui.update_chat(["Select channel to load messages", "Loading channels", "Connecting to Discord"], [[[self.colors[0]]]] * 3)

        # send new presence and start input thread
        self.gateway.update_presence(
            self.my_status["status"],
            custom_status=self.my_status["custom_status"],
            custom_status_emoji=self.my_status["custom_status_emoji"],
            rpc=self.my_rpc,
        )
        self.send_message_thread = threading.Thread(target=self.wait_input, daemon=True, args=())
        self.send_message_thread.start()

        # start RPC server
        if self.enable_rpc:
            self.rpc = rpc.RPC(self.discord, self.my_user_data, self.config)
            self.rpc_thread = threading.Thread(target=self.rpc.server_thread, daemon=True, args=())
            self.rpc_thread.start()

        logger.info("Main loop started")

        while self.run:
            selected_line, text_index = self.tui.get_selected()
            # get new messages
            while self.run:
                new_message = self.gateway.get_messages()
                if new_message:
                    op = new_message["op"]
                    new_message_channel_id = new_message["d"]["channel_id"]
                    this_channel = (new_message_channel_id == self.active_channel["channel_id"])
                    if this_channel:
                        data = new_message["d"]
                        if op == "MESSAGE_CREATE":
                            # if latest message is loaded - not viewing old message chunks
                            if self.messages[0]["id"] == self.last_message_id:
                                self.messages.insert(0, data)
                            self.last_message_id = new_message["d"]["id"]
                            # limit chat size
                            if len(self.messages) > self.limit_chat_buffer:
                                self.messages.pop(-1)
                            self.update_chat(change_amount=1)
                            if not self.unseen_scrolled:
                                if time.time() - self.sent_ack_time > self.ack_throttling:
                                    self.set_seen(self.active_channel["channel_id"], force=True)
                                    self.sent_ack_time = time.time()
                                    self.pending_ack = False
                                else:
                                    self.pending_ack = True
                            # remove user from typing
                            for num, user in enumerate(self.typing):
                                if user["user_id"] == data["user_id"]:
                                    self.typing.pop(num)
                                    self.update_status_line()
                                    break
                            new_member_roles = self.gateway.get_member_roles()
                            if new_member_roles:
                                self.member_roles = new_member_roles
                                self.select_current_member_roles()
                                self.update_chat()
                        else:
                            for num, loaded_message in enumerate(self.messages):
                                if data["id"] == loaded_message["id"]:
                                    if op == "MESSAGE_UPDATE":
                                        for element in MESSAGE_UPDATE_ELEMENTS:
                                            loaded_message[element] = data[element]
                                            loaded_message["spoiled"] = 0
                                        self.update_chat()
                                    elif op == "MESSAGE_DELETE":
                                        self.messages[num]["deleted"] = True
                                        if num < selected_line and not self.keep_deleted:
                                            self.update_chat(change_amount=-1)
                                        else:
                                            self.update_chat()
                                    elif op == "MESSAGE_REACTION_ADD":
                                        found = False
                                        for num2, reaction in enumerate(loaded_message["reactions"]):
                                            if data["emoji_id"] == reaction["emoji_id"] and data["emoji"] == reaction["emoji"]:
                                                loaded_message["reactions"][num2]["count"] += 1
                                                found = True
                                                break
                                        if not found:
                                            loaded_message["reactions"].append({
                                                "emoji": data["emoji"],
                                                "emoji_id": data["emoji_id"],
                                                "count": 1,
                                                "me": False,
                                            })
                                        self.update_chat()
                                    elif op == "MESSAGE_REACTION_REMOVE":
                                        for num2, reaction in enumerate(loaded_message["reactions"]):
                                            if data["emoji_id"] == reaction["emoji_id"] and data["emoji"] == reaction["emoji"]:
                                                if reaction["count"] <= 1:
                                                    loaded_message["reactions"].pop(num2)
                                                else:
                                                    loaded_message["reactions"][num2]["count"] -= 1
                                                break
                                        self.update_chat()
                    else:
                        new_member_roles = self.gateway.get_member_roles()
                        if new_member_roles:
                            self.member_roles = new_member_roles
                    # handling unseen and mentions
                    if not this_channel or (this_channel and (self.unseen_scrolled or self.ping_this_channel)):
                        # ignoring messages sent by other clients
                        if op == "MESSAGE_CREATE" and new_message["d"]["user_id"] != self.my_id:
                            if new_message_channel_id not in [x["channel_id"] for x in self.unseen]:
                                self.unseen.append({
                                    "channel_id": new_message_channel_id,
                                    "guild_id": new_message["d"]["guild_id"],
                                })
                            mentions = []
                            for mention in new_message["d"]["mentions"]:
                                mentions.append(mention["id"])
                            if (
                                new_message["d"]["mention_everyone"] or
                                bool([i for i in self.my_roles if i in new_message["d"]["mention_roles"]]) or
                                self.my_id in mentions or
                                (new_message_channel_id in self.dms_id)
                            ):
                                self.pings.append({
                                    "channel_id": new_message_channel_id,
                                    "message_id": new_message["d"]["id"],
                                })
                                self.send_desktop_notification(new_message)
                            self.update_tree()
                    # remove ghost pings
                    if op == "MESSAGE_DELETE" and not self.keep_deleted:
                        for num, pinged_channel in enumerate(self.pings):
                            if (
                                new_message_channel_id == pinged_channel["channel_id"] and
                                new_message["d"]["id"] == pinged_channel["message_id"]
                            ):
                                self.pings.pop(num)
                                if self.enable_notifications:
                                    for num_1, notification in enumerate(self.notifications):
                                        if notification["channel_id"] == new_message_channel_id:
                                            notification_id = self.notifications.pop(num_1)["notification_id"]
                                            peripherals.notify_remove(notification_id)
                                            break
                                break
                else:
                    break

            # get new typing
            while self.run:
                new_typing = self.gateway.get_typing()
                if new_typing:
                    if new_typing["channel_id"] == self.active_channel["channel_id"] and new_typing["user_id"] != self.my_id:
                        if not new_typing["username"]:   # its DM
                            for dm in self.dms:
                                if dm["id"] == new_typing["channel_id"]:
                                    new_typing["username"] = dm["username"]
                                    new_typing["global_name"] = dm["global_name"]
                                    # no nick in DMs
                                    break
                        done = False
                        for num, user in enumerate(self.typing):
                            if user["user_id"] == new_typing["user_id"]:
                                self.typing[num]["timestamp"] = new_typing["timestamp"]
                                done = True
                        if not done:
                            self.typing.append(new_typing)
                        self.update_status_line()
                else:
                    break

            # get new summaries
            while self.run:
                new_summary = self.gateway.get_summaries()
                if new_summary:
                    for num, loaded_summary in enumerate(self.summaries):
                        if new_summary["channel_id"] == loaded_summary["channel_id"]:
                            self.summaries[num] = new_summary
                        else:
                            self.summaries.append(new_summary)
                else:
                    break

            # get new message_ack
            while self.run:
                new_message_ack = self.gateway.get_message_ack()
                if new_message_ack:
                    ack_channel_id = new_message_ack["channel_id"]
                    for num_1, unseen_channel in enumerate(self.unseen):
                        if unseen_channel["channel_id"] == ack_channel_id:   # find this unseen chanel
                            self.unseen.pop(num_1)
                            self.update_tree()
                            for num, pinged_channel in enumerate(self.pings):
                                if ack_channel_id == pinged_channel["channel_id"]:
                                    self.pings.pop(num)
                                    break
                            if self.enable_notifications:
                                for num, notification in enumerate(self.notifications):
                                    if notification["channel_id"] == ack_channel_id:
                                        notification_id = self.notifications.pop(num)["notification_id"]
                                        peripherals.notify_remove(notification_id)
                                        break
                            break
                else:
                    break

            # get new rpc
            if self.enable_rpc:
                new_rpc = self.rpc.get_rpc()
                if new_rpc is not None and self.gateway_state == 1:
                    self.my_rpc = new_rpc
                    self.gateway.update_presence(
                        self.my_status["status"],
                        custom_status=self.my_status["custom_status"],
                        custom_status_emoji=self.my_status["custom_status_emoji"],
                        rpc=self.my_rpc,
                    )

            # remove expired typing
            if self.typing:
                for num, user in enumerate(self.typing):
                    if round(time.time()) - user["timestamp"] > 10:
                        self.typing.pop(num)
                        self.update_status_line()

            # send typing event
            if self.send_my_typing:
                my_typing = self.tui.get_my_typing()
                # typing indicator on server expires in 10s, so lest stay safe with 7s
                if my_typing and time.time() >= self.typing_sent + 7:
                    self.discord.send_typing(self.active_channel["channel_id"])
                    self.typing_sent = int(time.time())

            # remove unseen after scrooled to bottom on unseen channel
            if self.unseen_scrolled:
                if text_index == 0:
                    self.unseen_scrolled = False
                    self.update_status_line()
                    self.set_seen(self.active_channel["channel_id"])

            # send pending ack
            if not self.unseen_scrolled and self.pending_ack and time.time() - self.sent_ack_time > self.ack_throttling:
                self.set_seen(self.active_channel["channel_id"], force=True)
                self.sent_ack_time = time.time()
                self.pending_ack = False

            # check gateway state
            gateway_state = self.gateway.get_state()
            if gateway_state != self.gateway_state:
                self.gateway_state = gateway_state
                if self.gateway_state == 1:
                    self.my_status["client_state"] = "online"
                    self.reconnect()
                elif self.gateway_state == 2:
                    self.my_status["client_state"] = "connecting"
                else:
                    self.my_status["client_state"] = "OFFLINE"
                self.update_status_line()

            # check change in dimensions
            new_chat_dim = self.tui.get_dimensions()[0]
            if new_chat_dim != self.chat_dim:
                self.chat_dim = new_chat_dim
                self.update_chat()
                self.update_tree()
                self.update_extra_line()

            # check and update my status
            new_status = self.gateway.get_my_status()
            if new_status:
                self.my_status = {
                    "status": new_status["status"],
                    "custom_status": new_status["custom_status"],
                    "custom_status_emoji": new_status["custom_status_emoji"],
                    "activities": new_status["activities"],
                    "client_state": "online",
                }
                self.update_status_line()

            # check for tree format changes
            self.check_tree_format()

            # check if new chat chunks needs to be downloaded in any direction
            if self.messages:
                if selected_line == 0 and self.messages[0]["id"] != self.last_message_id:
                    self.get_chat_chunk(past=False)
                elif selected_line >= len(self.chat) - 1 and not self.chat_end:
                    self.get_chat_chunk(past=True)

            time.sleep(0.1)   # some reasonable delay
