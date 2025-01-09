## Default config values with explanations:
Note: always put string in `""`. To use `"` inside the string escape it like this: `\"`. To use `\` escape it like this: `\\`. These are counted as single character.

- `token = None`  
    Your discord token. Provide it here or as a command argument.
- `debug = False`  
    Enable debug mode.
- `limit_chat_buffer = 100`  
    Number of messages kept in chat buffer. Initial buffer is 50 messages and is expanded in scroll direction. Limit: 50-1000.
- `limit_username = 10`  
    Limit to the username string length.
- `limit_global_name = 15`  
    Limit to the global name string length.
- `convert_timezone = True`  
    If set to False, will show UTC time.
- `format_message = "[%timestamp] <%username> | %content %edited"`  
    Formatting for message base string. See [format_message](##format_message) for more info.
- `format_newline = "                       %content"`  
    Formatting for each newline string after message base. See [format_newline](##format_newline) for more info.
- `format_reply = "[REPLY] <%username> | /--> [%timestamp] %content"`  
    Formatting for replied message string. It is above message base. See [format_reply](##format_reply) for more info.
- `fformat_reactions = "[REACT]                \\--< %reactions"`  
    Formatting for message reactions string. It is bellow last newline string. See [format_reactions](##format_reactions) for more info.
- `format_one_reaction = "%count:%reaction"`  
    Formatting for single reaction string. Reactions string is assembled by joining these strings with `reactions_separator` in between. See [format_one_reaction](##format_one_reaction) for more info.
- `format_timestamp = "%H:%M"`  
    Same as [datetime format codes](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes)
- `edited_string = "(edited)"`  
    A string added to the end of the message when it is edsited.
- `reactions_separator = "; "`  
    A string placed between two reactions.
- `format_status_line_l = " %global_name (%username) - %status  %unreads %action %typing"`  
    Formatting for left side of status line. See [format_status](##format_status) for more info. Set to None to disable.
- `format_status_line_r = None`  
    Formatting for right side of status line. See [format_status](##format_status) for more info.
- `format_title_line_l = " %server: %channel"`  
    Formatting for left side of title line. See [format_status](##format_status) for more info. Set to None to disable.
- `format_title_line_r = "%rich"`  
    Formatting for right side of title line. See [format_status](##format_status) for more info.
- `limit_typing_string = 30`  
    Limit to the typing string length. Also limits `%details` and `%state` in `format_rich`
- `format_rich = "playing: %name - %state - %details "`  
    Formatting for rich presence string used in `format_status`. See [format_rich](##format_rich) for more info.
- `format_prompt = "[%channel] > "`  
    Formatting for prompt line. See [format_prompt](##format_prompt) for more info.
- `send_typing = True`  
    Allow `[your_username] is typing...` to be sent.
- `desktop_notifications = True`  
    Allow sending desktop notifications when user is pinged/mentioned.
- `linux_notification_sound = "message"`  
    Sound played when notification is displayed. Linux only. Set to None to disable. Sound names can be found in `/usr/share/sounds/freedesktop/stereo`, without extension.
- `ack_throttling = 5`  
    Delay in seconds between each ack send. Minimum is 3s. The larger it is, the longer will `[New unreads]` stay in status line.
- `use_nick_when_avail = True`  
    Replace global_name with nick when it is available.
- `tree_width = 30`  
    Width of channel tree in characters.
- `tree_vert_line = "|"`  
    A single character used to draw vertical line separating channel tree and the chat.
- `format_title_tree = " endcord"`  
    Formatting for channel tree title line. See [format_status](##format_status) for more info. Set to None to disable.
- `tree_drop_down_vline = "|"`  
    A single character used to draw vertical line in tree drop down menus.
- `tree_drop_down_hline = "-"`  
    A single character used to draw horizontal line in tree drop down menus.
- `tree_drop_down_line = "\\"`  
    A single character used to draw corners in tree drop down menus.
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
    What to do with blocked messages:
    0 - no blocking  
    1 - mask blocked messages  
    2 - hide blocked messages
- `hide_spam = True`  
    Wether to hide or show spam DM request channels in DM list.

## Colors
Colors use 8bit ANSI [codes](https://gist.github.com/ConnerWill/d4b6c776b509add763e17f9f113fd25b#256-colors). Eg. `[255, 232]`, where 255 is foreground and 232 is background. -1 is terminal default color.
- `color_format_default = [-1, -1]`  
    Base color formatting for text.
- `color_format_mention = [209, 234]`  
    Color for highlighted messages containing mentions (reply with ping included) and mention roles.
- `color_format_blocked = [242, -1]`  
    Color for blocked messages if `block_mode = 1`.
- `color_tree_default = [255, -1]`  
    Colors for tree components.
- `color_tree_selected = [233, 255]`  
- `color_tree_muted = [242, -1]`  
- `color_tree_active = [255, 234]`  
- `color_tree_unseen = [-1, -1]`  
- `color_tree_mentioned = [197, -1]`  
- `color_tree_active_mentioned = [197, 234]`  

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
