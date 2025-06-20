# DiscordEchoBot
Get the bot [here](https://discord.com/oauth2/authorize?client_id=1383542849362202746)
## Description
This is the python code for hosting the Discord bot: EchoBot.\
This bot is intented to be added to a server and have the members use the __!mimic_toggle__ command which will take a member of the server, or them by default, and set the member to be mimicked with text-to-speech when they send messages.\
Once one or more members have been registered and the bot is in a voice channel, which can be done either by using the __!join__ command or automatically when the __!mimic_toggle__ command is used while the member who used the command is in a voice channel, the bot will play text-to-speech of any message (except commands) put into and text channel the bot has access to.\
Finally when the user is done with the bot it will either leave it's voice channel automatically when its alone in a voice channel or can be made to leave using the __!leave__ command.
## TODO list
+ ~add auto disconnect when alone in a voice channel~
+ ~add auto connect when a command to play a sound is run by a user in a voice channel~
+ ~change how user state is managed so each users state is independent from their state in another server~
+ add locks to prevent race conditions
+ setup docker image
+ ~seperate the triggering of commands and the execution of commands into different functions~
+ add other voice options
+ ~add auto leave when the __!join__ command is used~
+ add better logging of events
