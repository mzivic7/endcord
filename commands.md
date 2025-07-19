## Commands
- `react` / `react [reaction]`  
    Prompt to type reaction or send provided reaction to selected message.
- `status` / `status [type]`, types: 1 - "online", 2 - "idle", 3 - "dnd", 4 - "invisible"  
    Cycle statuses, or set it by specifying its type name or index.  
- `download` / `download [num]`  
    Prompt for index of url to download, or provide it in the command.
- `open_link` / `open_link [num]`  
    Prompt for index of url to open in browser, or provide it in the command.
- `play` / `play [num]`  
    Prompt for index of media attachment to play, or provide it in the command.
- `search` / `search [search_string]`  
    Show message search prompt or perform search with provided string.
- `record` / `record cancel`  
    Toggle recording, will send when stopped.
- `upload` / `upload [path]`  
    Prompot for upload path, or provide it in command and start uploading.
- `profile` / `profile <@[user_id]>`  
    View prfile info of user from currently selected message or specified user.
- `channel` / `channel <#[channel_id]>`  
    View info of currently selected channel in tree or specified channel.
- `summaries` / `summaries <#[channel_id]>`  
    View summaries of currently active channel or specified channel.
- `copy_message`  
    Copy selected message contents to clipboard.
- `spoil`  
    Reveal one-by-one spoiler in selected message.
- `link_channel` / `link_channel <#[channel_id]>`  
    Copy link of selected channel in tree to clipboard, or from provided channel id.
- `link_message`  
    Copy link of selected message to clipboard,
- `goto_mention` / `goto_mention [num]`  
    Go to channel/message mentioned in this message.
- `cancel`  
    Prompt to cancel all downloads and uploads.
- `member_list`  
    Toggle member list.
- `toggle_thread`  
    Join/Leave selected thread in tree.
- `bottom`  
    Go to chat bottom.
- `go_reply`  
    Go to message that selected message is replying to.
- `show_reactions`  
    Show reactions details for selected message.
- `toggle_tab`  
    Toggle tabbed (pinned) state of currently active channel.
- `switch_tab [num]`  
    Switch to specified tab by ist number.
- `show_pinned`  
    Show pinned messages for current channel.

## Special commands (no keybinding)
- `goto <#[channel_id]>`  
    Go to specified channel/category/server from anywhere. If server or category is specified, they will be selected in tree.  
- `view_pfp` / `view_pfp <@[user_id]>`  
    View profile picture of user from currently selected message or specified user.
- `paste_clipboard_image`  
    Paste image from clipboard as attachment.
- `check_standing`  
    Check account standing. 0-100 value, anything non-100 is concerning.  
- `set [key] = [value]` / `set [key]=[value]`  
    Change settings and save them. Usually restart is required.  
    External theme wont be changed and it can override changed settings.  
- `hide` / `hide <#[channel_id]>`  
    Prompt to hide selected channel in tree or specified channel.
- `toggle_mute` / `toggle_mute <#[channel_id]>`  
    Mute/unmute selected item in tree or specified channel channel/category/guild.
- `mark_as_read` / `mark_as_read <#[channel_id]>`  
    Mark as read selected item in tree or specified channel/category/guild.
- `insert_timestamp [time]`  
    Insert timestamp in input line, `[time]` can be of formats: `YYYY-MM-DD-HH-mm`, `YYYY-MM-DD`, `HH:mm`, `HH:mm:SS`.
- `vote [num]`  
    If selected message is ongoing poll, vote for specified answer index.
- `pin_message`  
    Pin selected message to current channel.
- `push_button [num/name]`  
    Push button on interactive app message. Specify either button number or button name (case-insensitive).
- `dump_chat`  
    Dump current chat to unique json, saved in Debug folder found inside config location.
- `string_select [string]` / `string_select [num] [string]`  
    Select a string on interactive app message. Strings are provided in assist window. Specify `[num]` if have multiple string selects.
- `set_notifications ...` / `set_notifications <#[channel_id]> ...`  
    Show and modify server/channel notification settings.
