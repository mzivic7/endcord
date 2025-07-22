SEARCH_HELP_TEXT = """from:user_id
mentions:user_id
has:link/embed/file/video/image/sound/sticker
before:date (format: 2015-01-01)
after:date (format: 2015-01-01)
in:channel_id
pinned:true/false"""

COMMAND_ASSISTS = (
    ("goto <#[channel_id]> - go to specified channel/server/category/DM", "goto"),
    ("view_pfp *<@[user_id]> - view specified or selected users pfp", "view_pfp"),
    ("react *[reaction] - show prompt or react to message", "react"),
    ("status *[type] - change your status 1/online, 2/idle, 3/dnd, 4/invisible", "status"),
    ("download *[num] - download one file or specify index if multiple", "download"),
    ("open_link *[num] - open one link or specify index if multiple", "open_link"),
    ("play *[num] - play one media link or specify index if multiple", "play"),
    ("search *[query] - prompt for message search or search provided string", "search"),
    ("gif *[query] - prompt for gif search or search provided string", "gif"),
    ("record / record cancel - start/stop/cancel recording voice message", "record"),
    ("upload *[path] - propmt to upload attachment or use provided path", "upload"),
    ("profile *<@[user_id]> - view profile of selected or specified user", "profile"),
    ("channel *<#[channel_id]> - view info of selected or specified channel", "channel"),
    ("summaries *<#[channel_id]> - view summaries of selected or specified channel", "summaries"),
    ("hide *<#[channel_id]> - view info of selected or specified channel", "hide"),
    ("toggle_mute *<#[channel_id]> - toggle mute state of selected or specified channel", "toggle_mute"),
    ("mark_as_read *<#[channel_id]> - mark channel/server/category/DM as read", "mark_as_read"),
    ("copy_message - copy selected message text", "copy_message"),
    ("spoil - reveal one by one spoiler in selected message", "spoil"),
    ("link_channel *<#[channel_id]> - store channel link in clipboard", "link_channel"),
    ("link_message - store selected message link in clipboard", "link_message"),
    ("goto_mention *[num] - go to channel/message that selected message is mentioning", "goto_mention"),
    ("cancel - cancel all downloads and uploads", "cancel"),
    ("member_list - toggle member list", "member_list"),
    ("toggle_thread - join/leave selected thread in tree", "toggle_thread"),
    ("bottom - go to chat bottom", "bottom"),
    ("go_reply - go to message that selected message is replying to", "go_reply"),
    ("show_reactions - show reactions details for selected message", "show_reactions"),
    ("show_pinned - show pinned messages for current channel", "show_pinned"),
    ("pin_message - pin selected message to current channel", "pin_message"),
    ("push_button [num/name] - push button on interactive app message", "push_button"),
    ("string_select [string] - select string on interactive app message", "string_select"),
    ("toggle_tab - toggle tabbed (pinned) state of current channel", "toggle_tab"),
    ("switch_tab [num] - switch to specified tab by ist number", "switch_tab"),
    ("vote [num] - vote for specified answer index on active poll message", "vote"),
    ("paste_clipboard_image - upload image from clipboard as attachment", "paste_clipboard_image"),
    ("insert_timestamp YYYY-MM-DD-HH-mm / YYYY-MM-DD / HH:mm / HH:mm:SS - insert discord timestamp", "insert_timestamp"),
    ("set_notifications *<#[channel_id]> ... - show and modify server/channel notification settings", "set_notifications"),
    ("check_standing - check account standing, anything non-100 is concerning", "check_standing"),
    ("dump_chat - dump current chat to unique json file", "dump_chat"),
    ("set [key] = [value] - change settings and save them.", "set"),
)
