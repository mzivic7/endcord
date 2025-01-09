import logging
import threading
import time

from endcord import discord, formatter, gateway, peripherals, tui

logger = logging.getLogger(__name__)
APP_NAME = "endcord"
MESSAGE_UPDATE_ELEMENTS = ("id", "edited", "content", "mentions", "mention_roles", "mention_everyone", "embeds")


class Endcord:
    """Main app class"""

    def __init__(self, screen, config):
        self.screen = screen
        self.config = config

        # load often used values from config
        self.limit_chat_buffer = max(min(config["limit_chat_buffer"], 1000), 50)
        self.limit_typing = max(config["limit_typing_string"], 25)
        self.send_my_typing = config["send_typing"]
        self.ack_throttling = max(config["ack_throttling"], 3)
        self.convert_timezone = config["convert_timezone"]
        self.format_title_line_l = config["format_title_line_l"]
        self.format_title_line_r = config["format_title_line_r"]
        self.format_status_line_l = config["format_status_line_l"]
        self.format_status_line_r = config["format_status_line_r"]
        self.format_title_tree = config["format_title_tree"]
        self.use_nick = config["use_nick_when_avail"]
        self.reply_mention = config["reply_mention"]
        self.cache_typed = config["cache_typed"]
        self.enable_notifications = config["desktop_notifications"]
        self.notification_sound = config["linux_notification_sound"]
        self.blocked_mode = config["blocked_mode"]
        self.hide_spam = config["hide_spam"]
        self.keep_deleted = config["keep_deleted"]
        self.colors = peripherals.extract_colors(config)

        # variables
        self.run = False
        self.active_channel = {
            "guild_id": None,
            "channel_id": None,
            "guild_name": None,
            "channel_name": None,
        }
        self.guilds = []
        self.guilds_settings = []
        self.all_roles = []
        self.current_roles = []
        self.current_channels = []
        self.dms_setting = []
        self.summaries = []
        self.input_store = []
        self.running_task = ""

        # initialize stuff
        self.discord = discord.Discord(config["token"])
        self.gateway = gateway.Gateway(config["token"])
        self.tui = tui.TUI(self.screen, self.config)
        self.colors = self.tui.init_colors(self.colors)
        self.tui.update_status_line("CONNECTING")
        self.tui.update_chat(["Connecting to Discord"], [[self.colors[0]]] * 1)
        self.my_id = self.discord.get_my_id()
        self.my_user_data = self.discord.get_user(self.my_id)
        self.reset()
        self.gateway.connect()
        self.gateway_state = self.gateway.get_state()
        self.chat_dim, self.tree_dim  = self.tui.get_dimensions()
        self.state = {
            "last_guild_id": None,
            "last_channel_id": None,
            "collapsed": [],
        }
        self.tree = []
        self.tree_format = []
        self.tree_metadata = []
        self.my_roles = []
        self.reset_actions()
        self.main()


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


    def reconnect(self):
        """Fetch updated data from gateway and rebuild chat after reconnecting"""
        self.update_running_task("Reconnecting")
        self.reset()
        self.guilds = self.gateway.get_guilds()
        self.guilds_settings = self.gateway.get_guilds_settings()
        self.all_roles = self.gateway.get_roles()
        self.dms, self.dms_id = self.gateway.get_dms()
        if self.hide_spam:
            for dm in self.dms:
                if dm["is_spam"]:
                    self.dms_id.remove(dm["id"])
                    self.dms.remove(dm)
        self.dms_setting = self.gateway.get_dms_settings()
        self.pings = self.gateway.get_pings()
        self.unseen = self.gateway.get_unseen()
        self.blocked = self.gateway.get_blocked()
        self.current_roles = []   # dm has no roles
        for roles in self.all_roles:
            if roles["guild_id"] == self.active_channel["guild_id"]:
                self.current_roles = roles["roles"]
                break
        self.current_channels = []   # dm has no multiple channels
        for guild_channels in self.guilds:
            if guild_channels["guild_id"] == self.active_channel["guild_id"]:
                self.current_channels = guild_channels["channels"]
                break
        self.gateway.update_presence(
            self.my_status["status"],
            self.my_status["custom_status"],
            self.my_status["custom_status_emoji"],
        )
        self.gateway.subscribe(self.active_channel["channel_id"], self.active_channel["guild_id"])
        self.update_chat(keep_selected=False)
        self.update_tree()

        self.update_running_task()
        logger.info("Reconnect complete")


    def switch_channel(self, channel_id, channel_name, guild_id, guild_name):
        """
        All that should be done when switching channel.
        If it is DM, guild_id and guild_name should be None.
        """
        self.active_channel["guild_id"] = guild_id
        self.active_channel["guild_name"] = guild_name
        self.active_channel["channel_id"] = channel_id
        self.active_channel["channel_name"] = channel_name
        self.update_running_task("Switching channel")

        if self.active_channel["guild_id"]:
            my_user = self.discord.get_user_guild(self.my_id, self.active_channel["guild_id"])
            self.my_roles = my_user["roles"] if my_user["roles"] else []
        else:
            my_user = self.discord.get_user(self.my_id)
            self.my_rolse = []

        self.current_roles = []
        for roles in self.all_roles:
            if roles["guild_id"] == self.active_channel["guild_id"]:
                self.current_roles = roles["roles"]
                break
        self.current_channels = []
        for guild_channels in self.guilds:
            if guild_channels["guild_id"] == self.active_channel["guild_id"]:
                self.current_channels = guild_channels["channels"]
                break
        self.messages = self.discord.get_messages(self.active_channel["channel_id"])
        if self.messages:
            self.last_message_id = self.messages[0]["id"]

        self.typing = []
        self.gateway.subscribe(self.active_channel["channel_id"], self.active_channel["guild_id"])
        self.set_seen(self.active_channel["channel_id"])

        self.update_chat(keep_selected=False)
        self.update_prompt()
        if self.tree_format:
            self.update_tree()
        else:
            self.init_tree()

        # save state
        if self.config["remember_state"]:
            self.state["last_guild_id"] = guild_id
            self.state["last_channel_id"] = channel_id
            peripherals.save_state(self.state)

        self.update_running_task()
        logger.debug("Channel switching complete")


    def add_to_store(self, channel_id, text):
        """Adds entry to input line store"""
        if self.cache_typed:
            done = False
            for num, channel in enumerate(self.input_store):
                if channel["id"] == channel_id:
                    self.input_store["content"] = text
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


    def update_running_task(self, task=""):
        """Update currently running long task"""
        self.running_task = task
        self.update_status_line()


    def wait_input(self):
        """Thread that handles getting input, formatting, sending, replying, editing, deleting message and switching channel"""
        logger.info("Input handler loop started")

        while self.run:
            if self.editing["id"]:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.editing["content"], reset=False)
            elif self.replying["content"]:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.replying["content"], reset=False, keep_cursor=True)
            elif self.deleting["content"]:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt)
            elif self.warping is not None:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.warping, reset=False, keep_cursor=True, scroll_bot=True)
            elif self.going_to is not None:
                input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=self.going_to, reset=False, keep_cursor=True)
            else:
                restore_text = None
                if self.cache_typed:
                    for num, channel in enumerate(self.input_store):
                        if channel["id"] == self.active_channel["channel_id"]:
                            restore_text = self.input_store.pop(num)["content"]
                            break
                if restore_text:
                    input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt, init_text=restore_text, reset=False)
                else:
                    input_text, chat_sel, tree_sel, action = self.tui.wait_input(self.prompt)
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
            elif action == 1:
                self.reset_actions()
                msg_index = self.lines_to_msg(chat_sel + 1)
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
            elif action == 2:
                msg_index = self.lines_to_msg(chat_sel + 1)
                if self.messages[msg_index]["user_id"] == self.my_id:
                    if "deleted" not in self.messages[msg_index]:
                        self.reset_actions()
                        self.editing = {
                            "id": self.messages[msg_index]["id"],
                            "content": self.messages[msg_index]["content"],
                        }
                        self.update_status_line()

            # set delete
            elif action == 3:
                msg_index = self.lines_to_msg(chat_sel + 1)
                if self.messages[msg_index]["user_id"] == self.my_id:
                    if "deleted" not in self.messages[msg_index]:
                        self.add_to_store(self.active_channel["channel_id"], input_text)
                        self.reset_actions()
                        self.deleting = {
                            "id": self.messages[msg_index]["id"],
                            "content": input_text,
                        }
                        self.update_status_line()

            # escape key
            elif action == 5:
                if self.replying["id"]:
                    self.reset_actions()
                    self.replying["content"] = input_text
                else:
                    self.reset_actions()
                self.update_status_line()

            # toggle mention ping
            elif action == 6:
                self.replying["mention"] = None if self.replying["mention"] is None else not self.replying["mention"]
                self.update_status_line()

            # warping to chat bottom
            elif action == 7:
                self.warping = input_text
                if self.messages[0]["id"] != self.last_message_id:
                    self.update_running_task("Downloading chat")
                    self.messages = self.discord.get_messages(self.active_channel["channel_id"])
                    self.update_chat()
                    self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
                    self.update_running_task()

            # go to replied message
            elif action == 8:
                self.going_to = input_text
                msg_index = self.lines_to_msg(chat_sel + 1)
                if self.messages[msg_index]["referenced_message"]:
                    reference_id = self.messages[msg_index]["referenced_message"]["id"]
                    if reference_id:
                        self.go_to_message(reference_id)

            # send message
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
                else:
                    self.discord.send_message(
                        self.active_channel["channel_id"],
                        input_text,
                        reply_id=self.replying["id"],
                        reply_channel_id=self.active_channel["channel_id"],
                        reply_guild_id=self.active_channel["guild_id"],
                        reply_ping=self.replying["mention"],
                    )
                self.reset_actions()
                self.update_status_line()

            # deleting on enter
            elif input_text == "" and self.deleting["id"]:
                self.discord.send_delete_message(
                    channel_id=self.active_channel["channel_id"],
                    message_id=self.deleting["id"],
                )
                self.reset_actions()
                self.update_status_line()


    def get_chat_chunk(self, past=True):
        """Get chunk of chat in specified direction and add it to existing chat, trim chat to limited size and trigger update_chat"""
        self.update_running_task("Downloading chat")
        start_id = self.messages[-int(past)]["id"]

        if past:
            logger.debug(f"Requesting chat chunk before {start_id}")
            new_chunk = self.discord.get_messages(self.active_channel["channel_id"], before=start_id)
            self.messages = self.messages + new_chunk
            all_msg = len(self.messages)
            selected_line = len(self.chat) - 1
            selected_msg = self.lines_to_msg(selected_line)
            self.messages = self.messages[-self.limit_chat_buffer:]
            if len(new_chunk):
                logger.info(1)
                self.update_chat(keep_selected=None)
                logger.info(2)
                # when messages are trimmed, keep same selecteed position
                if len(self.messages) != all_msg:
                    selected_msg_new = selected_msg - (all_msg - len(self.messages))
                    selected_line = self.msg_to_lines(selected_msg_new)
                self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
                logger.info(3)
                self.tui.set_selected(selected_line)
                logger.info(4)

        else:
            logger.debug(f"Requesting chat chunk after {start_id}")
            new_chunk = self.discord.get_messages(self.active_channel["channel_id"], after=start_id)
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
        self.update_running_task()


    def go_to_message(self, message_id):
        """Check if message is in current chat buffer, if not: load chunk around specified message id and select message"""
        found = False
        for num, message in enumerate(self.messages):
            if message["id"] == message_id:
                self.tui.set_selected(self.msg_to_lines(num + 1) - 2)   # idk
                found = True
                break

        if not found:
            new_messages = self.discord.get_messages(self.active_channel["channel_id"], around=message_id)
            if new_messages:
                self.messages = new_messages
            self.update_chat(keep_selected=False)

            for num, message in enumerate(self.messages):
                if message["id"] == message_id:
                    self.tui.allow_chat_selected_hide(self.messages[0]["id"] == self.last_message_id)
                    self.tui.set_selected(self.msg_to_lines(num + 1) - 2)
                    break


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
            self.config["format_message"],
            self.config["format_newline"],
            self.config["format_reply"],
            self.config["format_reactions"],
            self.config["format_one_reaction"],
            self.config["format_timestamp"],
            self.config["edited_string"],
            self.config["reactions_separator"],
            self.chat_dim[1],
            self.my_id,
            self.my_roles,
            self.colors,
            self.blocked,
            limit_username=self.config["limit_username"],
            limit_global_name=self.config["limit_global_name"],
            use_nick=self.use_nick,
            convert_timezone=self.convert_timezone,
            blocked_mode=self.blocked_mode,
            keep_deleted=self.keep_deleted,
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
                self.running_task,
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
            self.running_task,
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
                self.running_task,
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
                self.running_task,
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
                self.running_task,
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


    def init_tree(self):
        """Generate initial channel tree"""
        self.tree, self.tree_format, self.tree_metadata = formatter.generate_tree(
            self.dms,
            self.guilds,
            self.dms_setting,
            self.guilds_settings,
            self.unseen,
            self.pings,
            self.guild_positions,
            self.state["collapsed"],
            self.active_channel["channel_id"],
            self.config["tree_drop_down_vline"],
            self.config["tree_drop_down_hline"],
            self.config["tree_drop_down_corner"],
        )
        self.tui.update_tree(self.tree, self.tree_format)


    def update_tree(self, set_seen=None):
        """Updates existing channel tree"""
        self.tree_format = formatter.update_tree(
            self.tree_format,
            self.tree_metadata,
            self.unseen,
            self.pings,
            self.active_channel["channel_id"],
            set_seen,
        )
        self.tui.update_tree(self.tree, self.tree_format)


    def lines_to_msg(self, lines):
        """Convert line index from formatted chat to message index"""
        total_len = 0
        for num, msg_len in enumerate(self.chat_indexes):
            total_len += msg_len
            if total_len >= lines:
                return num
        return 0


    def msg_to_lines(self, msg):
        """Convert message index to line index from formatted chat"""
        return sum(self.chat_indexes[:msg]) + 1


    def set_seen(self, channel_id, force=False):
        """Set channel as seen if it is not already seen.
        Force will send even if its not marked as unseen, used for active channel."""
        if channel_id in self.unseen or force:
            if not force:
                self.unseen.remove(channel_id)
            self.update_tree(set_seen=channel_id)
            self.discord.send_ack_message(channel_id, self.messages[0]["id"])
            if channel_id in self.pings:
                self.pings.remove(channel_id)
            if self.enable_notifications:
                for num, notification in enumerate(self.notifications):
                    if notification["channel_id"] == channel_id:
                        notification_id = self.notifications.pop(num)["notification_id"]
                        peripherals.notify_remove(notification_id)
                        break


    def main(self):
        """Main app method"""
        logger.info("Main started")
        logger.info("Waiting for ready signal from gateway")
        while not self.gateway.get_ready():
            time.sleep(0.2)
        self.discord_settings = self.discord.get_settings_proto(1)
        self.guild_positions = []
        for folder in self.discord_settings["guildFolders"]["folders"]:
            self.guild_positions += folder["guildIds"]
        self.my_status = {
            "status": self.discord_settings["status"]["status"],
            "custom_status": self.discord_settings["status"]["customStatus"]["text"],
            "custom_status_emoji": self.discord_settings["status"]["customStatus"]["emojiName"],
            "activities": [],
            "client_state": "online",
        }
        self.gateway_state = 1
        logger.info("Gateway is ready")

        self.tui.update_chat(["Loading channels", "Connecting to Discord"], [[self.colors[0]]] * 2)
        self.guilds = self.gateway.get_guilds()
        self.guilds_settings = self.gateway.get_guilds_settings()
        self.all_roles = self.gateway.get_roles()
        self.dms, self.dms_id = self.gateway.get_dms()
        if self.hide_spam:
            for dm in self.dms:
                if dm["is_spam"]:
                    self.dms_id.remove(dm["id"])
                    self.dms.remove(dm)
        self.dms_setting = self.gateway.get_dms_settings()
        self.pings = self.gateway.get_pings()
        self.unseen = self.gateway.get_unseen()
        self.blocked = self.gateway.get_blocked()

        # restore last state
        if self.config["remember_state"]:
            self.state = peripherals.load_state()
        if self.state is None:
            self.state = {
                "last_guild_id": None,
                "last_channel_id": None,
                "collapsed": [],
            }
        if self.state["last_channel_id"]:
            self.tui.update_chat(["Loading messages", "Loading channels", "Connecting to Discord"], [[self.colors[0]]] * 3)
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
                self.tui.set_tree_select_active()

        if not self.tree_format:
            self.init_tree()
            self.tui.update_chat(["Select channel to load messages", "Loading channels", "Connecting to Discord"], [[self.colors[0]]] * 3)

        self.gateway.update_presence(
            self.my_status["status"],
            self.my_status["custom_status"],
            self.my_status["custom_status_emoji"],
        )
        self.run = True
        self.send_message_thread = threading.Thread(target=self.wait_input, daemon=True, args=())
        self.send_message_thread.start()

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
                            del (data["guild_id"], data["channel_id"])
                            # if latest message is loaded - not viewing old message chunks
                            if self.messages[0]["id"] == self.last_message_id:
                                self.messages.insert(0, data)
                            self.last_message_id = new_message["d"]["id"]
                            self.update_chat(change_amount=1)
                            if not self.unseen_scrolled:
                                if time.time() - self.sent_ack_time > self.ack_throttling:
                                    self.set_seen(self.active_channel["channel_id"], force=True)
                                    self.sent_ack_time = time.time()
                                    self.pending_ack = False
                                else:
                                    self.pending_ack = True
                        else:
                            for num, loaded_message in enumerate(self.messages):
                                if data["id"] == loaded_message["id"]:
                                    if op == "MESSAGE_UPDATE":
                                        for element in MESSAGE_UPDATE_ELEMENTS:
                                            loaded_message[element] = data[element]
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
                    # handling unseen and mentions
                    if not this_channel or (this_channel and self.unseen_scrolled):
                        if op == "MESSAGE_CREATE":
                            if new_message_channel_id not in self.unseen:
                                self.unseen.append(new_message_channel_id)
                            mentions = []
                            for mention in new_message["d"]["mentions"]:
                                mentions.append(mention["id"])
                            if (
                                new_message["d"]["mention_everyone"] or
                                bool([i for i in self.my_roles if i in new_message["d"]["mention_roles"]]) or
                                self.my_id in mentions or
                                new_message_channel_id in self.dms_id
                            ):
                                self.pings.append(new_message_channel_id)
                                # notifications
                                if self.enable_notifications:
                                    skip = False
                                    for notification in self.notifications:
                                        if notification["channel_id"] == new_message_channel_id:
                                            skip = True
                                    if not skip:
                                        notification_id = peripherals.notify_send(
                                            APP_NAME,
                                            f"{new_message["d"]["global_name"]}:\n{new_message["d"]["content"]}",
                                            sound=self.notification_sound,
                                        )
                                        self.notifications.append({
                                            "notification_id": notification_id,
                                            "channel_id": new_message_channel_id,
                                        })
                            self.update_tree()
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
                    if ack_channel_id in self.unseen:
                        self.unseen.remove(ack_channel_id)
                        self.update_tree(set_seen=ack_channel_id)
                        if ack_channel_id in self.pings:
                            self.pings.remove(ack_channel_id)
                        if self.enable_notifications:
                            for num, notification in enumerate(self.notifications):
                                if notification["channel_id"] == ack_channel_id:
                                    notification_id = self.notifications.pop(num)["notification_id"]
                                    peripherals.notify_remove(notification_id)
                                    break
                else:
                    break

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
            new_chat_dim, _  = self.tui.get_dimensions()
            if new_chat_dim != self.chat_dim:
                self.chat_dim = new_chat_dim
                self.update_chat()
                self.update_tree()

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
            new_tree_format = self.tui.get_tree_format()
            if new_tree_format:
                self.tree_format = new_tree_format
                # get all collapsed channels/servers and save them
                collapsed = []
                for num, code in enumerate(self.tree_format):
                    if code < 300 and (code % 10) == 0:
                        collapsed.append(self.tree_metadata[num]["id"])
                self.state["collapsed"] = collapsed
                peripherals.save_state(self.state)

            # check if new chat chunks needs to be downloaded in any direction
            if selected_line == 0 and self.messages[0]["id"] != self.last_message_id:
                self.get_chat_chunk(past=False)
            elif selected_line >= len(self.chat) - 1:
                self.get_chat_chunk(past=True)

            time.sleep(0.1)   # some reasonable delay
