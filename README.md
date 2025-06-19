# DiscordEchoBot
Get the bot [here](https://discord.com/oauth2/authorize?client_id=1383542849362202746)
## Description
This is the python code for hosting the Discord EchoBot. This bot is intented to be added to a server and have the server's members use the __!join__ command to make it join either their currently occupied voice channel or a specified channel. Then they can use the __!mimic_toggle__ command which will take a member of the server or them by default. Once one or more members have been registered and the bot is in a voice channel it will play text-to-speech whenever the registered users sends a message in any text channel the bot has access to.
## TODO list
+ ~add auto disconnect when alone in a voice channel~
+ ~add auto connect when a command to play a sound is run by a user in a voice channel~
+ ~change how user state is managed so each users state is independent from their state in another server~
+ add locks to prevent race conditions
+ setup docker image
+ ~refactor the say function so the psuedo Context class hack can be removed~
+ ~remove the psuedo Context class hack~
+ add other voice options
+ ~add auto leave when the __!join__ command is used~
+ add better logging of events
