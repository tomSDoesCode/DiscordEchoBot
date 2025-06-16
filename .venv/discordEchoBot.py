from typing import Optional
from collections import defaultdict
from dataclasses import dataclass, field

import os
import sys
from dotenv import load_dotenv

import discord
from discord import VoiceClient, Message, TextChannel
from discord.app_commands import Command
from discord.ext import commands
from discord.ext.commands import Context
import nacl

from gtts import gTTS

#useful links

# https://realpython.com/how-to-make-a-discord-bot-python/
# https://murf.ai/blog/discord-voice-bot-api-guide
# https://discordpy.readthedocs.io/en/stable/api.html
# https://www.pythondiscord.com/pages/tags/on-message-event/
# https://discordpy.readthedocs.io/en/latest/ext/commands/commands.html
# https://pypi.org/project/replit-ffmpeg/



def main():
    print(f"{sys.platform = }")
    if sys.platform == "linux":
        discord.opus.load_opus("opus/libopus.so")

    elif sys.platform != "win32":
        print("unsupported platform")
        return

    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    FFMPEG_EXECUTABLE = os.getenv('FFMPEG_EXECUTABLE')
    LANGUAGE = "en"
    MAX_MP3_PER_SERVER = 100

    @dataclass()
    class MemberState:
        echo_member : bool = False
        mimic_member : bool = False

    @dataclass()
    class GuildState:
        member_states : defaultdict[discord.Member, MemberState] = field(default_factory=lambda : defaultdict(MemberState))
        current_mp3 : int = 0
        last_mp3 : int = 0

    guild_states : defaultdict[discord.Guild,GuildState] = defaultdict(GuildState)
    to_clean_up = []

    command_prefix = "!"

    intents : discord.Intents = discord.Intents.all()
    bot: commands.Bot = commands.Bot(command_prefix=command_prefix, intents=intents)

    # put event handlers here
    @bot.event
    async def on_ready():
        for guild in bot.guilds:
            print(f"{guild.name = } : {guild.id = }")

    @bot.event
    async def on_error(event, *args, **kwargs):
        with open('err.log', 'a') as f:
            f.write(f'Unhandled event: {event}\n')
            raise

    @bot.command(help="The bot toggles echoing a member")
    async def echo_toggle(ctx: Context, member: Optional[discord.Member]):
        print(f"echo_toggle")
        if ctx.guild is None:
            print("no guild")
            return
        else:
            guild : discord.Guild = ctx.guild

        if member is None:
            member = ctx.author
        if not isinstance(member, discord.Member):
            print("user not in server")
            return
        member : discord.Member

        #toggle the echo state and inform the user about it
        echo_state = guild_states[guild].member_states[member].echo_member = not guild_states[guild].member_states[member].echo_member
        response = f"{member} has been {"" if echo_state else "de"}registered to echo mode"
        await ctx.send(response)

    @bot.command(help="The bot toggles mimicing a member with text-to-speech")
    async def mimic_toggle(ctx: Context, member: Optional[discord.Member]):
        print(f"register")
        if ctx.guild is None:
            print("no guild")
            return
        else:
            guild : discord.Guild = ctx.guild

        if member is None:
            member = ctx.author
        if not isinstance(member, discord.Member):
            print("user not in server")
            return
        member : discord.Member

        #invet mimic_state and inform the user about it
        mimic_state = guild_states[guild].member_states[member].mimic_member = not guild_states[guild].member_states[member].mimic_member
        response = f"{member} has been {"" if mimic_state else "de"}registered to mimic mode"
        await ctx.send(response)

        #auto join vc if not alreadly in one
        await join_members_vc_if_None(guild, bot, member, ctx )

        # tell the person who activated the command to join a vc with the bot if not alreadly
        if get_shared_voice_client(ctx.author.voice, bot) is None:
            response = f"{ctx.author} is not in a vc with me. Join a vc with me to hear the regisered user"
            await ctx.send(response)

    @bot.command(help="echos the following words")
    async def echo(ctx: Context, *words : str):
        await echo_helper(ctx, " ".join(words))


    @bot.command(help="joins curent channel or a given channel")
    async def join(ctx: Context, channel: Optional[discord.VoiceChannel]):
        print("join")
        guild : Optional[discord.Guild] = ctx.guild

        # if the user didnt give a channel, try and get the channel theyr'e in
        if not channel:
            voice: Optional[discord.VoiceState] = ctx.author.voice
            if not voice:
                print("no voice state")
                response = f"I failed to join the voice channel because you are not in one to join and you didnt provide one to join"
                await ctx.send(response)
                return
            channel : Optional[discord.VoiceChannel] | StageChannel = voice.channel

        #check that the channel exists and is in the guild they put the command in
        if not isinstance(channel, discord.VoiceChannel) or channel.guild != guild:
            print("no voice Channel")
            response = f"I failed to join the voice channel because you are not in one to join and you didnt provide one to join"
            await ctx.send(response)
            return
        channel : discord.VoiceChannel

        #join channel
        await join_helper(channel, ctx)

    @bot.command(help="mimics the following sentence in text-to-speech")
    async def mimic(ctx: Context, *words):
        print("mimic")
        # get the guild in which the command was executed in
        if ctx.guild is None:
            print("not in guild")
            return
        guild: discord.Guild = ctx.guild

        #get the member who did the command
        if not isinstance(ctx.author, discord.Member):
            print("not member")
            return
        member : discord.Member = ctx.author

        #if the bot isnt in a vc on this server join th
        await join_members_vc_if_None(guild, bot, member, ctx)

        curr_vc = get_current_voice_client(guild, bot)
        if curr_vc is None:
            print("not in vc")
            return
        curr_vc : VoiceClient
        text = " ".join(words)
        await mimic_helper(guild, ctx, curr_vc, text)

    @bot.command(help="leave channel")
    async def leave(ctx: Context):
        print("leave")

        curr_vc = get_current_voice_client(ctx.guild, bot)
        if not curr_vc:
            print("no voice connection")
            response = f"I cant leave a voice channel im not in one"
            await ctx.send(response)
            return

        await leave_helper(curr_vc, ctx)

    @bot.listen()
    async def on_message(message: Message):
        # print(f"{message.content = }")
        if not message.guild:
            return
        guild: discord.Guild = message.guild

        # checks that the message author is a member
        if not isinstance(message.author, discord.Member):
            return
        member: discord.Member = message.author

        # checks if the message was from the bot so it can be ignored
        if message.author == bot.user:
            # print("is bot message")
            return

        # check if the message a command so it can be ignored by this function
        if (m := message.content) and m[0: len(command_prefix)] == command_prefix:
            # print("is command")
            return

        # if the channel isnt a text channel then we ignore the message
        if not isinstance((channel := message.channel), discord.TextChannel):
            return
        channel: TextChannel

        if guild_states[guild].member_states[member].echo_member:
            print(f"echoing {message =}")
            await echo_helper(message.channel, message.content )

        if guild_states[guild].member_states[member].mimic_member:
            print(f"mimicing {message =}")
            vc = get_current_voice_client()
            if vc:
                await mimic_helper(guild, message.channel, vc,  message.content)


    ###### put logic functions here
    def get_current_voice_client(guild : discord.Guild, bot: commands.Bot) -> Optional[VoiceClient]:
        return discord.utils.get(bot.voice_clients, guild=guild)

    def get_shared_voice_client(user_vs: Optional[discord.VoiceState], bot: commands.Bot) -> Optional[VoiceClient]:
        if user_vc is None:
            print("user not in a vc")
            return None
        return discord.utils.get(bot.voice_clients, channel=user_vc.channel)

    def cleanup(path):
        # try to delete a mp3
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

    def process_cleanup_stack():
        # attempt to delete the mp3s which have failed to be deleted in cleanup
        to_clean_up_cpy = to_clean_up.copy()
        to_clean_up.clear()
        for path in to_clean_up_cpy:
            cleanup(path)
        print(to_clean_up)

    def early_leave_cleanup(guild: discord.Guild):
        print("early leave cleanup")
        while (current_mp3 := guild_states[guild].current_mp3) <= guild_states[guild].last_mp3:
            path = f"{guild.id}-{current_mp3}.mp3"
            guild_states[guild].current_mp3 += 1
            cleanup(path)
        process_cleanup_stack()

    def play_next_mp3(guild: discord.Guild, curr_vc: VoiceClient):
        prev_mp3 = guild_states[guild].current_mp3
        last_mp3 = guild_states[guild].last_mp3

        # if the prev_mp3 equals last_mp3 then all mp3s have been played
        if prev_mp3 >= last_mp3:
            print("played last mp3")
            guild_states[guild].current_mp3 = 0
            guild_states[guild].last_mp3 = 0

            # attempt to clean up any failed cleanups then return
            process_cleanup_stack()
            return

        # get the next mp3 to play
        current_mp3 = guild_states[guild].current_mp3 = prev_mp3 + 1
        path = f"{guild.id}-{current_mp3}.mp3"

        def finished_playing(e : Optional[Exception]):
            cleanup(path)
            if e:
                print(f"Error when playing audio: {e}")
                early_leave_cleanup(guild)
            else:
                play_next_mp3(guild, curr_vc)

        # attempt to play the audio
        curr_vc.play(discord.FFmpegPCMAudio(path, executable=FFMPEG_EXECUTABLE), after=finished_playing)


    async def mimic_helper(guild : discord.Guild, messagble : discord.abc.Messageable, curr_vc : VoiceClient, text : str):
        # warning this has potential race conditions, but as it doesnt seem to likely to occur, so i havent added locks yet
        #####
        if guild_states[guild].last_mp3 >= MAX_MP3_PER_SERVER:
            print("too many mp3s")
            response = f"This server is only allowed to queue {MAX_MP3_PER_SERVER} sentences. Wait till I stop speaking to add more."
            await messagble.send(response)
            return

        last_mp3 = guild_states[guild].last_mp3 = guild_states[guild].last_mp3 + 1

        #get path which the new mp3 will be saved to
        path = f"{guild.id}-{last_mp3}.mp3"
        # if the path is marked to be deleted as we are overiding it we can unmark it
        if path in to_clean_up:
            to_clean_up.remove(path)

        #generate and save text-to-speech mp3
        tts_obj = gTTS(text=text, lang=LANGUAGE, slow=False)
        tts_obj.save(path)
        #####

        # start playing if the bot isnt already
        if not curr_vc.is_playing():
            play_next_mp3(guild, curr_vc)

    async def echo_helper(messagable: discord.abc.Messageable, text : str):
        response = f"echo: {text}"
        await messagable.send(response)

    async def join_members_vc_if_None(guild : discord.Guild, bot : commands.Bot, member : discord.Member, messagable : discord.abc.Messageable):
        if get_current_voice_client(guild, bot) is None and member.voice and isinstance(member.voice.channel, discord.VoiceChannel):
            await join_helper(member.voice.channel, messagable)


    async def join_helper(channel: discord.VoiceChannel, messagable: discord.abc.Messageable):
        #get the channel in this guild that the bot is in if its in one
        curr_vc: Optional[VoiceClient] = get_current_voice_client(channel.guild, bot)

        #if already in a vc, but not the one the user is in then we leave it so we can join their vc
        if curr_vc is not None:
            if curr_vc.channel == channel :
                print("alreadly in the vc")
                return
            await leave_helper(curr_vc, messagable)

        # attempt to connect to the voice channel
        try:
            vc: Optional[VoiceClient] = await channel.connect(timeout=5)
        except TimeoutError:
            print("timeout")
            response = f"I failed to join {channel.name}"
            await messagable.send(response)
        else:
            print("joined")
            response = f"I joined {channel.name}"
            #await messagable.send(response)

    async def leave_helper(curr_vc: VoiceClient, messagable: discord.abc.Messageable):
        await curr_vc.disconnect()
        print("i have left")
        response = f"I have left {curr_vc.channel}"
        #await messagable.send(response)

    bot.run(TOKEN)


if __name__ == '__main__':
    main()