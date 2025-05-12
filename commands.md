## Commands
- `react` / `react [reaction]`  
    Propt to type reaction or send provided reaction to selected message.
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
    Reveal one-by-one spoiler in selected messgae.
- `link_channel` / `link_channel <#[channel_id]>`  
    Copy link of selected channel in tree to clipboard, or from provided channel id.
- `link_message`  
    Copy link of selected message to clipboard,
- `goto_mention` / `goto_mention [num]`  
    Go to channel/message mentioned in this message.
- `cancel`  
    Prmpt to cancel all downloads and uploads.
- `member_list`  
    Toggle member list.
- `toggle_thread`  
    Join/Leave selected thread in tree.
- `bottom`  
    Go to chat bottom
- `go_reply`  
    Go to replied message from currently selected message.
- `show_reactions`  
    Show reactions details for selected message.



## Special commands (no keybinding)
- `goto <#[channel_id]>`  
    Go to specified channel from any server
- `view_pfp` / `view_pfp <@[user_id]>`  
    View prfile picure of user from currently selected message or specified user.
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
    Mute/unmute selected channel in tree or specified channel.
