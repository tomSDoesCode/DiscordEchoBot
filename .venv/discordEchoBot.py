from typing import Optional

import os

import discord
from discord import VoiceClient
from discord.ext.commands import Context
from dotenv import load_dotenv
from discord.ext import commands
from collections import defaultdict
import nacl
FFMPEG_EXECUTABLE = r"C:\Users\User\Documents\ffmpeg\ffmpeg-2025-06-11-git-f019dd69f0-full_build\ffmpeg-2025-06-11-git-f019dd69f0-full_build\bin\ffmpeg.exe"



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
    userStates = defaultdict(int)

    #load token
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')

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

    @bot.command(help = "The bot starts echoing the given user")
    async def register(ctx : Context, user : discord.Member):
        print(f"register")
        if user is None:
            return
        response = f"{user} has been registered"
        userStates[user] = 1
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

        vc : Optional[VoiceClient] = await channel.connect()
        if vc is None:
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
    async def on_message(message):
        print(f"{message.content = }")
        if message.author == bot.user:
            print("is bot message")
            return
        if (m := message.content) and m[0: len(command_prefix)] == command_prefix:
            print("is command")
            return
        elif userStates[message.author] == 1:
            print("echo")
            await message.channel.send(f"echo: {message.content}")
        else:
            print("not registered")

    bot.run(TOKEN)

if __name__ == '__main__':
    main()