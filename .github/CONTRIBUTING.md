## Before trying to contribute
Better dont contribute. You'll save your mental health, and I will save time trying to understand your code.  
But if you insist:  
First have a look at the code, if you can navigate through that mess and keep your sanity: try to maintain same writing style, and explain in detail what is done in a PR.  
If the code makes you scream, just open an issue, and I will get to it.  


## **LLM generated code is strongly prohibited**
If PR is suspected to have more than 5% of AI generated code, it will be ASAP closed, and the features will be "really" implemented by someone else, without any association with that PR. No exceptions.  
So, before even thinking about putting it through LLM, open an issue and save yourself of trouble, because others can do it for free and better.  


## Contributing rules
- Don't use inheritance. It makes code even more unreadable.
- Don't use dataclasses, they are slow and I dont like them, use nested lists and dicts.
- NO typing!
- Don't refactor, format (other than existing ruff config), clean, unnecessary optimize. I like the code the way it is.
- Don't use `requests`, it uses 3MB more RAM than `http.client`.
- Use `os.path` instead `pathlib`, its making things weird.
- NO `asyncio`, this is pure `threading` project.
- If you know how to do it and its not really hard, do it yourself, don't import large library for that.


## Running from source
1. setup uv environment if not already: `uv sync --all-groups`
2. Run main.py: `uv run main.py`


## useful debugging things

### Debug points in code
- `debug_events` - save all received events from gateway
- `debug_guilds_tree` - print all tree data in jsons
- `255_curses_bug` - this part of the code should be changed after [ncurses bug](https://github.com/python/cpython/issues/119138) is fixed. If there is no note, just remove the code

### Network tab filter
Filter for network tab in dev tools:  
`-.js -css -woff -svg -webp -png -ico -webm -science -txt -mp3`

### Monitor IPC on linux socket
```bash
sudo mv /run/user/1000/discord-ipc-0 /run/user/1000/discord-ipc-0.original
sudo socat -t100 -x -v UNIX-LISTEN:/run/user/1000/discord-ipc-0,mode=777,reuseaddr,fork UNIX-CONNECT:/run/user/1000/discord-ipc-0.original
```

### Log discord events to console
Open discord web or install discord-development  
Or regular discord:  
    in `.config/discord/config.json` put:  
    `"DANGEROUS_ENABLE_DEVTOOLS_ONLY_ENABLE_IF_YOU_KNOW_WHAT_YOURE_DOING": true`  
Open dev tools: `Ctrl+Shift+I`  
Type: `allow pasting`  
Paste code from [here](https://gist.github.com/MPThLee/3ccb554b9d882abc6313330e38e5dfaa?permalink_comment_id=5583182#gistcomment-5583182)  
Go to discord settings, in developer options, logging tab, enable "Logging Gateway Events to Console"  
In dev tools console select "Verbose" level (chrome and desktop client only)  

### Full API documentation
https://github.com/discord-userdoccers/discord-userdoccers

### App command permissions chart
https://discord.com/developers/docs/change-log#upcoming-application-command-permission-changes

### Channel types
- 0 - text
- 1 - single person DM
- 2 - voice
- 3 - group DM (name is not None)
- 4 - category
- 5 - announcements
- 11/12 - thread
- 15 - forum (contains only threads)

### Message notifications types
- 0 - all messages
- 1 - only mentions
- 2 - nothing
- 3 - category defaults

### RPC activity types
- 0 - playing
- 2 - listening

### Layout:
```
-------------------------------------------
|W TITLE W|WWWWWWWWWWWW TITLE WWWWWWWWWWWW|
|         |                        |      |
|         |                        |MEMBER|
|         |          CHAT          | LIST |
|         |                        |      |
|  TREE   |                        |      |
|         |MMMMMMMMMMMM EXTRA2 MMMMMMMMMMM|
|         |           EXTRA BODY          |
|         |UUUUUUUUUUUU EXTRA1 UUUUUUUUUUU|
|         |WWWWWWWWWWWW STATUS WWWWWWWWWWW|
|         |[PROMPT]>                      |
-------------------------------------------
```

### Tree layout and formatting:
```
> GUILD
|--> CATEGORY
|  |-- CHANNEL
|  |--> CHANNEL
|  |  |-< THREAD
|  |  \-< THREAD
|  \--> CHANNEL
\--> CATEGORY
```
```
> GUILD
|--> CATEGORY
|  |-- CHANNEL
|  |--> CHANNEL
|  |  |-< THREAD
|  |  \-< THREAD
|  |  end_channel 1300
|  \--> CHANNEL
|  end_category 1200
|--> CATEGORY
|  end_category 1200
end_guild 1100
```
