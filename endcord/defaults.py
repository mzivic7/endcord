settings = {
    "token": None,
    "debug": False,
    "theme": None,
    "rpc": True,
    "downloads_path": None,
    "limit_chat_buffer": 100,
    "limit_channel_cache": 5,
    "download_msg": 25,
    "convert_timezone": True,
    "send_typing": True,
    "desktop_notifications": True,
    "notification_in_active": True,
    "linux_notification_sound": "message",
    "custom_notification_sound": None,
    "ack_throttling": 5,
    "member_list": True,
    "member_list_auto_open": True,
    "use_nick_when_available": True,
    "remember_state": True,
    "reply_mention": True,
    "cache_typed": True,
    "assist": True,
    "cursor_on_time": 0.7,
    "cursor_off_time": 0.5,
    "blocked_mode": 2,
    "hide_spam": True,
    "keep_deleted": False,
    "limit_cache_deleted": 30,
    "tree_show_invisible": False,
    "wrap_around": True,
    "mouse": True,
    "tenor_gif_type": 1,
    "aspell_mode": "normal",
    "aspell_lang": "en_US",
    "media_mute": False,
    "media_cap_fps": 30,
    "rpc_external": True,
    "emoji_as_text": False,
    "native_media_player": False,
    "save_summaries": True,
    "default_stickers": True,
    "only_one_open_server": False,
    "yt_dlp_path": "yt-dlp",
    "yt_dlp_format": 18,
    "mpv_path": "mpv",
    "client_properties": "default",
    "custom_user_agent": None,
    "proxy": None,
    "custom_host": None,
    "disable_easter_eggs": False,
}
theme = {
    "tree_width": 32,
    "extra_window_height": 6,
    "member_list_width": 20,
    "format_message": "[%timestamp] <%username> | %content %edited",
    "format_newline": "                       %content",
    "format_reply": "[REPLY] <%username> | ┌──> [%timestamp] %content",
    "format_reactions": "[REACT]                └──< %reactions",
    "format_one_reaction": "%count:%reaction",
    "format_timestamp": "%H:%M",
    "format_status_line_l": " %global_name (%username) - %status  %unreads %action %typing",
    "format_status_line_r": None,
    "format_title_line_l": " %server: %channel",
    "format_title_line_r": "%tabs",
    "format_title_tree": " endcord  %task",
    "format_rich": "%type %name - %state - %details",
    "format_tabs": "%num - %name",
    "format_prompt": "[%channel] > ",
    "format_forum": "[%timestamp] - <%msg_count> - %thread_name",
    "format_forum_timestamp": "%Y-%m-%d",
    "format_search_message": "%channel: [%date] <%username> | %content",
    "edited_string": "(edited)",
    "quote_character": "║",
    "reactions_separator": "; ",
    "tabs_separator": " | ",
    "chat_date_separator": "─",
    "format_date": " %B %d, %Y ",
    "limit_username": 10,
    "limit_global_name": 15,
    "limit_typing_string": 30,
    "limit_prompt": 15,
    "limit_thread_name": 0,
    "limit_tabs_string": 40,
    "tree_vert_line": "│",
    "tree_drop_down_vline": "│",
    "tree_drop_down_hline": "─",
    "tree_drop_down_intersect": "├",
    "tree_drop_down_corner": "└",
    "tree_drop_down_pointer": ">",
    "tree_drop_down_thread": "<",
    "tree_drop_down_forum": "◆",
    "tree_dm_status": "●",
    "username_role_colors": True,
    "color_default": [-1, -1],
    "color_chat_mention": [209, 234],
    "color_chat_blocked": [242, -1],
    "color_chat_deleted": [95, -1],
    "color_chat_selected": [233, 255],
    "color_chat_separator": [242, -1, "i"],
    "color_status_line": [233, 255],
    "color_extra_line": [233, 245],
    "color_title_line": [233, 255],
    "color_extra_window": [-1, -1],
    "color_prompt": [255, -1],
    "color_input_line": [255, -1],
    "color_cursor": [233, 255],
    "color_misspelled": [222, -1],
    "color_tree_default": [255, -1],
    "color_tree_selected": [233, 255],
    "color_tree_muted": [242, -1],
    "color_tree_active": [255, 234],
    "color_tree_unseen": [255, -1, "b"],
    "color_tree_mentioned": [197, -1],
    "color_tree_active_mentioned": [197, 234],
    "color_format_message": [[-1, -1], [242, -2, 0, 0, 7], [25, -2, 0, 8, 9], [25, -2, 0, 19, 20]],
    "color_format_newline": None,
    "color_format_reply": [[245, -1], [67, -2, 0, 0, 7], [25, -2, 0, 8, 9], [25, -2, 0, 19, 20], [-1, -2, 0, 21, 27]],
    "color_format_reactions": [[245, -1], [131, -2, 0, 0, 7], [-1, -2, 0, 23, 27]],
    "color_format_forum": [[-1, -1], [242, -2, 0, 0, 12], [25, -2, 0, 15, 20]],
    "color_chat_edited": [241, -1],
    "color_chat_url": [153, -1, "u"],
    "color_chat_spoiler": [245, -1],
    "color_chat_code": [250, 233],
    "media_ascii_palette": "  ..',;:c*loexk#O0XNW",
    "media_saturation": 1.2,
    "media_font_scale": 2.25,
    "media_color_bg": 16,
    "media_bar_ch": "━",
}


keybindings = {
    # tree
    "tree_up": 575,   # Ctrl+Up
    "tree_down": 534,   # Ctrl+Donw
    "tree_select": 0,   # Ctrl+Space
    "tree_collapse_threads": "ALT+116",   # Alt+T
    "tree_join_thread": "ALT+106",   # Alt+J
    "channel_info": "ALT+105",   # Alt+I
    "copy_channel_link": "ALT+85",   # Alt+Shift+U
    # input line
    "word_left": 554,   # Ctrl+Left
    "word_right": 569,   # Ctrl+Right
    "ins_newline": 14,   # Ctrl+N
    "undo": "ALT+122",   # Alt+Z
    "redo": "ALT+90",   # Alt+Shift+Z
    "select_left": 393,   # Shift+Left
    "select_right": 402,   # Shift+Right
    "select_word_left": 555,   # Ctrl+Shift+Left
    "select_word_right": 570,   # Ctrl+Shift+Right
    "select_all": "ALT+97",   # Alt+A
    "copy_sel": "ALT+99",   # Alt+C
    "cut_sel": "ALT+120",   # Alt+X
    # chat
    "reply": 18,   # Ctrl+R
    "edit": 5,   # Ctrl+E
    "delete": 4,   # Ctrl+D
    "toggle_ping": 16,   # Ctrl+P
    "scroll_bottom": 2,   # Ctrl+B
    "go_replied": 7,   # Ctrl+G
    "download": 23,   # Ctrl+W
    "upload": 21,   # Ctrl+U
    "browser": 15,   # Ctrl+O
    "copy_msg": 8,   # Ctrl+H
    "view_media": 22,   # Ctrl+V
    "spoil": 20,   # Ctrl+T
    "search": 6,   # Ctrl+F
    "profile_info": "ALT+112",   # Alt+P
    "show_summaries": "ALT+115",   # Alt+S
    "copy_message_link": "ALT+117",   # Alt+U
    "go_channel": "ALT+103",   # Alt+G
    "add_reaction": "ALT+101",   # Alt+E
    "record_audio": "ALT+114",   # Alt+R
    "show_reactions": "ALT+119",   # Alt+W
    # extra line
    "attach_prev": "ALT+552",   # Alt+Left
    "attach_next": "ALT+567",   # Alt+Right
    "attach_cancel": 11,   # Ctrl+K
    # extra window
    "extra_up": 573,   # Alt+Up
    "extra_down": 532,   # Alt+Down
    "extra_select": "ALT+10",   # Alt+Enter
    # media
    "media_pause": 32,   # C
    "media_replay": 122,   # Z
    "media_seek_forward": 261,   # Right
    "media_seek_backward": 260,   # Left
    # other
    "redraw": 12,   # Ctrl+L
    "cancel": 24,   # Ctrl+X
    "forum_join_thread": "ALT+107",   # Alt+K
    "cycle_status": "ALT+118",   # Alt+V
    "toggle_member_list": "ALT+109",   # Alt+M
    "toggle_tab": "ALT+98",   # Alt+B
    "command_palette": 31,   # Ctrl+/
}


windows_override_keybindings = {
    "tree_up": 480,   # Ctrl+Up
    "tree_down": 481,   # Ctrl+Donw
    "tree_select": 1,   # Ctrl+A
    "word_left": 443,   # Ctrl+Left
    "word_right": 444,   # Ctrl+Right
    "copy_msg": "ALT+108",   # Alt+L
    "view_media": "ALT+121",   # Alt+Y
}
