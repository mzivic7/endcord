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
    parser,
    peripherals,
    perms,
    rpc,
    tui,
)

support_media = (
    importlib.util.find_spec("PIL") is not None and
    importlib.util.find_spec("av") is not None and
    importlib.util.find_spec("numpy") is not None
)
if support_media:
    from endcord import media

logger = logging.getLogger(__name__)
APP_NAME = "endcord"
MESSAGE_UPDATE_ELEMENTS = ("id", "edited", "content", "mentions", "mention_roles", "mention_everyone", "embeds")
MEDIA_EMBEDS = ("image", "gifv", "video", "audio", "rich")
STATUS_STRINGS = ("online", "idle", "dnd", "invisible")
ERROR_TEXT = "\nUnhandled exception occurred. Please report here: https://github.com/mzivic7/endcord/issues"
MSG_MIN = 3   # minimum number of messages that must be sent in official client
SUMMARY_SAVE_INTERVAL = 300   # 5min
LIMIT_SUMMARIES = 5   # max number of summaries per channel

match_emoji = re.compile(r"<:(.*):(\d*)>")


recorder = peripherals.Recorder()


class Endcord:
    """Main app class"""

    def __init__(self, screen, config, keybindings):
        self.screen = screen
        self.config = config

        # load often used values from config
        self.enable_rpc = config["rpc"]
        self.limit_chat_buffer = max(min(config["limit_chat_buffer"], 1000), 50)
        self.msg_num = max(min(config["download_msg"], 100), 20)
        self.limit_typing = max(config["limit_typing_string"], 25)
        self.send_my_typing = config["send_typing"]
        self.ack_throttling = max(config["ack_throttling"], 3)
        self.format_title_line_l = config["format_title_line_l"]
        self.format_title_line_r = config["format_title_line_r"]
        self.format_status_line_l = config["format_status_line_l"]
        self.format_status_line_r = config["format_status_line_r"]
        self.format_title_tree = config["format_title_tree"]
        self.format_rich = config["format_rich"]
        self.reply_mention = config["reply_mention"]
        self.cache_typed = config["cache_typed"]
        self.enable_notifications = config["desktop_notifications"]
        self.notification_sound = config["linux_notification_sound"]
        self.notification_path = config["custom_notification_sound"]
        self.hide_spam = config["hide_spam"]
        self.keep_deleted = config["keep_deleted"]
        self.deleted_cache_limit = config["deleted_cache_limit"]
        self.ping_this_channel = config["notification_in_active"]
        self.username_role_colors = config["username_role_colors"]
        self.save_summaries = config["save_summaries"]
        self.fun = not config["disable_easter_eggs"]
        self.tenor_gif_type = config["tenor_gif_type"]
        self.get_members = config["member_list"]
        self.member_list_auto_open = config["member_list_auto_open"]
        self.member_list_width = config["member_list_width"]
        self.use_nick = config["use_nick_when_available"]
        self.status_char = self.config["tree_dm_status"]
        downloads_path = config["downloads_path"]
        if not downloads_path:
            downloads_path = peripherals.downloads_path
        self.downloads_path = os.path.expanduser(downloads_path)
        if self.notification_path:
            self.notification_path = os.path.expanduser(self.notification_path)
        if not support_media:
            self.config["native_media_player"] = True
        self.colors = color.extract_colors(config)
        self.colors_formatted = color.extract_colors_formatted(config)
        self.default_msg_color = self.colors_formatted[0][0][:]
        self.default_msg_alt_color = self.colors[1]

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
        self.cached_downloads = []
        self.last_summary_save = time.time() - SUMMARY_SAVE_INTERVAL - 1

        # initialize stuff
        self.discord = discord.Discord(
            config["token"],
            config["custom_host"],
            config["proxy"],
        )
        self.gateway = gateway.Gateway(
            config["token"],
            config["custom_host"],
            config["proxy"],
        )
        self.downloader = downloader.Downloader(config["proxy"])
        self.tui = tui.TUI(self.screen, self.config, keybindings)
        self.colors = self.tui.init_colors(self.colors)
        self.colors_formatted = self.tui.init_colors_formatted(self.colors_formatted, self.default_msg_alt_color)
        self.tui.update_chat(["Connecting to Discord"], [[[self.colors[0]]]] * 1)
        self.tui.update_status_line("CONNECTING")
        self.my_id = self.discord.get_my_id()
        self.premium = None
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
        self.extra_window_open = False
        self.extra_indexes = []
        self.extra_body = []
        self.viewing_user_data = {"id": None, "guild_id": None}
        self.hidden_channels = []
        self.current_subscribed_members = []
        self.recording = False
        self.member_list_visible = False
        self.assist_word = None
        self.assist_type = None
        self.assist_found = []
        self.restore_input_text = [None, None]
        self.extra_bkp = None
        self.reset_actions()
        self.gateway.set_want_member_list(self.get_members)
        self.gateway.set_want_summaries(self.save_summaries)
        # threading.Thread(target=self.profiling_auto_exit, daemon=True).start()
        self.main()


    def profiling_auto_exit(self):
        """Thread that waits then exits cleanly, so profiler (vprof) can process data"""
        time.sleep(20)
        self.run = False


    def reset(self, online=False):
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
        self.downloader.cancel()
        self.download_threads = []
        self.upload_threads = []
        self.ready_attachments = []
        self.selected_attachment = 0
        self.member_roles = []
        self.current_member_roles = []
        self.threads = []
        self.activities = []
        self.search_messages = []
        self.members = []
        self.subscribed_members = []
        self.current_members = []
        self.forum = False
        self.disable_sending = False
        self.extra_line = None
        self.search = False
        self.search_end = False
        self.command = False
        self.ignore_typing = False
        if not online:
            self.my_status = {
                "status": "online",
                "custom_status": None,
                "custom_status_emoji": None,
                "activities": [],
                "client_state": "OFFLINE",
            }


    def reconnect(self):
        """Fetch updated data from gateway and rebuild chat after reconnecting"""
        self.add_running_task("Reconnecting", 1)
        self.reset(online=True)
        self.premium = self.gateway.get_premium()
        self.guilds = self.gateway.get_guilds()
        # not initializing role colors again to avoid issues with media colors
        self.dms, self.dms_vis_id = self.gateway.get_dms()
        if self.hide_spam:
            for dm in self.dms:
                if dm["is_spam"]:
                    self.dms_vis_id.remove(dm["id"])
                    self.dms.remove(dm)
                elif dm["muted"]:
                    self.dms_vis_id.remove(dm["id"])
        new_activities = self.gateway.get_dm_activities()
        if new_activities:
            self.activities = new_activities
            self.update_tree()
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
        self.gateway.subscribe(
            self.active_channel["channel_id"],
            self.active_channel["guild_id"],
        )
        self.update_chat(keep_selected=False)
        self.update_tree()

        self.remove_running_task("Reconnecting", 1)
        logger.info("Reconnect complete")


    def switch_channel(self, channel_id, channel_name, guild_id, guild_name, parent_hint=None, open_member_list=False):
        """
        All that should be done when switching channel.
        If it is DM, guild_id and guild_name should be None.
        """

        # dont switch to same channel
        if channel_id == self.active_channel["channel_id"]:
            return

        # dont switch when offline
        if self.my_status["client_state"] in ("OFFLINE", "connecting"):
            self.update_extra_line("Can't switch channel when offline.")
            return

        logger.debug(f"Switching channel, has_id: {bool(channel_id)}, has_guild:{bool(guild_id)}, has hint: {bool(parent_hint)}")

        # save deleted
        if self.keep_deleted:
            self.cache_deleted()

        # check if should open member list
        if self.member_list_auto_open and guild_id != self.active_channel["guild_id"]:
            open_member_list = True

        # clear member roles when switching guild so there are no issues with same members in both guilds
        if guild_id != self.active_channel["guild_id"]:
            self.current_member_roles = []

        # update active channel
        self.active_channel["guild_id"] = guild_id
        self.active_channel["guild_name"] = guild_name
        self.active_channel["channel_id"] = channel_id
        self.active_channel["channel_name"] = channel_name
        self.add_running_task("Switching channel", 1)

        # update list of this guild channels
        current_channels = []
        for guild_channels in self.guilds:
            if guild_channels["guild_id"] == guild_id:
                current_channels = guild_channels["channels"]
                break
        current_channel = {}
        for channel in current_channels:
            if channel["id"] == channel_id:
                current_channel = channel
                break

        # check threads if no channel
        else:
            if parent_hint:   # thread will have parent_hint
                for guild in self.threads:
                    if guild["guild_id"] == guild_id:
                        for channel in guild["channels"]:
                            if channel["channel_id"] == parent_hint:
                                for thread in channel["threads"]:
                                    if thread["id"] == channel_id:
                                        current_channel = thread
                                        break
                                break
                        break

        # generate forum
        if current_channel.get("type") == 15:
            self.forum = True
            self.update_forum(guild_id, channel_id)

        # fetch messages
        # also used to check network
        else:
            self.forum = False
            self.messages = self.get_messages_with_members(num=self.msg_num)
            if self.messages:
                self.last_message_id = self.messages[0]["id"]
            elif self.messages is None:
                self.remove_running_task("Switching channel", 1)
                logger.warn("Channel switching failed")
                return

        # if not failed
        self.current_channels = current_channels
        self.current_channel = current_channel

        # if this is dm, check if user has sent minimum number of messages
        # this is to prevent triggering discords spam filter
        if not guild_id and len(self.messages) < self.msg_num:
            # if there is less than self.msg_num messages, this is the start of conversation
            # so count all messages sent from this user
            my_messages = 0
            for message in self.messages:
                if message["user_id"] == self.my_id:
                    my_messages += 1
                    if my_messages >= MSG_MIN:
                        break
            if my_messages < MSG_MIN:
                self.disable_sending = f"Can't send a message: please send at least {MSG_MIN} messages with the official client"

        # if this is thread and is locked or archived, prevent sending messages
        elif self.current_channel.get("type") in (11, 12) and self.current_channel.get("locked"):
            self.disable_sending = "Can't send a message: this thread is locked"
        elif not self.current_channel.get("allow_write", True):
            self.disable_sending = "Can't send a message: No write permissions"
        else:
            self.disable_sending = False
            self.tui.remove_extra_line()

        # misc
        self.typing = []
        self.chat_end = False
        self.selected_attachment = 0
        self.gateway.subscribe(channel_id, guild_id)
        self.gateway.set_active_channel(channel_id)
        if not self.forum:
            self.set_seen(channel_id)
        if self.recording:
            self.recording = False
            _ = recorder.stop()

        # select guild member activities
        if guild_id:
            if self.get_members:
                for guild in self.members:
                    if guild["guild_id"] == self.active_channel["guild_id"]:
                        self.current_members = guild["members"]
                        break
                else:
                    self.current_members = []
            for guild in self.subscribed_members:
                if guild["guild_id"] == self.active_channel["guild_id"]:
                    self.current_subscribed_members = guild["members"]
                    break
                else:
                    self.current_subscribed_members = []

        # manage roles
        if guild_id:   # for guilds only
            # 255_curses_bug - make it run on init only
            self.all_roles = self.tui.init_role_colors(
                self.all_roles,
                self.default_msg_color[1],
                self.default_msg_alt_color[1],
                guild_id=guild_id,
            )
        self.current_roles = []   # dm has no roles
        for roles in self.all_roles:
            if roles["guild_id"] == guild_id:
                self.current_roles = roles["roles"]
                break
        self.current_my_roles = []   # user has no roles in dm
        for roles in self.my_roles:
            if roles["guild_id"] == guild_id:
                self.current_my_roles = roles["roles"]
                break
        self.select_current_member_roles()

        # update UI
        if not self.forum:
            self.update_chat(keep_selected=False)
        else:
            self.tui.update_chat(self.chat, self.chat_format)
        if not guild_id:   # no member list in dms
            self.member_list_visible = False
            self.tui.remove_member_list()
        elif self.member_list_visible or open_member_list:
            self.member_list_visible = True
            self.update_member_list()
        self.close_extra_window()
        if self.disable_sending:
            self.update_extra_line(self.disable_sending)
        else:
            self.update_extra_line()
        self.update_prompt()
        self.update_tree()

        # save state (exclude threads)
        if self.config["remember_state"] and self.current_channel.get("type") not in (11, 12, 15):
            self.state["last_guild_id"] = guild_id
            self.state["last_channel_id"] = channel_id
            peripherals.save_json(self.state, "state.json")

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
            collapsed = self.state["collapsed"][:]
        # toggle only this guild
        elif collapse and guild_id not in self.state["collapsed"]:
            collapsed = self.state["collapsed"][:]
            collapsed.append(guild_id)
        elif not collapse and guild_id in self.state["collapsed"]:
            collapsed = self.state["collapsed"][:]
            collapsed.remove(guild_id)

        self.update_tree(collapsed=collapsed)

        # keep this guild selected
        if self.config["only_one_open_server"] and select:
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
        else:
            self.current_member_roles = []


    def add_to_store(self, channel_id, text):
        """Adds entry to input line store"""
        if self.cache_typed:
            for num, channel in enumerate(self.input_store):
                if channel["id"] == channel_id:
                    self.input_store[num]["content"] = text
                    break
            else:
                self.input_store.append({
                    "id": channel_id,
                    "content": text,
                })


    def reset_actions(self):
        """Reset all actions"""
        self.replying = {
            "id": None,
            "username": None,
            "global_name": None,
            "mention": None,
        }
        self.editing = None
        self.deleting = None
        self.downloading_file = {
            "urls": None,
            "web": False,
            "open": False,
        }
        self.cancel_download = False
        self.uploading = False
        self.hiding_ch = {
            "channel_name": None,
            "channel_id": None,
            "guild_id": None,
        }
        self.reacting = {
            "id": None,
            "msg_index": None,
            "username": None,
            "global_name": None,
        }
        self.view_reactions = {
            "message_id": None,
            "reactions": [],
        }
        self.going_to_ch = None
        self.ignore_typing = False
        self.tui.typing = time.time() - 5


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


    def channel_name_from_id(self, channel_id):
        """Get channel name from its id"""
        for channel in self.current_channels:
            if channel["id"] == channel_id:
                return channel["name"]
        return None


    def wait_input(self):
        """Thread that handles: getting input, formatting, sending, replying, editing, deleting message and switching channel"""
        logger.info("Input handler loop started")

        while self.run:
            if self.forum:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input_forum(self.prompt)
                input_text = ""
            elif self.restore_input_text[1] == "prompt":
                self.restore_input_text = [None, "after_prompt"]
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt)
            elif self.restore_input_text[1] == "standard":
                init_text = self.restore_input_text[0]
                self.restore_input_text = [None, None]
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=init_text, reset=False, keep_cursor=True)
            elif self.restore_input_text[1] == "autocomplete":
                self.restore_input_text = [None, None]
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, autocomplete=True)
            elif self.restore_input_text[1] in ("search", "command", "react", "edit"):
                init_text = self.restore_input_text[0]
                prompt_text = self.restore_input_text[1].upper()
                self.restore_input_text = [None, None]
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(f"[{prompt_text}] > ", init_text=init_text)
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
            logger.debug(f"Input code: {action}")

            # switch channel
            if action == 4:
                if input_text and input_text != "\n":
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                sel_channel = self.tree_metadata[tree_sel]
                guild_id, parent_id, guild_name = self.find_parents(tree_sel)
                self.switch_channel(sel_channel["id"], sel_channel["name"], guild_id, guild_name, parent_hint=parent_id)
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
                        "username": self.messages[msg_index]["username"],
                        "global_name": self.messages[msg_index]["global_name"],
                        "mention": mention,
                    }
                self.restore_input_text = [input_text, "standard"]
                self.update_status_line()

            # set edit
            elif action == 2 and self.messages:
                self.restore_input_text = [input_text, "standard"]
                msg_index = self.lines_to_msg(chat_sel)
                if self.messages[msg_index]["user_id"] == self.my_id:
                    if "deleted" not in self.messages[msg_index]:
                        self.reset_actions()
                        self.editing = self.messages[msg_index]["id"]
                        self.add_to_store(self.active_channel["channel_id"], input_text)
                        self.restore_input_text = [self.messages[msg_index]["content"], "edit"]
                        self.update_status_line()

            # set delete
            elif action == 3 and self.messages:
                self.restore_input_text = [input_text, "standard"]
                msg_index = self.lines_to_msg(chat_sel)
                if self.messages[msg_index]["user_id"] == self.my_id:
                    if "deleted" not in self.messages[msg_index]:
                        self.reset_actions()
                        self.ignore_typing = True
                        self.deleting = self.messages[msg_index]["id"]
                        self.add_to_store(self.active_channel["channel_id"], input_text)
                        self.restore_input_text = [None, "prompt"]
                        self.update_status_line()

            # toggle mention ping
            elif action == 6:
                self.restore_input_text = [input_text, "standard"]
                self.replying["mention"] = None if self.replying["mention"] is None else not self.replying["mention"]
                self.update_status_line()

            # warping to chat bottom
            elif action == 7 and self.messages:
                self.restore_input_text = [input_text, "standard"]
                self.go_bottom()

            # go to replied message
            elif action == 8 and self.messages:
                self.restore_input_text = [input_text, "standard"]
                msg_index = self.lines_to_msg(chat_sel)
                self.go_replied(msg_index)

            # download file
            elif action == 9:
                msg_index = self.lines_to_msg(chat_sel)
                urls = []
                for embed in self.messages[msg_index]["embeds"]:
                    if embed["url"]:
                        urls.append(embed["url"])
                if len(urls) == 1:
                    self.restore_input_text = [input_text, "standard"]
                    self.download_threads.append(threading.Thread(target=self.download_file, daemon=True, args=(urls[0], )))
                    self.download_threads[-1].start()
                elif len(urls) > 1:
                    self.ignore_typing = True
                    self.downloading_file = {
                        "urls": urls,
                        "web": False,
                        "open": False,
                    }
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.restore_input_text = [None, "prompt"]
                    self.update_status_line()

            # open link in browser
            elif action == 10:
                msg_index = self.lines_to_msg(chat_sel)
                urls = self.get_msg_urls(msg_index)
                if len(urls) == 1:
                    self.restore_input_text = [input_text, "standard"]
                    webbrowser.open(urls[0], new=0, autoraise=True)
                elif len(urls) > 1:
                    self.ignore_typing = True
                    self.downloading_file = {
                        "urls": urls,
                        "web": True,
                        "open": False,
                    }
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.restore_input_text = [None, "prompt"]
                    self.update_status_line()

            # download and open media attachment
            elif action == 17 and support_media:
                msg_index = self.lines_to_msg(chat_sel)
                urls, media_type = self.get_msg_media(msg_index)
                if len(urls) == 1:
                    logger.debug(f"Trying to play attachment with type: {media_type}")
                    self.restore_input_text = [input_text, "standard"]
                    self.download_threads.append(threading.Thread(target=self.download_file, daemon=True, args=(urls[0], False, True)))
                    self.download_threads[-1].start()
                elif len(urls) > 1:
                    self.downloading_file = {
                        "urls": urls,
                        "web": False,
                        "open": True,
                    }
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.restore_input_text = [None, "prompt"]
                    self.update_status_line()

            # cancel all downloads and uploads
            elif action == 11:
                self.add_to_store(self.active_channel["channel_id"], input_text)
                self.restore_input_text = [None, "prompt"]
                self.reset_actions()
                self.ignore_typing = True
                self.cancel_download = True
                self.update_status_line()

            # copy message to clipboard
            elif action == 12 and self.messages:
                self.restore_input_text = [input_text, "standard"]
                msg_index = self.lines_to_msg(chat_sel)
                peripherals.copy_to_clipboard(self.messages[msg_index]["content"])

            # upload attachment
            elif action == 13 and self.messages and not self.disable_sending:
                self.restore_input_text = [None, "autocomplete"]
                self.add_to_store(self.active_channel["channel_id"], input_text)
                if self.current_channel.get("allow_attach", True):
                    if self.recording:   # stop recording voice message
                        self.recording = False
                        _ = recorder.stop()
                    self.uploading = True
                    self.ignore_typing = True
                    self.update_status_line()

            # moving left/right through attachments
            elif action == 14:
                self.restore_input_text = [input_text, "standard"]
                if self.selected_attachment > 0:
                    self.selected_attachment -= 1
                    self.update_extra_line()
            elif action == 15:
                self.restore_input_text = [input_text, "standard"]
                num_attachments = 0
                for attachments in self.ready_attachments:
                    if attachments["channel_id"] == self.active_channel["channel_id"]:
                        num_attachments = len(attachments["attachments"])
                if self.selected_attachment + 1 < num_attachments:
                    self.selected_attachment += 1
                    self.update_extra_line()

            # cancel selected attachment
            elif action == 16:
                self.restore_input_text = [input_text, "standard"]
                self.cancel_attachment()
                self.update_extra_line()

            # reveal one-by-one spoiler in a message
            elif action == 18:
                self.restore_input_text = [input_text, "standard"]
                msg_index = self.lines_to_msg(chat_sel)
                self.spoil(msg_index)

            # open guild in tree
            elif action == 19:
                self.restore_input_text = [input_text, "standard"]
                guild_id = self.tree_metadata[tree_sel]["id"]
                self.open_guild(guild_id, select=True)

            # copy/cut on input line
            elif action == 20:
                self.restore_input_text = [input_text, "standard"]
                peripherals.copy_to_clipboard(self.tui.input_select_text)

            # join/leave selected thread in tree
            elif action == 21:
                self.restore_input_text = [input_text, "standard"]
                if self.tree_metadata[tree_sel]["type"] in (11, 12):
                    # find threads parent channel and guild
                    thread_id = self.tree_metadata[tree_sel]["id"]
                    guild_id, channel_id, _ = self.find_parents(tree_sel)
                    # toggle joined
                    self.thread_togle_join(guild_id, channel_id, thread_id)
                    self.update_tree()

            # open thread from forum
            elif action == 22 and "owner_id" in self.messages[chat_sel]:
                if input_text and input_text != "\n":
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                # failsafe if messages got rewritten
                self.switch_channel(
                    self.messages[chat_sel]["id"],
                    self.messages[chat_sel]["name"],
                    self.active_channel["guild_id"],
                    self.active_channel["guild_name"],
                    parent_hint=self.active_channel["channel_id"],
                )
                self.reset_actions()
                self.update_status_line()

            # open and join thread from forum
            elif action == 23 and "owner_id" in self.messages[chat_sel]:
                if input_text and input_text != "\n":
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                # failsafe if messages got rewritten
                self.switch_channel(
                    self.messages[chat_sel]["id"],
                    self.messages[chat_sel]["name"],
                    self.active_channel["guild_id"],
                    self.active_channel["guild_name"],
                    parent_hint=self.active_channel["channel_id"],
                )
                self.reset_actions()
                self.update_status_line()
                self.thread_togle_join(guild_id, channel_id, thread_id, join=True)

            # view profile info
            elif action == 24:
                self.restore_input_text = [input_text, "standard"]
                msg_index = self.lines_to_msg(chat_sel)
                user_id = self.messages[msg_index]["user_id"]
                guild_id = self.active_channel["guild_id"]
                if self.viewing_user_data["id"] != user_id or self.viewing_user_data["guild_id"] != guild_id:
                    if guild_id:
                        self.viewing_user_data = self.discord.get_user_guild(user_id, guild_id)
                    else:
                        self.viewing_user_data = self.discord.get_user(user_id)
                self.stop_assist(close=False)
                self.view_profile(self.viewing_user_data)

            # view channel info
            elif action == 25:
                self.restore_input_text = [input_text, "standard"]
                self.view_selected_channel(tree_sel=tree_sel)

            # hide selected channel locally, with a prompt
            elif action == 26:
                ch_type = self.tree_metadata[tree_sel]["type"]
                if ch_type not in (-1, 1, 11, 12):
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.restore_input_text = [None, "prompt"]
                    self.reset_actions()
                    self.ignore_typing = True
                    guild_id = self.find_parents(tree_sel)[0]
                    self.hiding_ch = {
                        "channel_name": self.tree_metadata[tree_sel]["name"],
                        "channel_id": self.tree_metadata[tree_sel]["id"],
                        "guild_id": guild_id,
                    }
                    self.update_status_line()
                else:
                    self.restore_input_text = [input_text, "standard"]

            # select in extra window / memeber list
            elif action == 27:
                self.restore_input_text = [input_text, "standard"]
                if self.extra_window_open:
                    if self.extra_indexes:
                        extra_selected = self.tui.get_extra_selected()
                        if extra_selected < 0:
                            continue
                        total_len = 0
                        for num, item in enumerate(self.extra_indexes):
                            total_len += item["lines"]
                            if total_len >= extra_selected + 1:
                                message_id = item["message_id"]
                                channel_id = item.get("channel_id")
                                break
                        else:
                            continue
                        if channel_id and channel_id != self.active_channel["channel_id"]:
                            guild_id = self.active_channel["guild_id"]
                            guild_name = self.active_channel["guild_name"]
                            channel_name = self.channel_name_from_id(channel_id)
                            self.switch_channel(channel_id, channel_name, guild_id, guild_name)
                        self.go_to_message(message_id)
                        self.close_extra_window()
                    elif self.assist_found:
                        new_input_text, new_index = self.insert_assist(
                            input_text,
                            self.tui.get_extra_selected(),
                            self.tui.assist_start,
                            self.tui.input_index,
                        )
                        if new_input_text:
                            if self.search and self.extra_bkp:
                                self.restore_input_text = [new_input_text, "search"]
                                self.ignore_typing = True
                            elif self.command and self.extra_bkp:
                                self.restore_input_text = [new_input_text, "command"]
                                self.ignore_typing = True
                                self.tui.instant_assist = True
                            else:
                                self.restore_input_text = [new_input_text, "standard"]
                            self.tui.set_input_index(new_index)
                elif self.member_list_visible:   # controls for memeber list when no extra window
                    member = self.current_members[self.tui.get_extra_selected()]
                    if "id" in member:
                        user_id = member["id"]
                        guild_id = self.active_channel["guild_id"]
                        if self.viewing_user_data["id"] != user_id or self.viewing_user_data["guild_id"] != guild_id:
                            if guild_id:
                                self.viewing_user_data = self.discord.get_user_guild(user_id, guild_id)
                            else:
                                self.viewing_user_data = self.discord.get_user(user_id)
                        self.view_profile(self.viewing_user_data)

            # view summaries
            elif action == 28:
                self.restore_input_text = [input_text, "standard"]
                self.show_summaries()

            # search
            elif action == 29:
                if not self.search:
                    self.reset_actions()
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.restore_input_text = [None, "search"]
                    self.search = True
                    self.ignore_typing = True
                    max_w = self.tui.get_dimensions()[2][1]
                    extra_title, extra_body = formatter.generate_extra_window_text("Search:", formatter.SEARCH_HELP_TEXT, max_w)
                    self.stop_assist(close=False)
                    self.tui.draw_extra_window(extra_title, extra_body)
                    self.extra_window_open = True
                else:
                    self.close_extra_window()
                    self.reset_actions()
                    self.search = False
                    self.search_end = False
                    self.search_messages = []
                    self.update_status_line()
                    self.stop_assist()

            # copy channel link
            elif action == 30:
                self.restore_input_text = [input_text, "standard"]
                guild_id = self.active_channel["guild_id"]
                channel_id = self.tree_metadata[tree_sel]["id"]
                if guild_id:
                    url = f"https://{self.discord.host}/channels/{guild_id}/{channel_id}"
                    peripherals.copy_to_clipboard(url)

            # copy message link
            elif action == 31 and self.messages:
                self.restore_input_text = [input_text, "standard"]
                msg_index = self.lines_to_msg(chat_sel)
                self.copy_msg_url(msg_index)

            # go to channel/message mentioned in this message
            elif action == 32:
                self.restore_input_text = [input_text, "standard"]
                channels = []
                msg_index = self.lines_to_msg(chat_sel)
                message_text = self.messages[msg_index]["content"]
                mention_msg = self.messages[msg_index].get("mention_msg")
                msg_num = 0
                for match in re.finditer(formatter.match_channel_id_msg_group, message_text):
                    if match.group(2) and msg_num < len(mention_msg):
                        message_id = mention_msg[msg_num]
                        msg_num += 1
                    else:
                        message_id = None
                    channels.append([match.group(1), message_id])
                if not channels:
                    continue
                if len(channels) == 1:
                    channel_id = channels[0][0]
                    message_id = channels[0][1]
                    channel_name = self.channel_name_from_id(channel_id)
                    if channel_name:
                        self.switch_channel(channel_id, channel_name, self.active_channel["guild_id"], self.active_channel["guild_name"])
                        if message_id:
                            self.go_to_message(message_id)
                else:
                    self.reset_actions()
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.ignore_typing = True
                    self.going_to_ch = channels
                    self.update_status_line()

            # cycle status
            elif action == 33:
                self.restore_input_text = [input_text, "standard"]
                if self.my_status["client_state"] == "online":
                    for num, status in enumerate(STATUS_STRINGS):
                        if status == self.my_status["status"]:
                            if num == len(STATUS_STRINGS) - 1:
                                new_status = STATUS_STRINGS[0]
                            else:
                                new_status = STATUS_STRINGS[num+1]
                            break
                    self.set_status(new_status)

            # record audio message
            elif action == 34 and self.messages and not self.disable_sending and not self.uploading:
                self.restore_input_text = [input_text, "standard"]
                if self.recording:
                    self.stop_recording()
                else:
                    self.start_recording()

            # toggle member list
            elif self.get_members and action == 35:
                self.restore_input_text = [input_text, "standard"]
                self.toggle_member_list()

            # add reaction
            elif action == 36 and self.messages:
                msg_index = self.lines_to_msg(chat_sel)
                self.add_to_store(self.active_channel["channel_id"], input_text)
                if "deleted" not in self.messages[msg_index]:
                    self.restore_input_text = [None, "react"]
                    self.ignore_typing = True
                    self.reacting = {
                        "id": self.messages[msg_index]["id"],
                        "msg_index": msg_index,
                        "username": self.messages[msg_index]["username"],
                        "global_name": self.messages[msg_index]["global_name"],
                    }
                    self.update_status_line()

            # show detailed reactions
            elif action == 37 and self.messages:
                self.restore_input_text = [input_text, "standard"]
                msg_index = self.lines_to_msg(chat_sel)
                multiple = self.do_view_reactions(msg_index)
                if multiple:
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.restore_input_text = [None, "prompt"]

            # command
            elif action == 38:
                if not self.command:
                    self.update_extra_line()
                    self.reset_actions()
                    self.add_to_store(self.active_channel["channel_id"], input_text)
                    self.restore_input_text = [None, "command"]
                    self.command = True
                    self.ignore_typing = True
                    max_w = self.tui.get_dimensions()[2][1]
                    extra_title, extra_body = formatter.generate_extra_window_assist(formatter.COMMAND_ASSISTS, 5, max_w)
                    self.stop_assist(close=False)
                    self.assist_found = formatter.COMMAND_ASSISTS
                    self.assist_word = " "
                    self.assist_type = 5
                    self.tui.instant_assist = True
                    self.tui.draw_extra_window(extra_title, extra_body, select=True, start_zero=True)
                    self.extra_window_open = True
                    self.extra_bkp = (self.tui.extra_window_title, self.tui.extra_window_body)
                else:
                    self.tui.instant_assist = False
                    self.close_extra_window()
                    self.reset_actions()
                    self.command = False
                    self.update_status_line()
                    self.stop_assist()

            # escape in main UI
            elif action == 5:
                if self.recording:
                    self.stop_recording(cancel=True)
                elif self.reacting["id"]:
                    self.reset_actions()
                    self.restore_input_text = [None, None]
                elif self.assist_word and not self.tui.instant_assist:
                    if self.search:
                        self.restore_input_text = [input_text, "search"]
                    elif self.command:
                        self.restore_input_text = [input_text, "command"]
                    else:
                        self.restore_input_text = [input_text, "standard"]
                elif self.extra_window_open:
                    self.tui.instant_assist = False
                    self.close_extra_window()
                    if self.search or self.command:
                        self.reset_actions()
                    self.search = False
                    self.search_end = False
                    self.search_messages = []
                    self.command = False
                elif self.replying["id"]:
                    self.reset_actions()
                elif self.editing:
                    self.restore_input_text = [None, None]
                    self.reset_actions()
                elif self.restore_input_text[1] == "after_prompt":
                    self.reset_actions()
                    self.restore_input_text = [None, None]
                else:
                    self.update_extra_line()
                    self.reset_actions()
                    self.restore_input_text = [input_text, "standard"]
                self.update_status_line()
                self.stop_assist()

            # media controls
            elif action >= 100:
                self.curses_media.control_codes(action)

            # enter
            elif (action == 0 and input_text and input_text != "\n" and self.active_channel["channel_id"]) or self.command:
                if self.assist_word and self.assist_found:
                    self.restore_input_text = [input_text, "standard"]
                    new_input_text, new_index = self.insert_assist(
                        input_text,
                        self.tui.get_extra_selected(),
                        self.tui.assist_start,
                        self.tui.input_index,
                    )
                    if not self.reacting:
                        self.reset_actions()
                        self.update_status_line()
                    if new_input_text:
                        if self.search and self.extra_bkp:
                            self.restore_input_text = [new_input_text, "search"]
                            self.ignore_typing = True
                        elif self.command and self.extra_bkp:
                            self.restore_input_text = [new_input_text, "command"]
                            self.ignore_typing = True
                        elif self.reacting["id"]:
                            self.restore_input_text = [new_input_text, "react"]
                            self.ignore_typing = True
                        else:
                            self.restore_input_text = [new_input_text, "standard"]
                        self.tui.set_input_index(new_index)
                    continue

                # message will be received from gateway and then added to self.messages
                if input_text.lower() != "y" and (self.deleting or self.cancel_download or self.hiding_ch["channel_id"]):
                    # anything not "y" when asking for "[Y/n]"
                    self.reset_actions()
                    self.update_status_line()
                    continue

                if self.editing:
                    text_to_send = emoji.emojize(input_text, language="alias", variant="emoji_type")
                    self.discord.send_update_message(
                        channel_id=self.active_channel["channel_id"],
                        message_id=self.editing,
                        message_content=text_to_send,
                    )

                elif self.deleting and input_text.lower() == "y":
                    self.discord.send_delete_message(
                        channel_id=self.active_channel["channel_id"],
                        message_id=self.deleting,
                    )

                elif self.downloading_file["urls"]:
                    urls = self.downloading_file["urls"]
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
                    self.downloader.cancel()
                    self.download_threads = []
                    self.cancel_upload()
                    self.upload_threads = []

                elif self.uploading:
                    self.upload_threads.append(threading.Thread(target=self.upload, daemon=True, args=(input_text, )))
                    self.upload_threads[-1].start()

                elif self.search:
                    self.do_search(input_text)
                    self.restore_input_text = [None, "search"]
                    self.reset_actions()
                    self.ignore_typing = True
                    self.update_status_line()
                    continue

                elif self.command:
                    self.tui.instant_assist = False
                    command_type, command_args = parser.command_string(input_text)
                    self.close_extra_window()
                    self.execute_command(command_type, command_args, chat_sel, tree_sel)
                    self.command = False
                    continue

                elif self.reacting["id"]:
                    self.build_reaction(input_text)

                elif self.hiding_ch["channel_id"] and input_text.lower() == "y":
                    channel_id = self.hiding_ch["channel_id"]
                    guild_id = self.hiding_ch["guild_id"]
                    self.hide_channel(channel_id, guild_id)
                    self.hidden_channels.append({
                        "channel_name": self.hiding_ch["channel_name"],
                        "channel_id": channel_id,
                        "guild_id": guild_id,
                        })
                    peripherals.save_json(self.hidden_channels, "hidden_channels.json")
                    self.update_tree()

                elif self.going_to_ch:
                    try:
                        num = max(int(input_text) - 1, 0)
                    except ValueError:
                        self.reset_actions()
                        self.update_status_line()
                        continue
                    if num <= len(self.going_to_ch):
                        channel_id = self.going_to_ch[num][0]
                        message_id = self.going_to_ch[num][1]
                        channel_name = self.channel_name_from_id(channel_id)
                        self.switch_channel(channel_id, channel_name, self.active_channel["guild_id"], self.active_channel["guild_name"])
                        if message_id:
                            self.go_to_message(message_id)

                elif self.view_reactions["message_id"]:
                    reactions = self.view_reactions["reactions"]
                    try:
                        num = max(int(input_text) - 1, 0)
                        if num <= len(reactions):
                            if reactions[num]["emoji_id"]:
                                reaction = f"{reactions[num]["emoji"]}:{reactions[0]["emoji_id"]}"
                            else:
                                reaction = reactions[num]["emoji"]
                            reaction_details = self.discord.get_reactions(
                                self.active_channel["channel_id"],
                                self.view_reactions["message_id"],
                                reaction,
                                )
                            self.stop_assist(close=False)
                            max_w = self.tui.get_dimensions()[2][1]
                            extra_title, extra_body = formatter.generate_extra_window_reactions(reactions[num], reaction_details, max_w)
                            self.tui.draw_extra_window(extra_title, extra_body)
                            self.extra_window_open = True
                    except ValueError:
                        pass

                else:
                    this_attachments = None
                    for num, attachments in enumerate(self.ready_attachments):
                        if attachments["channel_id"] == self.active_channel["channel_id"]:
                            this_attachments = self.ready_attachments.pop(num)["attachments"]
                            self.update_extra_line()
                            break
                    if not self.disable_sending:
                        # if this is unjoined thread, join it (locally only)
                        if self.current_channel.get("type") in (11, 12) and not self.current_channel.get("joined"):
                            self.thread_togle_join(guild_id, channel_id, thread_id, join=True)
                        # search for stickers
                        stickers = []
                        for match in re.finditer(formatter.match_sticker_id, input_text):
                            stickers.append(match.group()[2:-2])
                            input_text = input_text[:match.start()] + input_text[match.end():]
                        text_to_send = emoji.emojize(input_text, language="alias", variant="emoji_type")
                        if self.fun and ("xyzzy" in text_to_send or "XYZZY" in text_to_send):
                            self.update_extra_line("Nothing happens.")
                        self.discord.send_message(
                            self.active_channel["channel_id"],
                            text_to_send,
                            reply_id=self.replying["id"],
                            reply_channel_id=self.active_channel["channel_id"],
                            reply_guild_id=self.active_channel["guild_id"],
                            reply_ping=self.replying["mention"],
                            attachments=this_attachments,
                            stickers=stickers,
                        )

                self.reset_actions()
                self.update_status_line()

            # enter with no text
            elif input_text == "":
                if self.deleting:
                    self.discord.send_delete_message(
                        channel_id=self.active_channel["channel_id"],
                        message_id=self.deleting,
                    )
                elif self.cancel_download:
                    self.downloader.cancel()
                    self.download_threads = []
                    self.cancel_upload()
                    self.upload_threads = []
                elif self.ready_attachments:
                    this_attachments = None
                    for num, attachments in enumerate(self.ready_attachments):
                        if attachments["channel_id"] == self.active_channel["channel_id"]:
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
                elif self.hiding_ch["channel_id"]:
                    channel_id = self.hiding_ch["channel_id"]
                    guild_id = self.hiding_ch["guild_id"]
                    self.hide_channel(channel_id, guild_id)
                    self.hidden_channels.append({
                        "channel_name": self.hiding_ch["channel_name"],
                        "channel_id": channel_id,
                        "guild_id": guild_id,
                        })
                    peripherals.save_json(self.hidden_channels, "hidden_channels.json")
                    self.update_tree()
                elif self.recording:
                    self.recording = False
                    file_path = recorder.stop()
                    self.update_extra_line()
                    if not self.disable_sending:
                        self.add_running_task("Uploading file", 2)
                        self.discord.send_voice_message(
                            self.active_channel["channel_id"],
                            file_path,
                            reply_id=self.replying["id"],
                            reply_channel_id=self.active_channel["channel_id"],
                            reply_guild_id=self.active_channel["guild_id"],
                            reply_ping=self.replying["mention"],
                        )
                        self.remove_running_task("Uploading file", 2)
                self.reset_actions()
                self.update_status_line()


    def execute_command(self, cmd_type, cmd_args, chat_sel, tree_sel):
        """Execute custom command"""
        logger.debug(f"Executig command, type: {cmd_type}, args: {cmd_args}")
        reset = True
        self.restore_input_text = [None, None]
        if cmd_type == 0:
            if cmd_args:
                self.update_extra_line("Invalid command arguments.")
            else:
                self.update_extra_line("Unknown command.")

        elif cmd_type == 1:   # SET
            key = cmd_args["key"]
            value = cmd_args["value"]
            if key in self.config and key != "token":
                self.update_extra_line("Restart needed for changes to take effect.")
                self.config = peripherals.update_config(self.config, key, value)
            else:
                self.update_extra_line("Unknow settings key.")

        elif cmd_type == 2:   # BOTTOM
            self.go_bottom()

        elif cmd_type == 3:   # GO_REPLY
            msg_index = self.lines_to_msg(chat_sel)
            self.go_replied(msg_index)

        elif cmd_type == 4:   # DOWNLOAD
            msg_index = self.lines_to_msg(chat_sel)
            urls = []
            for embed in self.messages[msg_index]["embeds"]:
                if embed["url"]:
                    urls.append(embed["url"])
            select_num = cmd_args.get("num", 0)
            if select_num > 0 and select_num <= len(urls):
                select_num -= 1
            else:
                select_num = None
            if len(urls) == 1 or select_num is not None:
                if select_num is None:
                    select_num = 0
                self.download_threads.append(threading.Thread(target=self.download_file, daemon=True, args=(urls[select_num], )))
                self.download_threads[-1].start()
            elif len(urls) > 1:
                self.ignore_typing = True
                self.downloading_file = {
                    "urls": urls,
                    "web": False,
                    "open": False,
                }
                self.restore_input_text = [None, "prompt"]
                reset = False

        elif cmd_type == 5:   # OPEN_LINK
            msg_index = self.lines_to_msg(chat_sel)
            urls = self.get_msg_urls(msg_index)
            select_num = cmd_args.get("num", 0)
            if select_num > 0 and select_num <= len(urls):
                select_num -= 1
            else:
                select_num = None
            if len(urls) == 1 or select_num is not None:
                if select_num is None:
                    select_num = 0
                webbrowser.open(urls[select_num], new=0, autoraise=True)
            elif len(urls) > 1:
                self.ignore_typing = True
                self.downloading_file = {
                    "urls": urls,
                    "web": True,
                    "open": False,
                }
                self.restore_input_text = [None, "prompt"]
                reset = False

        elif cmd_type == 6 and support_media:   # PLAY
            msg_index = self.lines_to_msg(chat_sel)
            urls, media_type = self.get_msg_media(msg_index)
            select_num = cmd_args.get("num", 0)
            if select_num > 0 and select_num <= len(urls):
                select_num -= 1
            else:
                select_num = None
            if len(urls) == 1 or select_num is not None:
                if select_num is None:
                    select_num = 0
                logger.debug(f"Trying to play attachment with type: {media_type}")
                self.download_threads.append(threading.Thread(target=self.download_file, daemon=True, args=(urls[select_num], False, True)))
                self.download_threads[-1].start()
            elif len(urls) > 1:
                self.downloading_file = {
                    "urls": urls,
                    "web": False,
                    "open": True,
                }
                self.restore_input_text = [None, "prompt"]
                reset = False

        elif cmd_type == 7:   # CANCEL
            reset = False
            self.restore_input_text = [None, "prompt"]
            self.reset_actions()
            self.ignore_typing = True
            self.cancel_download = True

        elif cmd_type == 8:   # COPY_MESSAGE
            msg_index = self.lines_to_msg(chat_sel)
            peripherals.copy_to_clipboard(self.messages[msg_index]["content"])

        elif cmd_type == 9:   # UPLOAD
            if self.current_channel.get("allow_attach", True):
                path = cmd_args.get("path", None)
                if path:
                    self.upload_threads.append(threading.Thread(target=self.upload, daemon=True, args=(path, )))
                    self.upload_threads[-1].start()
                else:
                    self.restore_input_text = [None, "autocomplete"]
                    if self.recording:   # stop recording voice message
                        self.recording = False
                        _ = recorder.stop()
                    self.uploading = True
                    self.ignore_typing = True
                    reset = False

        elif cmd_type == 10:   # SPOIL
            msg_index = self.lines_to_msg(chat_sel)
            self.spoil(msg_index)

        elif cmd_type == 11 and self.tree_metadata[tree_sel]["type"] in (11, 12):   # TOGGLE_THREAD
            thread_id = self.tree_metadata[tree_sel]["id"]
            guild_id, channel_id, _ = self.find_parents(tree_sel)
            self.thread_togle_join(guild_id, channel_id, thread_id)
            self.update_tree()

        elif cmd_type == 12:  # PROFILE
            user_id = cmd_args.get("user_id", None)
            if not user_id:
                msg_index = self.lines_to_msg(chat_sel)
                user_id = self.messages[msg_index]["user_id"]
            guild_id = self.active_channel["guild_id"]
            if self.viewing_user_data["id"] != user_id or self.viewing_user_data["guild_id"] != guild_id:
                if guild_id:
                    self.viewing_user_data = self.discord.get_user_guild(user_id, guild_id)
                else:
                    self.viewing_user_data = self.discord.get_user(user_id)
            self.stop_assist(close=False)
            self.view_profile(self.viewing_user_data)

        elif cmd_type == 13:   # CHANNEL
            channel_id = cmd_args.get("channel_id", None)
            if channel_id:
                self.view_selected_channel(channel_id=channel_id)
            else:
                self.view_selected_channel(tree_sel=tree_sel)

        elif cmd_type == 14:   # SUMMARIES
            channel_id = cmd_args.get("channel_id", None)
            self.view_summaries(channel_id)

        elif cmd_type == 15:   # HIDE
            channel_id = cmd_args.get("channel_id", None)
            channel_sel = None
            if channel_id:
                _, _, guild_id, _, _ = self.find_parents_from_id(channel_id)
            else:
                channel_sel = self.tree_metadata[tree_sel]["type"]
            if channel_sel and channel_sel["type"] not in (-1, 1, 11, 12):
                self.restore_input_text = [None, "prompt"]
                reset = False
                self.reset_actions()
                self.ignore_typing = True
                guild_id = self.find_parents(tree_sel)[0]
                self.hiding_ch = {
                    "channel_name": channel_sel["name"],
                    "channel_id": channel_sel["id"],
                    "guild_id": guild_id,
                }

        elif cmd_type == 16:   # SEARCH
            search_text = cmd_args.get("search_text", None)
            if search_text:
                reset = False
                self.do_search(search_text)
                self.restore_input_text = [None, "search"]
                self.reset_actions()
                self.extra_window_open = True
                self.search = True
                self.ignore_typing = True
            elif not self.search:
                reset = False
                self.reset_actions()
                self.restore_input_text = [None, "search"]
                self.search = True
                self.ignore_typing = True
                max_w = self.tui.get_dimensions()[2][1]
                extra_title, extra_body = formatter.generate_extra_window_text("Search:", formatter.SEARCH_HELP_TEXT, max_w)
                self.stop_assist(close=False)
                self.tui.draw_extra_window(extra_title, extra_body)
                self.extra_window_open = True

        elif cmd_type == 17:   # LINK_CHANNEL
            channel_id = cmd_args.get("channel_id")
            guild_id = None
            if channel_id:
                _, _, guild_id, _, _ = self.find_parents_from_id(channel_id)
            else:
                guild_id = self.active_channel["guild_id"]
                channel_id = self.tree_metadata[tree_sel]["id"]
            if guild_id:
                url = f"https://{self.discord.host}/channels/{guild_id}/{channel_id}"
                peripherals.copy_to_clipboard(url)

        elif cmd_type == 18:   # LINK_MESSAGE
            msg_index = self.lines_to_msg(chat_sel)
            self.copy_msg_url(msg_index)

        elif cmd_type == 19:   # GOTO_MENTION
            select_num = cmd_args.get("num", 0)
            if select_num > 0 and select_num <= len(urls):
                select_num -= 1
            else:
                select_num = None
            msg_index = self.lines_to_msg(chat_sel)
            channels = []
            message_text = self.messages[msg_index]["content"]
            mention_msg = self.messages[msg_index].get("mention_msg")
            msg_num = 0
            for match in re.finditer(formatter.match_channel_id_msg_group, message_text):
                if match.group(2) and msg_num < len(mention_msg):
                    message_id = mention_msg[msg_num]
                    msg_num += 1
                else:
                    message_id = None
                channels.append([match.group(1), message_id])
            if len(channels) == 1 or select_num is not None:
                if select_num is None:
                    select_num = 0
                channel_id = channels[select_num][0]
                message_id = channels[select_num][1]
                channel_name = self.channel_name_from_id(channel_id)
                if channel_name:
                    self.switch_channel(channel_id, channel_name, self.active_channel["guild_id"], self.active_channel["guild_name"])
                    if message_id:
                        self.go_to_message(message_id)
            elif channels:
                self.ignore_typing = True
                self.going_to_ch = channels
                self.update_status_line()

        elif cmd_type == 20:   # STATUS
            new_status = cmd_args.get("status")
            if self.my_status["client_state"] == "online":
                if not new_status:
                    for num, status in enumerate(STATUS_STRINGS):
                        if status == self.my_status["status"]:
                            if num == len(STATUS_STRINGS) - 1:
                                new_status = STATUS_STRINGS[0]
                            else:
                                new_status = STATUS_STRINGS[num+1]
                            break
                self.set_status(new_status)

        elif cmd_type == 21:   # RECORD
            cancel = cmd_args.get("cancel")
            if self.recording:
                self.stop_recording(cancel=cancel)
            else:
                self.start_recording()

        elif cmd_type == 22:   # MEMBER_LIST
            self.toggle_member_list()

        elif cmd_type == 23:   # REACT
            react_text = cmd_args.get("react_text")
            msg_index = self.lines_to_msg(chat_sel)
            if not react_text:
                reset = False
                if "deleted" not in self.messages[msg_index]:
                    self.restore_input_text = [None, "react"]
                    self.ignore_typing = True
                    self.reacting = {
                        "id": self.messages[msg_index]["id"],
                        "msg_index": msg_index,
                        "username": self.messages[msg_index]["username"],
                        "global_name": self.messages[msg_index]["global_name"],
                    }
                    self.update_status_line()
            else:
                self.build_reaction(react_text, msg_index=msg_index)

        elif cmd_type == 24:   # SHOW_REACTIONS
            msg_index = self.lines_to_msg(chat_sel)
            multiple = self.do_view_reactions(msg_index)
            if multiple:
                self.restore_input_text = [None, "prompt"]

        elif cmd_type == 25:   # GOTO
            channel_id, channel_name, guild_id, guild_name, parent_hint = self.find_parents_from_id(cmd_args["channel_id"])
            self.switch_channel(channel_id, channel_name, guild_id, guild_name, parent_hint=parent_hint)

        elif cmd_type == 26:   # VIEW_PFP
            user_id = cmd_args.get("user_id", None)
            if not user_id:
                msg_index = self.lines_to_msg(chat_sel)
                user_id = self.messages[msg_index]["user_id"]
            avatar_id = None
            if user_id == self.my_id:
                avatar_id = self.my_user_data["extra"]["avatar"]
            if not avatar_id:
                for dm in self.dms:
                    if dm["id"] == user_id:
                        avatar_id = dm["avatar"]
                        break
            if not avatar_id:
                avatar_id = self.discord.get_user(user_id, extra=True)["extra"]["avatar"]
            if avatar_id:
                if self.config["native_media_player"]:
                    size = 160
                else:
                    size = None
                pfp_path = self.discord.get_pfp(user_id, avatar_id, size)
                if pfp_path:
                    self.media_thread = threading.Thread(target=self.open_media, daemon=True, args=(pfp_path, ))
                    self.media_thread.start()

        elif cmd_type == 27:   # CHECK_STANDING
            standing = self.discord.get_my_standing()
            self.update_extra_line(f"Account standing: {standing}/100")

        if reset:
            self.reset_actions()
        self.update_status_line()


    def find_parents(self, tree_sel):
        """Find object parents from its tree index"""
        guild_id = None
        guild_name = None
        parent_id = None
        parent_index = self.tree_metadata[tree_sel]["parent_index"]
        for i in range(3):   # avoid infinite loops, there can be max 3 nest levels
            if parent_index is None:
                break
            guild_id = self.tree_metadata[parent_index]["id"]
            guild_name = self.tree_metadata[parent_index]["name"]
            parent_index = self.tree_metadata[parent_index]["parent_index"]
            if i == 0 and self.tree_metadata[tree_sel]["type"] in (11, 12):
                parent_id = guild_id
        return guild_id, parent_id, guild_name


    def find_parents_from_id(self, channel_id):
        """Find channel parents from its id"""
        for guild in self.guilds:
            for channel in guild["channels"]:
                if channel["id"] == channel_id:
                    return channel_id, channel["name"], guild["guild_id"], guild["name"], None
        # check dms
        for dm in self.dms:
            if dm["id"] == channel_id:
                if dm["name"]:
                    name = dm["name"]
                else:
                    name = dm["recipients"][0]["username"]
                return channel_id, name, None, None, None
        return None, None, None, None, None


    def go_bottom(self):
        """Go to chat bottom"""
        self.tui.scroll_bot()
        if self.messages[0]["id"] != self.last_message_id:
            self.add_running_task("Downloading chat", 4)
            self.messages = self.get_messages_with_members()
            self.update_chat()
            self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
            self.remove_running_task("Downloading chat", 4)


    def go_replied(self, msg_index):
        """Go to replied message from selected message in chat"""
        if self.messages[msg_index]["referenced_message"]:
            reference_id = self.messages[msg_index]["referenced_message"]["id"]
            if reference_id:
                self.go_to_message(reference_id)


    def get_msg_urls(self, msg_index):
        """Get all urls from message in chat"""
        urls = []
        code_snippets = []
        code_blocks = []
        message_text = self.messages[msg_index]["content"]
        for match in re.finditer(formatter.match_md_code_snippet, message_text):
            code_snippets.append([match.start(), match.end()])
        for match in re.finditer(formatter.match_md_code_block, message_text):
            code_blocks.append([match.start(), match.end()])
        except_ranges = code_snippets + code_blocks
        for match in re.finditer(formatter.match_url, message_text):
            start = match.start()
            end = match.end()
            skip = False
            for except_range in except_ranges:
                start_r = except_range[0]
                end_r = except_range[1]
                if start > start_r and start < end_r and end > start_r and end <= end_r:
                    skip = True
                    break
            if not skip:
                urls.append(match.group())
        for embed in self.messages[msg_index]["embeds"]:
            if embed["url"]:
                urls.append(embed["url"])
        return urls

    def copy_msg_url(self, msg_index):
        """Copy message url to clipboard"""
        guild_id = self.active_channel["guild_id"]
        channel_id = self.active_channel["channel_id"]
        msg_id = self.messages[msg_index]["id"]
        url = f"https://{self.discord.host}/channels/{guild_id}/{channel_id}/{msg_id}"
        peripherals.copy_to_clipboard(url)


    def get_msg_media(self, msg_index):
        """Get all palyable media embeds from message in chat"""
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
        return urls, media_type


    def spoil(self, msg_index):
        """Reveal one-by-one spoiler in selected messgae in chat"""
        if "spoiled" in self.messages[msg_index]:
            self.messages[msg_index]["spoiled"] += 1
        else:
            self.messages[msg_index]["spoiled"] = 1
        self.update_chat(keep_selected=True)


    def download_file(self, url, move=True, open_media=False):
        """Thread that downloads and moves file to downloads dir"""
        if "https://media.tenor.com/" in url:
            url = downloader.convert_tenor_gif_type(url, self.tenor_gif_type)
        destination = None
        from_cache = False
        match = re.search(media.match_youtube, url)
        if match:
            url = match.group()
            if open_media:
                self.add_running_task("Loading video", 2)
                self.media_thread = threading.Thread(target=self.open_media, daemon=True, args=(url, ))
                self.media_thread.start()
                self.remove_running_task("Loading video", 2)
            else:
                self.update_extra_line("Can only play YouTube video")
            return

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
                path = self.downloader.download(url)
                if path:
                    if move:
                        if not os.path.exists(self.downloads_path):
                            os.makedirs(os.path.expanduser(os.path.dirname(self.downloads_path)), exist_ok=True)
                        destination = os.path.join(self.downloads_path, os.path.basename(path))
                        shutil.move(path, destination)
                    else:
                        destination = path
                else:
                    return
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
            for ch_index, channel in enumerate(self.ready_attachments):
                if channel["channel_id"] == self.active_channel["channel_id"]:
                    break
            else:
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


    def start_recording(self):
        """Start recording audio message"""
        recorder.start()
        self.recording = True
        self.update_extra_line("RECORDING, Esc to cancel, Enter to send")


    def stop_recording(self, cancel=False):
        """Stop recording audio message and send it"""
        if self.recording:
            self.recording = False
            file_path = recorder.stop()
            self.update_extra_line()
            if not cancel:
                self.add_running_task("Uploading file", 2)
                self.discord.send_voice_message(
                    self.active_channel["channel_id"],
                    file_path,
                    reply_id=self.replying["id"],
                    reply_channel_id=self.active_channel["channel_id"],
                    reply_guild_id=self.active_channel["guild_id"],
                    reply_ping=self.replying["mention"],
                )
                self.remove_running_task("Uploading file", 2)


    def get_messages_with_members(self, num=50, before=None, after=None, around=None):
        """Get messages, check for missing members, request and wait for member chunk, and update local member list"""
        channel_id = self.active_channel["channel_id"]
        messages = self.discord.get_messages(channel_id, num, before, after, around)
        if messages is None:
            return None   # network error

        # restore deleted
        if self.keep_deleted and messages:
            messages = self.restore_deleted(messages)

        current_guild = self.active_channel["guild_id"]
        missing_members = []
        if not current_guild:
            # skipping dms
            return messages

        # find missing members
        for message in messages:
            message_user_id = message["user_id"]
            if message_user_id in missing_members:
                continue
            for member in self.current_member_roles:
                if member["user_id"] == message_user_id:
                    break
            else:
                missing_members.append(message_user_id)

        # request missing members
        if missing_members:
            self.gateway.request_members(current_guild, missing_members)
            for _ in range(10):   # wait max 1s
                new_member_roles = self.gateway.get_member_roles()
                if new_member_roles:
                    # update member list
                    self.member_roles = new_member_roles
                    self.select_current_member_roles()
                else:
                    # wait to receive
                    time.sleep(0.1)

        # replace discord links
        for msg_num, message in enumerate(messages):
            messages[msg_num] = formatter.replace_discord_url(message, current_guild)
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
        for num, message in enumerate(self.messages):
            if message["id"] == message_id:
                self.tui.set_selected(self.msg_to_lines(num))
                break

        else:
            logger.debug(f"Requesting chat chunk around {message_id}")
            self.add_running_task("Downloading chat", 4)
            new_messages = self.get_messages_with_members(around=message_id)
            if new_messages:
                self.messages = new_messages
            self.update_chat(keep_selected=False)
            self.add_running_task("Downloading chat", 4)

            for num, message in enumerate(self.messages):
                if message["id"] == message_id:
                    self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
                    self.tui.set_selected(self.msg_to_lines(num))
                    break


    def toggle_member_list(self):
        """Toggle member list if there is enough space"""
        if self.member_list_visible:
            if self.screen.getmaxyx()[1] - self.config["tree_width"] - self.member_list_width - 2 < 32:
                self.update_extra_line("Not enough space to draw member list")
            else:
                self.tui.remove_member_list()
                self.member_list_visible = False
        else:
            self.update_member_list()
            self.member_list_visible = True


    def set_status(self, status):
        """Set my status: online, idle, dnd, invisible"""
        if status in STATUS_STRINGS:
            self.my_status["status"] = status
            self.gateway.update_presence(
                status,
                custom_status=self.my_status["custom_status"],
                custom_status_emoji=self.my_status["custom_status_emoji"],
                rpc=self.my_rpc,
            )
            settings = {
                "status":{
                    "status": status,
                    "custom_status": {
                        "text": self.my_status["custom_status"],
                        "emoji_name": self.my_status["custom_status_emoji"]["name"],
                    },
                    "show_current_game": True,
                },
            }
            self.discord.patch_settings_proto(1, settings)
            self.update_status_line()


    def view_profile(self, user_data):
        """Format and show extra window with profile informations"""
        max_w = self.tui.get_dimensions()[2][1]
        roles = []
        if user_data["roles"]:
            for role_id in user_data["roles"]:
                for role in self.current_roles:
                    if role["id"] == role_id:
                        roles.append(role["name"])
                        break
        user_id = user_data["id"]
        selected_presence = None
        guild_id = user_data["guild_id"]
        if user_id == self.my_id:
            selected_presence = self.my_status
        elif guild_id:
            if self.get_members:   # first check member list
                for presence in self.current_members:
                    if "id" in presence and presence["id"] == user_id:
                        selected_presence = presence
                        break
            if not selected_presence:   # then check subscribed list
                for presence in self.current_subscribed_members:
                    if presence["id"] == user_id:
                        selected_presence = presence
                        break
                else:   # if none, then subscribe
                    self.gateway.subscribe_member(user_id, guild_id)
        else:   # dms
            for presence in self.activities:
                if "id" in presence and presence["id"] == user_id:
                    selected_presence = presence
                    break
        extra_title, extra_body = formatter.generate_extra_window_profile(user_data, roles, selected_presence, max_w)
        self.tui.draw_extra_window(extra_title, extra_body)
        self.extra_window_open = True


    def view_selected_channel(self, tree_sel=None, channel_id=None):
        """View selected channel from tree or by its id"""
        channel_sel = None
        if tree_sel:
            ch_type = self.tree_metadata[tree_sel]["type"]
            if ch_type == -1:
                guild_id = self.tree_metadata[tree_sel]["id"]
                for guild in self.guilds:
                    if guild["guild_id"] == guild_id:
                        self.stop_assist(close=False)
                        self.view_channel(guild, True)
                        break
            elif ch_type not in (1, 3, 4, 11, 12):
                channel_id = self.tree_metadata[tree_sel]["id"]
                guild_id = self.find_parents(tree_sel)[0]
                for guild in self.guilds:
                    if guild["guild_id"] == guild_id:
                        for channel in guild["channels"]:
                            if channel["id"] == channel_id:
                                channel_sel = channel
                                break
                        break
        else:
            found = False
            for guild in self.guilds:
                for channel in guild["channels"]:
                    if channel["id"] == channel_id:
                        if channel["type"] not in (1, 3, 4, 11, 12):
                            channel_sel = channel
                        found = True
                        break
                if found:
                    break
        if channel_sel:
            self.stop_assist(close=False)
            self.view_channel(channel_sel)


    def view_channel(self, channel, guild=False):
        """Format and show extra window with channel/guild informations"""
        max_w = self.tui.get_dimensions()[2][1]
        if guild:
            extra_title, extra_body = formatter.generate_extra_window_guild(channel, max_w)
        else:
            extra_title, extra_body = formatter.generate_extra_window_channel(channel, max_w)
        self.tui.draw_extra_window(extra_title, extra_body)
        self.extra_window_open = True


    def view_summaries(self, channel_id=None):
        """Format and show extra window with this or specified channel sumamries"""
        summaries = []
        if not channel_id:
            for guild in self.summaries:
                if guild["guild_id"] == self.active_channel["guild_id"]:
                    for channel in guild["channels"]:
                        if channel["channel_id"] == self.active_channel["channel_id"]:
                            summaries = channel["summaries"]
                            break
                    break
        else:
            found = False
            for guild in self.summaries:
                for channel in guild["channels"]:
                    if channel["channel_id"] == channel_id:
                        summaries = channel["summaries"]
                        found = True
                        break
                if found:
                    break
        self.stop_assist(close=False)
        max_w = self.tui.get_dimensions()[2][1]
        extra_title, extra_body, self.extra_indexes = formatter.generate_extra_window_summaries(summaries, max_w)
        self.tui.draw_extra_window(extra_title, extra_body, select=True)
        self.extra_window_open = True


    def do_view_reactions(self, msg_index):
        """Format and show extra window with this or specified message reactions details"""
        reactions = self.messages[msg_index]["reactions"]
        if reactions:
            if len(self.messages[msg_index]["reactions"]) == 1:
                if reactions[0]["emoji_id"]:
                    reaction = f"{reactions[0]["emoji"]}:{reactions[0]["emoji_id"]}"
                else:
                    reaction = reactions[0]["emoji"]
                reaction_details = self.discord.get_reactions(
                    self.active_channel["channel_id"],
                    self.messages[msg_index]["id"],
                    reaction,
                    )
                self.stop_assist(close=False)
                max_w = self.tui.get_dimensions()[2][1]
                extra_title, extra_body = formatter.generate_extra_window_reactions(reactions[0], reaction_details, max_w)
                self.tui.draw_extra_window(extra_title, extra_body)
                self.extra_window_open = True
            else:
                self.ignore_typing = True
                self.view_reactions = {
                    "message_id": self.messages[msg_index]["id"],
                    "reactions": reactions,
                }
                self.update_status_line()
                return True


    def build_reaction(self, text, msg_index=None):
        """Build and send reaction from provided text"""
        first = text.split(" ")[0]
        if msg_index is None:
            msg_index = self.reacting["msg_index"]
        if msg_index is None or msg_index < 0:
            return
        all_reactions = self.messages[msg_index]["reactions"]
        my_present_emojis = []
        my_present_ids = []
        for reaction in all_reactions:
            if reaction["me"]:
                if reaction["emoji_id"]:
                    my_present_ids.append(reaction["emoji_id"])
                else:
                    my_present_emojis.append(reaction["emoji"])
        add_to_existing = False
        try:  # existing emoji index
            num = max(int(first) - 1, 0)
            if num < len(all_reactions) and num >= 0:
                # get reaction from existing emoji
                selected_reaction = all_reactions[num]
                if selected_reaction["emoji_id"]:
                    emoji_string = f"<:{selected_reaction["emoji"]}:{selected_reaction["emoji_id"]}>"
                else:
                    emoji_string = selected_reaction["emoji"]
                add_to_existing = True
        except ValueError:   # new emoji
            emoji_string = emoji.emojize(first)
        if emoji.is_emoji(emoji_string):   # standard emoji
            if emoji_string not in my_present_emojis:
                if len(all_reactions) < 20 or add_to_existing:
                    self.discord.send_reaction(
                        self.active_channel["channel_id"],
                        self.messages[msg_index]["id"],
                        emoji_string,
                    )
                else:
                    self.update_extra_line("Maximum number of reactions reached.")
            else:
                self.discord.remove_reaction(
                    self.active_channel["channel_id"],
                    self.messages[msg_index]["id"],
                    emoji_string,
                )
        else:   # discord emoji
            match = re.match(match_emoji, emoji_string)
            if match:
                emoji_name = match.group(1)
                emoji_id = match.group(2)
                if emoji_id not in my_present_ids:
                    if len(all_reactions) < 20 or add_to_existing:
                        # validate discord emoji before adding it
                        valid = False
                        guild_emojis = []
                        for guild in self.gateway.get_emojis():
                            if guild["guild_id"] == self.active_channel["guild_id"]:
                                guild_emojis += guild["emojis"]
                                if not self.premium:
                                    break
                        for guild_emoji in guild_emojis:
                            if guild_emoji["id"] == emoji_id:
                                valid = True
                                break
                        if valid:
                            self.discord.send_reaction(
                                self.active_channel["channel_id"],
                                self.messages[msg_index]["id"],
                                f"{emoji_name}:{emoji_id}",
                            )
                    else:
                        self.update_extra_line("Maximum number of reactions reached.")
                else:
                    self.discord.remove_reaction(
                        self.active_channel["channel_id"],
                        self.messages[msg_index]["id"],
                        f"{emoji_name}:{emoji_id}",
                    )
        self.restore_input_text = [None, None]


    def close_extra_window(self):
        """Close extra window and toggle its state"""
        self.tui.remove_extra_window()
        self.extra_window_open = False
        self.viewing_user_data = {"id": None, "guild_id": None}


    def do_search(self, text):
        """Perform message search"""
        self.add_running_task("Searching", 4)
        content, channel_id, author_id, mentions, has, max_id, min_id, pinned = parser.search_string(text)
        self.search = (content, channel_id, author_id, mentions, has, max_id, min_id, pinned)
        logger.debug(f"Starting search with params: {self.search}")
        total_search_messages, self.search_messages = self.discord.search(
            self.active_channel["guild_id"],
            content=content,
            channel_id=channel_id,
            author_id=author_id,
            mentions=mentions,
            has=has,
            max_id=max_id,
            min_id=min_id,
            pinned=pinned,
        )
        if len(self.search_messages) >= total_search_messages:
            self.search_end = True
        extra_title, self.extra_body, self.extra_indexes = formatter.generate_extra_window_search(
            self.search_messages,
            self.current_roles,
            self.current_channels,
            self.blocked,
            total_search_messages,
            self.config,
            self.tui.get_dimensions()[2][1],
        )
        self.tui.draw_extra_window(extra_title, self.extra_body, select=True)
        self.remove_running_task("Searching", 4)


    def extend_search(self):
        """Repeat search and add more messages"""
        self.add_running_task("Searching", 4)
        logger.debug(f"Extending search with params: {self.search}")
        total_search_messages, search_chunk = self.discord.search(
            self.active_channel["guild_id"],
            content=self.search[0],
            channel_id=self.search[1],
            author_id=self.search[2],
            mentions=self.search[3],
            has=self.search[4],
            max_id=self.search[5],
            min_id=self.search[6],
            pinned=self.search[7],
            offset=len(self.search_messages),
        )
        if search_chunk:
            self.search_messages += search_chunk
            if len(self.search_messages) >= total_search_messages:
                self.search_end = True
            extra_title, extra_body_chunk, indexes_chunk = formatter.generate_extra_window_search(
                search_chunk,
                self.current_roles,
                self.current_channels,
                self.blocked,
                total_search_messages,
                self.config,
                self.tui.get_dimensions()[2][1],
            )
            self.extra_body += extra_body_chunk
            self.extra_indexes += indexes_chunk
            self.tui.draw_extra_window(extra_title, self.extra_body, select=len(self.extra_body))
        self.remove_running_task("Searching", 4)


    def assist(self, assist_word, assist_type, query_results=None):
        """Assist when typing: channel, username, role, emoji and sticker"""
        assist_word = assist_word.lower()
        assist_words = assist_word.split("_")
        self.assist_type = assist_type
        self.assist_found = []

        if assist_type == 1:   # channels
            if not self.command:   # current guild channels
                for channel in self.current_channels:
                    # skip categories (type 4)
                    channel_name = channel["name"].lower()
                    if channel["type"] != 4 and all(x in channel_name for x in assist_words):
                        if channel["type"] == 2:
                            name = f"{channel["name"]} - voice"
                        elif channel["type"] in (11, 12):
                            name = f"{channel["name"]} - thread"
                        elif channel["type"] == 15:
                            name = f"{channel["name"]} - forum"
                        else:
                            name = channel["name"]
                        self.assist_found.append((name, channel["id"]))
            else:   # all guilds channels and dms
                for dm in self.dms:
                    if dm["name"]:
                        name = dm["name"]
                    else:
                        name = dm["recipients"][0]["username"]
                    if all(x in name.lower() for x in assist_words):
                        self.assist_found.append((f"{name} (DM)", dm["id"]))
                for guild in self.guilds:
                    guild_name = guild["name"]
                    guild_name_lower = guild_name.lower()
                    for channel in guild["channels"]:
                        # skip categories (type 4)
                        channel_name = channel["name"].lower()
                        check_string = f"{channel_name} {guild_name_lower}"
                        if channel["type"] != 4 and all(x in check_string for x in assist_words):
                            if channel["type"] == 2:
                                name = f"{channel["name"]} - voice ({guild["name"]})"
                            elif channel["type"] in (11, 12):
                                name = f"{channel["name"]} - thread ({guild["name"]})"
                            elif channel["type"] == 15:
                                name = f"{channel["name"]} - forum ({guild["name"]})"
                            else:
                                name = f"{channel["name"]} ({guild["name"]})"
                            self.assist_found.append((name, channel["id"]))

        elif assist_type == 2:   # username/role
            # roles first
            for role in self.current_roles:
                role_name = role["name"]
                role_name_lower = role_name.lower()
                if all(x in role_name_lower for x in assist_words):
                    self.assist_found.append((f"{role_name} - role", f"&{role["id"]}"))
            if query_results:
                for member in query_results:
                    member_name = member["username"]
                    if all(x in member_name for x in assist_words):
                        self.assist_found.append((member_name, member["id"]))
            else:
                self.gateway.request_members(
                    self.active_channel["guild_id"],
                    None,
                    query=assist_word,
                    limit=10,
                )

        elif assist_type == 3:   # emoji
            # server emoji
            emojis = []
            if self.premium:
                emojis = self.gateway.get_emojis()
            else:
                for guild in self.gateway.get_emojis():
                    if guild["guild_id"] == self.active_channel["guild_id"]:
                        emojis = [guild]
                        break
            for guild in emojis:
                guild_name = guild["guild_name"]
                guild_name_lower = guild_name.lower()
                for guild_emoji in guild["emojis"]:
                    check_string = f"{guild_emoji["name"].lower()} {guild_name_lower}"
                    if all(x in check_string for x in assist_words):
                        self.assist_found.append((
                            f"{guild_emoji["name"]} ({guild_name})",
                            f"<:{guild_emoji["name"]}:{guild_emoji["id"]}>",
                        ))
                        if len(self.assist_found) >= 50:
                            break
                if len(self.assist_found) >= 50:
                    break
            # standard emoji
            for key, item in emoji.EMOJI_DATA.items():
                # emoji.EMOJI_DATA = {emoji: {"en": ":emoji_name:", "status": 2, "E": 3}...}
                # using only qualified emojis (status: 2)
                if item["status"] == 2 and all(x in item["en"] for x in assist_words):
                    self.assist_found.append((f"{item["en"]} - {key}", item["en"]))
                    if len(self.assist_found) >= 50:
                        break
            # sort emoji so shorter are first
            self.assist_found = sorted(self.assist_found, key=lambda x: len(x[0]))

        elif assist_type == 4:   # sticker
            stickers = []
            if self.premium:
                stickers += self.gateway.get_stickers()
            else:
                for pack in self.gateway.get_stickers():
                    if pack["pack_id"] == self.active_channel["guild_id"]:
                        stickers.append(pack)
                        break
            if self.config["default_stickers"]:
                stickers += self.discord.get_stickers()
            for pack in stickers:
                pack_name = pack["pack_name"]
                pack_name_lower = pack_name.lower()
                for sticker in pack["stickers"]:
                    check_string = f"{sticker["name"].lower()} {pack_name_lower}"
                    if all(x in check_string for x in assist_words):
                        sticker_name = f"{sticker["name"]} ({pack_name})"
                        self.assist_found.append((sticker_name, sticker["id"]))
                        if len(self.assist_found) > 50:
                            break
                if len(self.assist_found) > 50:
                    break
        elif assist_type == 5:   # command
            if assist_word.lower().startswith("set "):
                assist_words = assist_word[4:].split("_")
                if assist_words:
                    for key, value in self.config.items():
                        if all(x in key for x in assist_words) and key != "token":
                            self.assist_found.append((f"set {key} = {value}", f"set {key} = {value}"))
                else:
                    for key, value in self.config.items():
                        if key != "token":
                            self.assist_found.append((f"set {key} = {value}", f"set {key} = {value}"))
            else:
                for command in formatter.COMMAND_ASSISTS:
                    if all(x in command[1] for x in assist_words):
                        self.assist_found.append(command)

        max_w = self.tui.get_dimensions()[2][1]
        extra_title, extra_body = formatter.generate_extra_window_assist(self.assist_found, assist_type, max_w)
        self.extra_window_open = True
        if (self.search or self.command) and not (self.assist_word or self.assist_word == " "):
            self.extra_bkp = (self.tui.extra_window_title, self.tui.extra_window_body)
        self.assist_word = assist_word
        self.tui.draw_extra_window(extra_title, extra_body, select=True, start_zero=True)


    def stop_assist(self, close=True):
        """Stop assisting and hide assist UI"""
        self.tui.instant_assist = False
        if self.assist_word:
            if close:
                self.close_extra_window()
            self.assist_word = None
            self.assist_type = None
            self.assist_found = []
            self.tui.assist_start = -1
            # if search was open, restore it
            if (self.search or self.command) and self.extra_bkp:
                self.extra_window_open = True
                self.tui.draw_extra_window(self.extra_bkp[0], self.extra_bkp[1], select=True)


    def insert_assist(self, input_text, index, start, end):
        """Insert assist from specified at specified position in the text"""
        if index >= len(self.assist_found) or index < 0:
            return None, None
        if self.assist_type == 1:   # channel
            insert_string = f"<#{self.assist_found[index][1]}>"   # format: "<#ID>"
        elif self.assist_type == 2:   # username/role
            # username format: "<@ID>"
            # role format: "<@&ID>" - already has "&" in ID
            insert_string = f"<@{self.assist_found[index][1]}>"
        elif self.assist_type == 3:   # emoji
            # default emoji - :emoji_name:
            # discord emoji format: "<:name:ID>"
            insert_string = self.assist_found[index][1]
        elif self.assist_type == 4:   # sticker
            insert_string = f"<;{self.assist_found[index][1]};>"   # format: "<;ID;>"
        elif self.assist_type == 5:   # command
            insert_string = self.assist_found[index][1]
            new_text = insert_string + " "
            new_pos = len(new_text)
            return new_text, new_pos
        new_text = input_text[:start-1] + insert_string + input_text[end:]
        new_pos = len(input_text[:start-1] + insert_string)
        self.stop_assist()
        return new_text, new_pos


    def cache_deleted(self):
        """Cache all deleted messages from current channel"""
        if not self.active_channel["channel_id"]:
            return
        for channel in self.deleted_cache:
            if channel["channel_id"] == self.active_channel["channel_id"]:
                this_channel_cache = channel["messages"]
                break
        else:
            self.deleted_cache.append({
                "channel_id": self.active_channel["channel_id"],
                "messages": [],
            })
            this_channel_cache = self.deleted_cache[-1]["messages"]
        for message in self.messages:
            if message.get("deleted"):
                for message_c in this_channel_cache:
                    if message_c["id"] == message["id"]:
                        break
                else:
                    this_channel_cache.append(message)
                    if len(this_channel_cache) > self.deleted_cache_limit:
                        this_channel_cache.pop(0)


    def restore_deleted(self, messages):
        """Restore all cached deleted messages for this channels in the correct position"""
        for channel in self.deleted_cache:
            if channel["channel_id"] == self.active_channel["channel_id"]:
                this_channel_cache = channel["messages"]
                break
        else:
            return messages
        for message_c in this_channel_cache:
            message_c_id = message_c["id"]
            # ids are discord snowflakes containing unix time so it can be used message sent time
            if message_c_id < messages[-1]["id"]:
                # if message_c date is before last message date
                continue
            if message_c_id > messages[0]["id"]:
                # if message_c date is after first message date
                if messages[0]["id"] > self.last_message_id:
                    # if it is not scrolled up
                    messages.insert(0, message_c)
                    pass
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
        """
        If TUI mode: prevent other UI updates, draw media and wait for input, after quitting - update UI
        If native mode: just open the file/url
        """
        if self.config["native_media_player"]:
            if shutil.which(self.config["yt_dlp_path"]) and shutil.which(self.config["mpv_path"]):
                mpv_path = self.config["mpv_path"]
            else:
                mpv_path = ""
            peripherals.native_open(path, mpv_path)
        elif support_media:
            self.tui.lock_ui(True)
            self.curses_media.play(path)
            # restore first 255 colors, attributes were not modified
            self.tui.restore_colors()   # 255_curses_bug
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
            self.current_my_roles,
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


    def update_forum(self, guild_id, channel_id):
        """Generate forum instead chat and update it in TUI"""
        # using self.messages as forum entries, should not be overwritten while in forum
        self.messages = []
        for guild in self.threads:
            if guild["guild_id"] == guild_id:
                for channel in guild["channels"]:
                    if channel["channel_id"] == channel_id:
                        self.messages = channel["threads"]
                        break
                break
        self.chat, self.chat_format = formatter.generate_forum(
            self.messages,
            self.blocked,
            self.chat_dim[1],
            self.colors,
            self.colors_formatted,
            self.config,
        )


    def update_member_list(self, last_index=None):
        """Generate member list and update it in TUI"""
        if last_index is not None and not self.tui.mlist_index-1 < last_index < self.tui.mlist_index-1 + self.screen.getmaxyx()[0]:
            return   # dont regenerate for changes that are not visible
        member_list, member_list_format = formatter.generate_member_list(
            self.current_members,
            self.current_roles,
            self.member_list_width,
            self.use_nick,
            self.status_char,
        )
        self.tui.draw_member_list(member_list, member_list_format)


    def update_status_line(self):
        """Generate status and title lines and update them in TUI"""
        action = {
            "type": None,
            "username": None,
            "global_name": None,
            "mention": None,
        }
        if self.replying["id"]:
            action = {
                "type": 1,
                "username": self.replying["username"],
                "global_name": self.replying["global_name"],
                "mention": self.replying["mention"],
            }
        elif self.editing:
            action["type"] = 2
        elif self.deleting:
            action["type"] = 3
        elif self.downloading_file["urls"]:
            if self.downloading_file["web"]:
                action["type"] = 4
            elif self.downloading_file["open"]:
                action["type"] = 6
            else:
                action["type"] = 5
        elif self.cancel_download:
            action["type"] = 7
        elif self.uploading:
            action["type"] = 8
        elif self.hiding_ch["channel_id"]:
            action["type"] = 9
        elif self.going_to_ch:
            action["type"] = 10
        elif self.reacting["id"]:
            action = {
                "type": 11,
                "username": self.reacting["username"],
                "global_name": self.reacting["global_name"],
            }
        elif self.view_reactions["message_id"]:
            action["type"] = 12
        else:
            action["type"] = 0

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
                self.format_rich,
                limit_typing=self.limit_typing,
                fun=self.fun,
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
            self.format_rich,
            limit_typing=self.limit_typing,
            fun=self.fun,
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
                self.format_rich,
                limit_typing=self.limit_typing,
                fun=self.fun,
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
                self.format_rich,
                limit_typing=self.limit_typing,
                fun=self.fun,
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
                self.format_rich,
                limit_typing=self.limit_typing,
                fun=self.fun,
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
            limit_prompt=self.config["limit_prompt"],
        )


    def update_extra_line(self, custom_text=None, update_only=False):
        """Genearate extra line and update it in TUI"""
        if custom_text:
            if custom_text == self.extra_line:
                self.extra_line = None
                self.tui.remove_extra_line()
            else:
                self.extra_line = custom_text
                self.tui.draw_extra_line(self.extra_line)
        elif update_only and self.extra_line:
            self.tui.draw_extra_line(self.extra_line)
        else:
            attachments = None
            for attachments in self.ready_attachments:
                if attachments["channel_id"] == self.active_channel["channel_id"]:
                    break
            if attachments:
                statusline_w = self.tui.get_dimensions()[2][1]
                self.extra_line = formatter.generate_extra_line(attachments["attachments"], self.selected_attachment, statusline_w)
                self.tui.draw_extra_line(self.extra_line)
            else:
                self.extra_line = None
                self.tui.remove_extra_line()


    def update_tree(self, collapsed=None, init_uncollapse=False):
        """Generate channel tree"""
        if collapsed is None:
            collapsed = self.state["collapsed"]
        self.tree, self.tree_format, self.tree_metadata = formatter.generate_tree(
            self.dms,
            self.guilds,
            self.threads,
            [x["channel_id"] for x in self.unseen],
            [x["channel_id"] for x in self.pings],
            self.guild_positions,
            self.activities,
            collapsed,
            self.active_channel["channel_id"],
            self.config["tree_drop_down_vline"],
            self.config["tree_drop_down_hline"],
            self.config["tree_drop_down_intersect"],
            self.config["tree_drop_down_corner"],
            self.config["tree_drop_down_pointer"],
            self.config["tree_drop_down_thread"],
            self.config["tree_drop_down_forum"],
            self.status_char,
            init_uncollapse=init_uncollapse,
            safe_emoji=self.config["emoji_as_text"],
            show_invisible = self.config["tree_show_invisible"],
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


    def set_seen(self, channel_id, force=False, ack=True):
        """
        Set channel as seen if it is not already seen.
        Force will set even if its not marked as unseen, used for active channel.
        """
        for num_1, unseen_channel in enumerate(self.unseen):
            if unseen_channel["channel_id"] == channel_id or force:   # find this unseen chanel
                if not force:
                    self.unseen.pop(num_1)
                if ack:
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
                self.update_tree()
                break


    def compute_permissions(self):
        """Compute permissions for all guilds. Run after roles have been obtained."""
        for guild in self.guilds:
            guild_id = guild["guild_id"]
            # get my roles
            my_roles = None
            for roles in self.my_roles:
                if roles["guild_id"] == guild_id:
                    my_roles = roles["roles"]
                    break
            if my_roles is None:
                return
            # get guild roles
            this_guild_roles = []
            for roles in self.all_roles:
                if roles["guild_id"] == guild_id:
                    this_guild_roles = roles["roles"]
                    break
            # get permissions
            self.guilds = perms.compute_permissions(
                self.guilds,
                this_guild_roles,
                guild_id,
                my_roles,
                self.my_id,
            )


    def hide_channel(self, channel_id, guild_id):
        """Locally hide this channel, for this session"""
        for guild in self.guilds:
            if guild["guild_id"] == guild_id:
                for channel in guild["channels"]:
                    if channel["id"] == channel_id:
                        channel["hidden"] = True
                        break
                break


    def load_threads(self, new_threads):
        """
        Add new threads to sorted list of threads by guild and channel.
        new_threads is list of threads that belong to same server.
        Threads are sorted by creation date.
        """
        to_sort = False
        guild_id = new_threads["guild_id"]
        new_threads = new_threads["threads"]
        for num, guild in enumerate(self.threads):
            if guild["guild_id"] == guild_id:
                break
        else:
            num = len(self.threads)
            self.threads.append({
                "guild_id": guild_id,
                "channels": [],
            })
        for new_thread in new_threads:
            parent_id = new_thread["parent_id"]
            for channel in self.threads[num]["channels"]:
                if channel["channel_id"] == parent_id:
                    for thread in channel["threads"]:
                        if thread["id"] == new_thread["id"]:
                            muted = thread["muted"]   # dont overwrite muted and joined
                            joined = thread.get("joined", False)
                            thread.update(new_thread)
                            thread["muted"] = muted
                            thread["joined"] = joined
                            # no need to sort if its only update
                            break
                    else:
                        to_sort = True
                        channel["threads"].append(new_thread)
            else:
                new_thread.pop("parent_id")
                self.threads[num]["channels"].append({
                    "channel_id": parent_id,
                    "threads": [new_thread],
                })
        if to_sort:
            for guild in self.threads:
                if guild["guild_id"] == guild_id or guild_id is None:
                    for channel in guild["channels"]:
                        channel["threads"] = sorted(channel["threads"], key=lambda x: x["id"], reverse=True)
                break
        self.update_tree()
        if self.forum:
            self.update_forum(self.active_channel["guild_id"], self.active_channel["channel_id"])


    def thread_togle_join(self, guild_id, channel_id, thread_id, join=None):
        """Toggle, or set a custom value for 'joined' state of a thread and return new state"""
        for guild in self.threads:
            if guild["guild_id"] == guild_id:
                for channel in guild["channels"]:
                    if channel["channel_id"] == channel_id:
                        for thread in channel["threads"]:
                            if thread["id"] == thread_id:
                                if join is None:
                                    if thread["joined"]:
                                        thread["joined"] = False
                                        discord.leave_thread(thread_id)
                                    else:
                                        thread["joined"] = True
                                        discord.join_thread(thread_id)
                                if join != thread["joined"]:
                                    thread["joined"] = join
                                    discord.join_thread(thread_id)
                        break
                break


    def check_tree_format(self):
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
                peripherals.save_json(self.state, "state.json")


    def update_summary(self, new_summary):
        """Add new summary to list, then save it, avoiding often disk writes"""
        summary = {
            "message_id": new_summary["message_id"],
            "topic": new_summary["topic"],
            "description": new_summary["description"],
        }
        for num, guild in enumerate(self.summaries):   # select guild
            if guild["guild_id"] == new_summary["guild_id"]:
                selected_guild = num
                break
        else:
            self.summaries.append({
                "guild_id": new_summary["guild_id"],
                "channels": [],
            })
            selected_guild = -1
        for channel in self.summaries[selected_guild]["channels"]:
            if channel["channel_id"] == new_summary["channel_id"]:
                channel["summaries"].append(summary)
                if len(channel["summaries"]) > LIMIT_SUMMARIES:
                    del channel["summaries"][0]
                break
        else:
            self.summaries[selected_guild]["channels"].append({
                "channel_id": new_summary["channel_id"],
                "summaries": [summary],
            })
        if time.time() - self.last_summary_save > SUMMARY_SAVE_INTERVAL:
            peripherals.save_json(self.summaries, "summaries.json")
            self.last_summary_save = time.time()


    def update_presence_from_proto(self):
        """Update presence from protos locally and redraw status line"""
        custom_status_emoji = None
        custom_status = None
        if "status" in self.discord_settings:
            status = self.discord_settings["status"]["status"]
            if "customStatus" in self.discord_settings["status"]:
                custom_status_emoji = {
                    "id": self.discord_settings["status"]["customStatus"].get("emojiID"),
                    "name": self.discord_settings["status"]["customStatus"].get("emojiName"),
                    "animated": self.discord_settings["status"]["customStatus"].get("animated", False),
                }
                custom_status = self.discord_settings["status"]["customStatus"]["text"]
            if custom_status_emoji and not (custom_status_emoji["name"] or custom_status_emoji["id"]):
                custom_status_emoji = None
        else:   # just in case
            status = "online"
            custom_status = None
            custom_status_emoji = None
        self.my_status.update({
            "status": status,
            "custom_status": custom_status,
            "custom_status_emoji": custom_status_emoji,
        })
        self.update_status_line()


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
                    custom_sound=self.notification_path,
                )
                self.notifications.append({
                    "notification_id": notification_id,
                    "channel_id": new_message["d"]["channel_id"],
                })


    def main(self):
        """Main app method"""
        logger.info("Init sequence started")
        logger.info("Waiting for ready signal from gateway")
        self.my_status["client_state"] = "connecting"
        self.update_status_line()

        while not self.gateway.get_ready():
            if self.gateway.error:
                logger.fatal(f"Gateway error: \n {self.gateway.error}")
                sys.exit(self.gateway.error + ERROR_TEXT)
            time.sleep(0.2)

        self.my_status["client_state"] = "online"
        self.update_status_line()

        self.premium = self.gateway.get_premium()
        self.discord_settings = self.gateway.get_settings_proto()

        # just in case, download proto if its not in gateway
        if "status" not in self.discord_settings:
            self.discord_settings = self.discord.get_settings_proto(1)

        # guild position
        self.guild_positions = []
        if "guildFolders" in self.discord_settings:
            for folder in self.discord_settings["guildFolders"]["folders"]:
                self.guild_positions += folder["guildIds"]
        if logger.getEffectiveLevel() == logging.DEBUG:
            debug.save_json(debug.anonymize_guild_positions(self.guild_positions), "guild_positions.json")

        # custom status
        self.update_presence_from_proto()

        self.gateway_state = 1
        logger.info("Gateway is ready")
        self.tui.update_chat(["Loading channels", "Connecting to Discord"], [[[self.colors[0]]]] * 2)

        # get data from gateway
        self.guilds = self.gateway.get_guilds()
        self.all_roles = self.gateway.get_roles()
        self.all_roles = color.convert_role_colors(self.all_roles)
        last_free_color_id = self.tui.get_last_free_color_id()

        # get my roles
        self.my_roles = self.gateway.get_my_roles()
        self.current_my_roles = []
        for roles in self.my_roles:
            if roles["guild_id"] == self.active_channel["guild_id"]:
                self.current_my_roles = roles["roles"]
                break
        self.compute_permissions()

        # load locally hidden channels
        self.hidden_channels = peripherals.load_json("hidden_channels.json")
        if not self.hidden_channels:
            self.hidden_channels = []
        for hidden in self.hidden_channels:
            self.hide_channel(hidden["channel_id"], hidden["guild_id"])

        # init media
        have_yt_dlp = ", have yt-dlp" if shutil.which(self.config["yt_dlp_path"]) else ""
        have_mpv = ", have mpv" if shutil.which(self.config["mpv_path"]) else ""
        if support_media:
            # must be run after all colors are initialized in endcord.tui
            logger.info(f"ASCII media is supported{have_yt_dlp}{have_mpv}")
            self.curses_media = media.CursesMedia(self.screen, self.config, last_free_color_id)
        else:
            self.curses_media = None
            logger.info("ASCII media is not supported{have_yt_dlp}{have_mpv}")

        if self.config["proxy"]:
            logger.info(f"Using proxy: {self.config["proxy"]}")

        # load dms
        self.dms, self.dms_vis_id = self.gateway.get_dms()
        if self.hide_spam:
            for dm in self.dms:
                if dm["is_spam"]:
                    self.dms_vis_id.remove(dm["id"])
                    self.dms.remove(dm)
        new_activities = self.gateway.get_dm_activities()
        if new_activities:
            self.activities = new_activities

        # load threads, if any
        while self.run:
            new_threads = self.gateway.get_threads()
            if new_threads:
                self.load_threads(new_threads)
            else:
                break

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
            self.state = peripherals.load_json("state.json")
            if self.state is None:
                self.state = {
                    "last_guild_id": None,
                    "last_channel_id": None,
                    "collapsed": [],
                }

        # load summaries
        if self.save_summaries:
            self.summaries = peripherals.load_json("summaries.json")
            if not self.summaries:
                self.summaries = []

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
                self.switch_channel(channel_id, channel_name, guild_id, guild_name, open_member_list=self.member_list_auto_open)
                self.tui.tree_select_active()

        # generate and draw tree
        if not self.tree_format:
            self.update_tree(init_uncollapse=True)
            self.tui.update_chat(["Select channel to load messages", "Loading channels", "Connecting to Discord"], [[[self.colors[0]]]] * 3)

        # auto open member list if enough space
        if (
            self.member_list_auto_open and
            self.active_channel["guild_id"] and
            self.screen.getmaxyx()[1] - self.config["tree_width"] - self.member_list_width - 2 >= 32
        ):
            self.member_list_visible
            self.update_member_list()

        # send new presence
        self.gateway.update_presence(
            self.my_status["status"],
            custom_status=self.my_status["custom_status"],
            custom_status_emoji=self.my_status["custom_status_emoji"],
            rpc=self.my_rpc,
        )

        # start input thread
        self.send_message_thread = threading.Thread(target=self.wait_input, daemon=True, args=())
        self.send_message_thread.start()

        # start RPC server
        if self.enable_rpc:
            self.rpc = rpc.RPC(self.discord, self.my_user_data, self.config)

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
                            data = formatter.replace_discord_url(data, self.active_channel["guild_id"])
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
                                        data = formatter.replace_discord_url(data, self.active_channel["guild_id"])
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
                                        for num2, reaction in enumerate(loaded_message["reactions"]):
                                            if data["emoji_id"] == reaction["emoji_id"] and data["emoji"] == reaction["emoji"]:
                                                loaded_message["reactions"][num2]["count"] += 1
                                                if data["user_id"] == self.my_id:
                                                    loaded_message["reactions"][num2]["me"] = True
                                                break
                                        else:
                                            loaded_message["reactions"].append({
                                                "emoji": data["emoji"],
                                                "emoji_id": data["emoji_id"],
                                                "count": 1,
                                                "me": data["user_id"] == self.my_id,
                                            })
                                        self.update_chat()
                                    elif op == "MESSAGE_REACTION_REMOVE":
                                        for num2, reaction in enumerate(loaded_message["reactions"]):
                                            if data["emoji_id"] == reaction["emoji_id"] and data["emoji"] == reaction["emoji"]:
                                                if reaction["count"] <= 1:
                                                    loaded_message["reactions"].pop(num2)
                                                else:
                                                    loaded_message["reactions"][num2]["count"] -= 1
                                                    if data["user_id"] == self.my_id:
                                                        loaded_message["reactions"][num2]["me"] = False
                                                break
                                        self.update_chat()
                    # handling unseen and mentions
                    if not this_channel or (this_channel and (self.unseen_scrolled or self.ping_this_channel)):
                        # ignoring messages sent by other clients
                        if op == "MESSAGE_CREATE" and new_message["d"]["user_id"] != self.my_id:
                            # skip muted channels
                            muted = False
                            for guild in self.guilds:
                                if guild["guild_id"] == new_message["d"]["guild_id"]:
                                    if guild.get("muted"):
                                        break
                                    for channel in guild["channels"]:
                                        if new_message_channel_id == channel["id"] and (channel.get("muted") or channel.get("hidden")):
                                            muted = True
                                            break
                                    break
                            if not muted:
                                if new_message_channel_id not in [x["channel_id"] for x in self.unseen]:
                                    self.unseen.append({
                                        "channel_id": new_message_channel_id,
                                        "guild_id": new_message["d"]["guild_id"],
                                    })
                                mentions = new_message["d"]["mentions"]
                                if (
                                    new_message["d"]["mention_everyone"] or
                                    bool([i for i in self.my_roles if i in new_message["d"]["mention_roles"]]) or
                                    self.my_id in [[x["id"] for x in mentions]] or
                                    (new_message_channel_id in self.dms_vis_id)
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
                    if (
                        new_typing["channel_id"] == self.active_channel["channel_id"] and
                        new_typing["user_id"] not in self.blocked and
                        new_typing["user_id"] != self.my_id
                    ):
                        if not new_typing["username"]:   # its DM
                            for dm in self.dms:
                                if dm["id"] == new_typing["channel_id"]:
                                    new_typing["username"] = dm["recipients"][0]["username"]
                                    new_typing["global_name"] = dm["recipients"][0]["global_name"]
                                    # no nick in dms
                                    break
                        for num, user in enumerate(self.typing):
                            if user["user_id"] == new_typing["user_id"]:
                                self.typing[num]["timestamp"] = new_typing["timestamp"]
                                break
                        else:
                            self.typing.append(new_typing)
                        self.update_status_line()
                else:
                    break

            # get new summaries
            if self.save_summaries:
                while self.run:
                    new_summary = self.gateway.get_summaries()
                    if new_summary:
                        self.update_summary(new_summary)
                    else:
                        break

            # get new message_ack
            while self.run:
                new_message_ack = self.gateway.get_message_ack()
                if new_message_ack:
                    self.set_seen(new_message_ack["channel_id"], ack=False)
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
                if not self.ignore_typing and my_typing and time.time() >= self.typing_sent + 7:
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
                if self.forum:
                    self.update_forum(self.active_channel["guild_id"], self.active_channel["channel_id"])
                    self.tui.update_chat(self.chat, self.chat_format)
                else:
                    self.update_chat()
                self.update_tree()
                self.update_extra_line(update_only=True)

            # check and update my status
            new_status = self.gateway.get_my_status()
            if new_status:
                self.my_status.update(new_status)
                self.my_status["activities"] = new_status["activities"]
                self.update_status_line()
            new_proto = self.gateway.get_settings_proto()
            if new_proto:
                self.discord_settings = new_proto
                self.update_presence_from_proto()
                self.gateway.update_presence(
                    self.my_status["status"],
                    custom_status=self.my_status["custom_status"],
                    custom_status_emoji=self.my_status["custom_status_emoji"],
                    rpc=self.my_rpc,
                )

            # check changes in presences and update tree
            new_activities = self.gateway.get_dm_activities()
            if new_activities:
                self.activities = new_activities
                self.update_tree()

            # check for new threads
            while self.run:
                new_threads = self.gateway.get_threads()
                if new_threads:
                    self.load_threads(new_threads)
                else:
                    break

            # check for new member presences
            if self.get_members:
                new_members, changed_guilds = self.gateway.get_activities()
                if changed_guilds:
                    self.members = new_members
                    last_index = 99
                    for guild in new_members:   # select guild
                        if guild["guild_id"] == self.active_channel["guild_id"]:
                            self.current_members = guild["members"]
                            last_index = guild["last_index"]
                            break
                    if self.active_channel["guild_id"] in changed_guilds:
                        if self.viewing_user_data["id"]:
                            self.view_profile(self.viewing_user_data)
                        if self.member_list_visible:
                            self.update_member_list(last_index)

            # check for subscribed member presences
            new_members, changed_guilds = self.gateway.get_subscribed_activities()
            if changed_guilds:
                self.subscribed_members = new_members
                for guild in new_members:   # select guild
                    if guild["guild_id"] == self.active_channel["guild_id"]:
                        self.current_subscribed_members = guild["members"]
                        break
                if self.active_channel["guild_id"] in changed_guilds:
                    if self.viewing_user_data["id"]:
                        self.view_profile(self.viewing_user_data)

            # check for tree format changes
            self.check_tree_format()

            # check if new chat chunks needs to be downloaded in any direction
            if not self.forum and self.messages:
                if selected_line == 0 and self.messages[0]["id"] != self.last_message_id:
                    self.get_chat_chunk(past=False)
                elif selected_line >= len(self.chat) - 1 and not self.chat_end:
                    self.get_chat_chunk(past=True)

            # check for message search chunks
            if self.search and self.extra_indexes:
                extra_selected = self.tui.get_extra_selected()
                if extra_selected >= len(self.extra_body) - 2 and not self.search_end:
                    self.extend_search()

            # check if assist is needed
            assist_word, assist_type = self.tui.get_assist()
            if assist_type:
                if assist_type == 100 or (" " in assist_word and assist_type != 5):
                    self.stop_assist()
                elif assist_word != self.assist_word:
                    self.assist(assist_word, assist_type)
            # check member assist query results
            if self.assist_type == 2:
                query_results = self.gateway.get_member_query_resuts()
                if query_results:
                    self.assist(self.assist_word, self.assist_type, query_results=query_results)

            # check gateway for errors
            if self.gateway.error:
                logger.fatal(f"Gateway error: \n {self.gateway.error}")
                sys.exit(self.gateway.error + ERROR_TEXT)

            time.sleep(0.1)   # some reasonable delay
