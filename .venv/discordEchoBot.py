from discord.app_commands import Command
from typing import Optional
from collections import defaultdict
from collections import deque

import os
from dotenv import load_dotenv

import discord
from discord import VoiceClient, Message
from discord.ext.commands import Context
from discord.ext import commands
import nacl

from gtts import gTTS




def getVoiceClient(ctx : Context, bot : commands.Bot) -> Optional[VoiceClient]:
    user_vc: Optional[discord.VoiceChannel] = ctx.author.voice.channel
    if user_vc is None:
        print("user not in vc")
        return None
    curr_vc: Optional[VoiceClient] = discord.utils.get(bot.voice_clients, channel=user_vc)
    return curr_vc

def main():
    #https://realpython.com/how-to-make-a-discord-bot-python/
    #https://murf.ai/blog/discord-voice-bot-api-guide
    #https://discordpy.readthedocs.io/en/stable/api.html
    #https://www.pythondiscord.com/pages/tags/on-message-event/
    #https://discordpy.readthedocs.io/en/latest/ext/commands/commands.html
    # load constants
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    FFMPEG_EXECUTABLE = os.getenv('FFMPEG_EXECUTABLE')
    LANGUAGE = "en"
    MAX_MP3_PER_SERVER = 100

    userStates = defaultdict(int)
    serverMP3s = defaultdict(lambda : list((0,0)))
    to_clean_up = []

    command_prefix = "!"
    #client = discord.Client()
    intents = discord.Intents.all()
    bot : commands.Bot = commands.Bot(command_prefix=command_prefix, intents = intents)




    #put event handlers here
    @bot.event
    async def on_ready():
        for guild in bot.guilds:
            print(f"{guild.name = } : {guild.id = }")

    @bot.event
    async def on_error(event, *args, **kwargs):
        with open('err.log', 'a') as f:
            f.write(f'Unhandled event: {event}\n')
            raise

    @bot.command(help = "The bot starts echoing the given user in chat")
    async def echo_register(ctx : Context, user : discord.Member):
        print(f"register")
        if user is None:
            return

        userStates[user] = 1
        response = f"{user} has been registered to echo"
        await ctx.send(response)

    @bot.command(help = "The bot starts echoing the given user in vc")
    async def say_register(ctx : Context, user : discord.Member):
        print(f"register")
        if user is None:
            return

        userStates[user] = 2
        response = f"{user} has been registered to say"
        await ctx.send(response)
        if getVoiceClient(ctx, bot) is None:
            response = f"{ctx.author} is not in a vc with me. Join a vc with me to hear the regisered user"
            await ctx.send(response)

    @bot.command(help = "The bot stops echoing the given user")
    #@commands.has_role('admin') #example role check
    async def deregister(ctx : Context, user : discord.Member):
        print(f"deregister")
        if user is None:
            return
        response = f"{user} has been deregistered"
        userStates[user] = 0
        await ctx.send(response)
        # discord.utils.get(guild.channels, name=channel_name)

    @bot.command(help = "echos the following word")
    async def echo(ctx : Context, word):
        print(f"echo")
        response = f"echo: {word}"
        await ctx.send(response)

    @bot.command(help = "joins channel")
    async def join(ctx : Context):
        print("join")
        channel : discord.VoiceChannel = ctx.author.voice.channel
        if not channel:
            print("no channel")
            response = f"I failed to join the voice channel"
            await ctx.send(response)
            return
        user_guild: Optional[discord.Guild] = ctx.guild
        if user_guild is None:
            print("not in guild, strange")
            return
        curr_vc: Optional[VoiceClient] = discord.utils.get(bot.voice_clients, guild=user_guild)
        if curr_vc is not None:
            print("already in vc")
            response = f"I failed to join the voice channel beacuse im in one"
            await ctx.send(response)
            return
        try:
            vc : Optional[VoiceClient] = await channel.connect(timeout = 5)
        except TimeoutError:
            print("timeout")
            response = f"I failed to join {channel.name}"
        else:
            response = f"I joined {channel.name}"
        await ctx.send(response)

    @bot.command(help="plays the expected sound")
    async def play(ctx : Context):
        print("play")
        curr_vc : VoiceClient = getVoiceClient(ctx, bot)

        if not curr_vc:
            print("no voice connection")
            response = f"I'm not in the same voice channel as you"
            await ctx.send(response)
            return


        curr_vc.play(discord.FFmpegPCMAudio('test1.mp3', executable = FFMPEG_EXECUTABLE), after=lambda e: print('done', e))
        response = f"playing sound"
        await ctx.send(response)

    #say helper functions
    def cleanup(path):
        #try to delete a mp3
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"File '{path}' deleted successfully.")
            else:
                print(f"File '{path}' not found.")
        except PermissionError:
            # if you arent allowed access to the path then note the path so it can be cleaned up later
            print("failed clean up, set to try again later")
            to_clean_up.append(path)

    def processCleanUpStack():
        #attempt to delete the mp3s which have failed to be deleted
        to_clean_up_cpy = to_clean_up.copy()
        to_clean_up.clear()
        for path in to_clean_up_cpy:
            cleanup(path)
        print(to_clean_up)

    def begin_playing(ctx: Context, curr_vc: Optional[VoiceClient]):
        currentMP3, maxMP3 = serverMP3s[ctx.guild]
        print(f"{currentMP3 = }, {maxMP3 =}")

        # if the currentMP3 equals maxMP3 then all mp3s have been played
        if currentMP3 >= maxMP3:
            print("played last mp3")
            serverMP3s[ctx.guild] = [0, 0]  # reset servers mp3 number range
            # attempt to clean up any failed cleanups then return
            processCleanUpStack()
            return

        #get the next mp3 to play
        currentMP3 = serverMP3s[ctx.guild][0] = currentMP3 + 1
        path = f"{ctx.guild.id}-{currentMP3}.mp3"

        # attempt to play the audio
        try:
            curr_vc.play(discord.FFmpegPCMAudio(path, executable=FFMPEG_EXECUTABLE),
                         after=lambda e: cleanup(path) or begin_playing(ctx, curr_vc))
        except discord.ClientException:
            print("early leave cleanup")
            # if the bot disconnects clean up all the mp3s and return
            cleanup(f"{ctx.guild.id}-{currentMP3}.mp3")
            while serverMP3s[ctx.guild][0] <= serverMP3s[ctx.guild][1]:
                path = f"{ctx.guild.id}-{serverMP3s[ctx.guild][0]}.mp3"
                serverMP3s[ctx.guild][0] += 1
                cleanup(path)
            processCleanUpStack()
            return

    @bot.command(help="says the following sentence")
    async def say(ctx : Context, *words):
        print("say")
        if ctx.guild is None:
            print("no guild")
            return
        curr_vc : VoiceClient = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        mytext = " ".join(words)

        if not curr_vc:
            print("no voice connection")
            response = f"I'm not in the same voice channel as you"
            #await ctx.send(response)
            return
        
        #warning this has potential race conditions, but as it doesnt seem to likely to occur, so i havent added locks yet
        #TODO: add locks for serverMP3s and to_clean_up
        #####
        maxMP3 = serverMP3s[ctx.guild][1] = serverMP3s[ctx.guild][1] +1
        if maxMP3 > MAX_MP3_PER_SERVER :
            serverMP3s[ctx.guild][1] -=1
            print("too many mp3s")
            response = f"This server is only allowed to queue {MAX_MP3_PER_SERVER} sentences. Wait till I stop speaking to add more."
            await ctx.send(response)
            return

        #generate tts and save it
        path = f"{ctx.guild.id}-{maxMP3}.mp3"
        #if the path is marked to be deleted as we are overiding it we can unmark it
        if path in to_clean_up:
            to_clean_up.remove(path)
        tts_obj = gTTS(text=mytext, lang=LANGUAGE, slow=False)
        tts_obj.save(path)

        #start playing if the bot isnt already
        if not curr_vc.is_playing():
            begin_playing(ctx, curr_vc)
        #####


    @bot.command(help="leave channel")
    async def leave(ctx : Context):
        print("leave")
        curr_vc : VoiceClient = getVoiceClient(ctx, bot)
        if not curr_vc:
            print("no voice connection")
            response = f"I cant leave a voice channel if we aren't both in it"
            await ctx.send(response)
            return
        await curr_vc.disconnect()
        response = f"I have left the voice channel"
        await ctx.send(response)

    @bot.listen()
    async def on_message(message : Message):
        print(f"{message.content = }")
        if message.author == bot.user:
            print("is bot message")
            return
        elif (m := message.content) and m[0: len(command_prefix)] == command_prefix:
            print("is command")
            return
        elif userStates[message.author] == 1:
            print("echo")
            await message.channel.send(f"echo: {message.content}")
        elif userStates[message.author] == 2:
            psuedo_ctx = commands.Context(message=message, bot=bot, view=commands.view.StringView(message.content))
            await say(psuedo_ctx, message.content)
        else:
            print("not registered")

    bot.run(TOKEN)

if __name__ == '__main__':
    main()