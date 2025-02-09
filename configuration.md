## Default config values with explanations:
Note: always put string in `""`. To use `"` inside the string escape it like this: `\"`. To use `\` escape it like this: `\\`. These are counted as single character.

### Main
- `token = None`  
    Your discord token. Provide it here or as a command argument.
- `debug = False`  
    Enable debug mode.
- `rpc = True`  
    Enable RPC server. For now Linux only.
- `theme = None`  
    Custom theme path, or name of file in `Themes` directory.  Set to None to use theme from `config.ini` `[theme]` section or defaults.
- `downloads_path = None`  
    Directory where to store downloaded files. Set to None to use 'Downloads' directory (cross platform).
- `limit_chat_buffer = 100`  
    Number of messages kept in chat buffer. Initial buffer is 50 messages and is expanded in scroll direction. Limit: 50-1000.
- `convert_timezone = True`  
    Use local time. If set to False, will show UTC time.
- `send_typing = True`  
    Allow `[your_username] is typing...` to be sent.
- `desktop_notifications = True`  
    Allow sending desktop notifications when user is pinged/mentioned.
- `notification_in_active = True`  
    Allow sending desktop notifications for mentions even in active channel.
- `linux_notification_sound = "message"`  
    Sound played when notification is displayed. Linux only. Set to None to disable. Sound names can be found in `/usr/share/sounds/freedesktop/stereo`, without extension.
- `ack_throttling = 5`  
    Delay in seconds between each ack send. Minimum is 3s. The larger it is, the longer will `[New unreads]` stay in status line.
- `use_nick_when_avail = True`  
    Replace global_name with nick when it is available.
- `remember_state = True`  
    Remeber last open channel on exit and reopen it on start.
- `reply_mention = True`  
    Ping someone by default when replying.
- `cache_typed = True`  
    Save unsent message when switching channel, and load it when re-opening that channel.
- `cursor_on_time = 0.7`  
    Time in seconds the cursor stays ON. Set to None or 0 to disable cursor blinking.
- `cursor_off_time = 0.5`  
    Time in seconds the cursor stays OFF. Set to None or 0 to disable cursor blinking.
- `blocked_mode = 1`  
    What to do with blocked/ignored messages:
    0 - No blocking  
    1 - Mask blocked messages  
    2 - Hide blocked messages  
- `hide_spam = True`  
    Wether to hide or show spam DM request channels in DM list.
- `keep_deleted = False`  
    Wether to keep deleted messages in chat, with different color, or remove them.
- `deleted_cache_limit = 50`  
    Limit lumber of cached deleted messages per channel.
- `tenor_gif_type = 1`  
    Type of the media when gif is downloaded from tenor:  
    0 - gif HD  
    1 - gif UHD  
    2 - mp4 Video  
- `aspell_mode`  
    [Aspell](http://aspell.net/) filter mode.  
    Available options: `ultra` / `fast` / `normal` / `slow` / `bad-spellers`  
    Set to None to disable spell checking.  
    More info [here](http://aspell.net/man-html/Notes-on-the-Different-Suggestion-Modes.html#Notes-on-the-Different-Suggestion-Modes).  
- `aspell_lang = en_US`  
    Language dictionary for aspell.  
    To list all installed languages, run `aspell dump dicts`.
    Additional dictionaries can be installed with package manager or downloaded [here](https://ftp.gnu.org/gnu/aspell/dict/0index.html) (extract archive and run "configure" script).  
- `mute_video = False`  
    Wether to mute video or not. If tru, will not initialize audio at all.

### Theme
- `tree_width = 32`  
    Width of channel tree in characters.
- `format_message = "[%timestamp] <%username> | %content %edited"`  
    Formatting for message base string. See [format_message](##format_message) for more info.
- `format_newline = "                       %content"`  
    Formatting for each newline string after message base. See [format_newline](##format_newline) for more info.
- `format_reply = "[REPLY] <%username> | /--> [%timestamp] %content"`  
    Formatting for replied message string. It is above message base. See [format_reply](##format_reply) for more info.
- `format_reactions = "[REACT]                \\--< %reactions"`  
    Formatting for message reactions string. It is bellow last newline string. See [format_reactions](##format_reactions) for more info.
- `format_one_reaction = "%count:%reaction"`  
    Formatting for single reaction string. Reactions string is assembled by joining these strings with `reactions_separator` in between. See [format_one_reaction](##format_one_reaction) for more info.
- `format_timestamp = "%H:%M"`  
    Format for timestamps in messages. Same as [datetime format codes](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes)
- `format_status_line_l = " %global_name (%username) - %status  %unreads %action %typing"`  
    Formatting for left side of status line. See [format_status](##format_status) for more info. Set to None to disable.
- `format_status_line_r = None`  
    Formatting for right side of status line. See [format_status](##format_status) for more info.
- `format_title_line_l = " %server: %channel"`  
    Formatting for left side of title line. See [format_status](##format_status) for more info. Set to None to disable.
- `format_title_line_r = "%rich"`  
    Formatting for right side of title line. See [format_status](##format_status) for more info.
- `format_title_tree = " endcord  %task"`  
    Formatting for channel tree title line. See [format_status](##format_status) for more info. Set to None to disable.
- `format_rich = "playing: %name - %state - %details "`  
    Formatting for rich presence string used in `format_status`. See [format_rich](##format_rich) for more info.
- `format_prompt = "[%channel] > "`  
    Formatting for prompt line. See [format_prompt](##format_prompt) for more info.
- `edited_string = "(edited)"`  
    A string added to the end of the message when it is edsited.
- `reactions_separator = "; "`  
    A string placed between two reactions.
- `chat_date_separator = "-"`  
    A single character used to draw horizontal line for separating messages sent on different days. Set to None to disable date separator.
- `format_date = " %B %d, %Y "`  
    Format for timestamps in `chat_date_separator`. Same as [datetime format codes](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes).
- `limit_username = 10`  
    Limit to the username string length.
- `limit_global_name = 15`  
    Limit to the global name string length.
- `limit_typing_string = 32`  
    Limit to the typing string length. Also limits `%details` and `%state` in `format_rich`
- `tree_vert_line = "|"`  
    A single character used to draw vertical line separating channel tree and the chat.
- `tree_drop_down_vline = "|"`  
    A single character used to draw vertical line in tree drop down menus.
- `tree_drop_down_hline = "-"`  
    A single character used to draw horizontal line in tree drop down menus.
- `tree_drop_down_intersect = "|"`  
    A single character used to draw intersections in tree drop down menus.
- `tree_drop_down_corner = "\\"`  
    A single character used to draw corners in tree drop down menus.
- `tree_drop_down_pointer = ">"`  
    A single character used to draw pointer in tree drop down menus. Pointer is used to designate categories and servers.
- `username_role_colors = True`  
    Allow `%username` and `%global_name` to have color of primary role.
- `ascii_palette = "  ..',;:c*loexkO0XNW#%"`  
    Characters used to draw in terminal. From darkest to brightest. Same character can be repeated. Number of characters is not fixed.
- `saturation = 1.2`  
    Saturation correction applied to image in order to make colors more visible. Adjust if changing `ascii_palette` or color_media_bg.
- `target_fps = 30`  
    Target framerate when playing videos, high values may result in AV-desyncing and higher CPU usage.
- `font_scale = 2.25`  
    Font height/width ratio. Change if picture dimensions ratio is wrong in terminal.

### Colors and attributes
Colors are part of the theme, configured as 2 or 3 values in a list: `[foreground, background, attribute]`  
Foreground and background are ANSI [codes](https://gist.github.com/ConnerWill/d4b6c776b509add763e17f9f113fd25b#256-colors). -1 is terminal default color.  
Set to None to use terminal default colors.  
Attribute is optional string: `"b"/"bold"`, `"u"/"underline"`, `"i"/"italic"`
Example: `[209, 234, "u"]` - 209 is foreground, 234 is background, "u" is underline.  
All colors starting with `color_format` are formatted like this:  
`[[fg, bg, attr], [fg, bg, attr, start, end], [...]...]`  
First `[fg, bg, attr]` is base color for whole context. If `bg` is -1, `bg` from `color_chat_default` and `color_chat_mention` is used. Same for `fg`.  
Every next list has additional `start` and `end`- indexes on a line where color is applied. If `bg` is -2, `bg` from base color is used. -1 is terminal default color. Same for `fg`.  
- `color_chat_default = [-1, -1]`  
    Base color formatting for text. No attribute.
- `color_chat_mention = [209, 234]`  
    Color for highlighted messages containing mentions (reply with ping included) and mention roles.
- `color_chat_blocked = [242, -1]`  
    Color for blocked messages if `block_mode = 1`.
- `color_chat_deleted = [95, -1]`  
    Color for deleted mesages when `keep_deleted = True`.
- `color_chat_selected = [233, 255]`  
    Color for selected line in chat.
- `color_chat_separator = [242, -1, "i"]`  
    Color for date separator line in chat.
- `color_status_line = [233, 255]`  
    Color for status line.
- `color_extra_line = [233, 245]`  
    Color for extra line, drawn above status line.
- `"color_title_line" = [233, 255]`  
    Color for chat title line and tree title line.
- `color_prompt = [255, -1]`  
    Color for prompt line.
- `color_input_line = [255, -1]`  
    Base color for input line.
- `color_cursor = [233, 255]`  
    Color for cursor in input line.
- `color_misspelled = [222, -1]`  
    Color for misspelled words in input line.
- `color_tree_default = [255, -1]`  
    Base color for tree components. No attribute.
- `color_tree_selected = [233, 255]`  
- `color_tree_muted = [242, -1]`  
- `color_tree_active = [255, 234]`  
- `color_tree_unseen = [255, -1, "b"]`  
- `color_tree_mentioned = [197, -1]`  
- `color_tree_active_mentioned = [197, 234]`
- `color_format_message = [[-1, -1], [242, -2, 0, 0, 7], [25, -2, 0, 8, 9], [25, -2, 0, 19, 20]]`  
    Color format for message base string. Corresponding to `format_message`.
- `color_format_newline = None`  
    Color format for each newline string after message base. Corresponding to `format_newline`.
- `color_format_reply = [[245, -1], [67, -2, 0, 0, 7], [25, -2, 0, 8, 9], [25, -2, 0, 19, 20], [-1, -2, 0, 21, 27]]`  
    Color format for replied message string. Corresponding to `format_reply`.
- `color_format_reactions = [[245, -1], [131, -2, 0, 0, 7], [-1, -2, 0, 23, 27]]`  
    Color format for message reactions string. Corresponding to `format_reactions`.
- `color_chat_edited = [241, -1]`  
    Color for `edited_string`.
- `color_chat_url = [153, -1, "u"]`  
    Color for urls in message content and embeds.
- `color_media_bg = -1`  
    single color value for background color when showing media.

## format_message
- `%content` - message text
- `%username` - of message author
- `%global_name` - of message author
- `%timestamp` - formatted with `format_timestamp`
- `%edited` - replaced with `edited_string`  
Note: everything after `%content` may be pushed to newline.

## format_newline
- `%content` - this is remainder of previous line
- `%timestamp` - formatted with `format_timestamp`

## format_reply
- `%content` - of replied message
- `%username` - of replied message autor
- `%global_name` - of replied message autor
- `%timestamp` - of replied message, formatted with `format_timestamp`

## format_reactions
- `%timestamp` - of base message, formatted with `format_timestamp`
- `%reactions` - all reactions formatted with `format_one_reaction` then joined with `reactions_separator`

## format_one_reaction
- `%reaction` - reaction emoji or emoji name
- `%count` - count of this same reaction

## format_status
- `%global_name` - my global name
- `%username` - my username
- `%status` - Discord status if online, otherwise 'connecting' or 'offline'
- `%custom_status` - custom status string
- `%custom_status_emoji` - custom status emoji or emoji name
- `%pronouns` - my pronouns
- `%unreads` - `[New unreads]` if in this channel has unread messages
- `%typing` - typing string
- `%rich` - my rich presence, replaced with `format_rich`
- `%server` - currently viewed server
- `%channel` - currently viewed channel
- `%action` - warning for replying/editing/deleting message
- `%task` - currently running slow task (reconnecting, downloading chat...)

## format_rich
- `%name` - name of the rich presence app
- `%state` - rich presence state
- `%details` - rich presence details
- `%small_text` - rich presence small text
- `%large_text` - rich presence large text

## format_prompt
- `%global_name` - my global name
- `%username` - my username
- `%server` - currently viewed server
- `%channel` - currently viewed channel
