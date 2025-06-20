from typing import Optional
from collections import defaultdict
from dataclasses import dataclass, field

import os
import sys
from dotenv import load_dotenv

import discord
from discord import VoiceClient, Message, TextChannel, Member, Guild, VoiceChannel, VoiceState, StageChannel
from discord.abc import Messageable
from discord.ext.commands import Context, Bot
#import nacl #doesn't need to be imported but needs to be installed

from gtts import gTTS

#useful links
# https://realpython.com/how-to-make-a-discord-bot-python/
# https://murf.ai/blog/discord-voice-bot-api-guide
# https://discordpy.readthedocs.io/en/stable/api.html
# https://www.pythondiscord.com/pages/tags/on-message-event/
# https://discordpy.readthedocs.io/en/latest/ext/commands/commands.html
# https://pypi.org/project/replit-ffmpeg/

def main():

    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    FFMPEG_EXECUTABLE = os.getenv('FFMPEG_EXECUTABLE')
    LANGUAGE = "en"
    MAX_MP3_PER_SERVER = 100

    print(f"{sys.platform = }")
    if sys.platform == "linux":
        OPUS = os.getenv('OPUS')
        discord.opus.load_opus(OPUS)
    elif sys.platform != "win32":
        print("unsupported platform")
        return

    @dataclass()
    class MemberState:
        echo_member : bool = False
        mimic_member : bool = False

    @dataclass()
    class GuildState:
        member_states : defaultdict[Member, MemberState] = field(default_factory=lambda : defaultdict(MemberState))
        current_mp3 : int = 0
        last_mp3 : int = 0

    guild_states : defaultdict[Guild,GuildState] = defaultdict(GuildState)
    to_clean_up = []

    command_prefix = "!"

    intents : discord.Intents = discord.Intents.all()
    bot: Bot = Bot(command_prefix=command_prefix, intents=intents)

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

    @bot.command(name= "echo_toggle", help="The bot toggles echoing a member")
    async def echo_toggle_command(ctx: Context, member: Optional[Member]):
        print(f"echo_toggle")
        if ctx.guild is None:
            print("no guild")
            return
        else:
            guild : Guild = ctx.guild

        if member is None:
            member = ctx.author
        if not isinstance(member, Member):
            print("user not in server")
            return

        await echo_toggle(ctx, guild, member)

    @bot.command(name = "mimic_toggle", help="The bot toggles mimicking a member with text-to-speech")
    async def mimic_toggle_command(ctx: Context, member: Optional[Member]):
        print(f"register")
        if ctx.guild is None:
            print("no guild")
            return
        else:
            guild : Guild = ctx.guild

        if member is None:
            member = ctx.author
        if not isinstance(member, Member):
            print("user not in server")
            return

        await mimic_toggle(ctx, guild, member)

        await auto_join(ctx, guild, member)

    @bot.command(name = "mimic_all", help = "Set the bot to mimic all users in this server")
    async def mimic_all_command(ctx: Context):
        guild : Guild = ctx.guild
        if not guild:
            print("no guild")
            return

        for member in guild.members:
            if member != bot.user:
                guild_states[guild].member_states[member].mimic_member = True
        response = f"all members set to be mimicked"

        await ctx.send(response)

        member = ctx.author
        if not isinstance(member, Member):
            print("user not in server")
            return

        await auto_join(ctx, guild, member)

    @bot.command(name = "mimic_none", help = "Set the bot to mimic no users in this server")
    async def mimic_none_command(ctx: Context):
        guild: Guild = ctx.guild
        if not guild:
            print("no guild")
            return

        for member in guild.members:
            guild_states[guild].member_states[member].mimic_member = False
        response = f"all members set to not be mimicked"
        await ctx.send(response)

    @bot.command(name = "mimic_role", help = "Set the bot to mimic members of a given role in this server")
    async def mimic_role_command(ctx: Context, role : discord.Role):
        guild: Guild = ctx.guild
        if not guild:
            print("no guild")
            return

        for member in guild.members:
            if role in member.roles and member != bot.user:
                guild_states[guild].member_states[member].mimic_member = True
        response = f"all members of role {role} set to be mimicked"
        await ctx.send(response)

        member = ctx.author
        if not isinstance(member, Member):
            print("user not in server")
            return

        await auto_join(ctx, guild, member)

    @bot.command(name = "stop_mimic_role", help = "Set the bot to not mimic members of a given role in this server")
    async def stop_mimic_role_command(ctx: Context, role : discord.Role):
        guild: Guild = ctx.guild
        if not guild:
            print("no guild")
            return

        for member in guild.members:
            if role in member.roles:
                guild_states[guild].member_states[member].mimic_member = False
        response = f"all members of role {role} set to not be mimicked"
        await ctx.send(response)

    @bot.command(name = "echo", help="Echos the following words")
    async def echo_command(ctx: Context, *words : str):
        await echo(ctx, " ".join(words))

    @bot.command(name = "join", help="Joins current channel or a specified channel")
    async def join_command(ctx: Context, channel: Optional[VoiceChannel]):
        print("join")
        guild : Optional[Guild] = ctx.guild

        # if the user didn't give a channel, try and get the channel they're in
        if not channel:
            voice: Optional[VoiceState] = ctx.author.voice
            if not voice:
                print("no voice state")
                response = f"I failed to join the voice channel because you are not in one to join and you didn't provide one to join"
                await ctx.send(response)
                return
            channel : Optional[VoiceChannel] | StageChannel = voice.channel

        #check that the channel exists and is in the guild they put the command in
        if not isinstance(channel, VoiceChannel) or channel.guild != guild:
            print("no voice Channel")
            response = f"I failed to join the voice channel because you are not in one to join and you didn't provide one to join"
            await ctx.send(response)
            return
        channel : VoiceChannel

        #join channel
        await join(channel, ctx)

    @bot.command(name = "mimic", help="Mimics the following sentence in text-to-speech")
    async def mimic_command(ctx: Context, *words):
        print("mimic")
        # get the guild in which the command was executed in
        if ctx.guild is None:
            print("not in guild")
            return
        guild: Guild = ctx.guild

        #get the member who did the command
        if not isinstance(ctx.author, Member):
            print("not member")
            return
        member : Member = ctx.author

        await auto_join(ctx, guild, member)

        curr_vc = get_current_voice_client(guild, bot)
        if curr_vc is None:
            print("not in vc")
            return
        curr_vc : VoiceClient
        text = " ".join(words)
        await mimic(guild, ctx, curr_vc, text)

    @bot.command(name = "leave", help="Leave the channel its in")
    async def leave_command(ctx: Context):
        print("leave")

        curr_vc = get_current_voice_client(ctx.guild, bot)
        if not curr_vc:
            print("no voice connection")
            response = f"I cant leave a voice channel im not in one"
            await ctx.send(response)
            return

        await leave(curr_vc)

    @bot.listen()
    async def on_message(message: Message):
        # print(f"{message.content = }")
        if not message.guild:
            return
        guild: Guild = message.guild

        # checks that the message author is a member
        if not isinstance(message.author, Member):
            return
        member: Member = message.author

        # checks if the message was from the bot so it can be ignored
        if message.author == bot.user:
            # print("is bot message")
            return

        # check if the message is a command so it can be ignored by this function
        if (m := message.content) and m[0: len(command_prefix)] == command_prefix:
            # print("is command")
            return

        # if the channel isn't a text channel then we ignore the message
        if not isinstance((channel := message.channel), TextChannel):
            return
        channel: TextChannel

        if guild_states[guild].member_states[member].mimic_member:
            print(f"mimicking {message.content =}")
            vc = get_current_voice_client(guild, bot)
            if vc:
                await mimic(guild, channel, vc,  message.content)

        if guild_states[guild].member_states[member].echo_member:
            print(f"echoing {message =}")
            await echo(channel, message.content )

    @bot.event
    async def on_voice_state_update(member : Member, before : VoiceState, after: VoiceState):
        vc = get_current_voice_client(member.guild, bot)
        if not vc:
            return

        if len(vc.channel.members) == 1:
            await leave(vc)


    ###### put logic functions here
    def get_current_voice_client(guild : Guild, bot: Bot) -> Optional[VoiceClient]:
        return discord.utils.get(bot.voice_clients, guild=guild)

    def get_shared_voice_client(user_vs: Optional[VoiceState], bot: Bot) -> Optional[VoiceClient]:
        if user_vs is None:
            print("user not in a vc")
            return None
        return discord.utils.get(bot.voice_clients, channel=user_vs.channel)

    def cleanup(path):
        # try to delete a mp3
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"File '{path}' deleted successfully.")
            else:
                print(f"File '{path}' not found.")
        except PermissionError:
            # if you aren't allowed access to the path then note the path so it can be cleaned up later
            print(f"File '{path}' failed clean up")
            to_clean_up.append(path)

    def process_cleanup_stack():
        # attempt to delete the mp3s which have failed to be deleted in cleanup
        to_clean_up_cpy = to_clean_up.copy()
        to_clean_up.clear()
        for path in to_clean_up_cpy:
            cleanup(path)
        print(to_clean_up)

    def early_leave_cleanup(guild: Guild):
        print("early leave cleanup")
        while (current_mp3 := guild_states[guild].current_mp3) <= guild_states[guild].last_mp3:
            path = f"{guild.id}-{current_mp3}.mp3"
            guild_states[guild].current_mp3 += 1
            cleanup(path)
        guild_states[guild].current_mp3 = 0
        guild_states[guild].last_mp3 = 0
        process_cleanup_stack()


    def play_next_mp3(guild: Guild, curr_vc: VoiceClient):
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
        try:
            curr_vc.play(discord.FFmpegPCMAudio(path, executable=FFMPEG_EXECUTABLE), after=finished_playing)
        except discord.ClientException:
            print("disconnected")
            early_leave_cleanup(guild)
        print(f"currMP3 = {guild_states[guild].current_mp3}, lastMP3 = {guild_states[guild].last_mp3}")


    async def mimic(guild : Guild, messageable : Messageable, curr_vc : VoiceClient, text : str):
        if text == "":
            print("no text")
            return

        # warning this has potential race conditions, but it doesn't seem likely to occur, so I haven't added locks yet
        #####
        if guild_states[guild].last_mp3 >= MAX_MP3_PER_SERVER:
            print("too many mp3s")
            response = f"This server is only allowed to queue {MAX_MP3_PER_SERVER} sentences. Wait till I stop speaking to add more."
            await messageable.send(response)
            return

        last_mp3 = guild_states[guild].last_mp3 = guild_states[guild].last_mp3 + 1

        #get path which the new mp3 will be saved to
        path = f"{guild.id}-{last_mp3}.mp3"

        #as failed cleanups are expected to be rare, searching in the list should have minimal impact
        if path in to_clean_up:
            # if the path is marked to be deleted as we are overriding it we can unmark it
            to_clean_up.remove(path)


        #generate and save text-to-speech mp3
        tts_obj = gTTS(text=text, lang=LANGUAGE, slow=False)
        tts_obj.save(path)
        #####

        # start playing if the bot isn't already
        if not curr_vc.is_playing():
            play_next_mp3(guild, curr_vc)

    async def auto_join(messageable : Messageable, guild : Guild, member : Member):
        # auto join vc if not already in one
        await join_members_vc_if_none(guild, bot, member, messageable)
        # tell the person who activated the command to join a vc with the bot if not already
        if get_shared_voice_client(member.voice, bot) is None:
            response = f"{member} is not in a vc with me. Join a vc with me to hear the registered user"
            await messageable.send(response)

    async def echo_toggle(messageable : Messageable, guild : Guild, member : Member):
        # toggle the echo state and inform the user about it
        echo_state = guild_states[guild].member_states[member].echo_member = not guild_states[guild].member_states[
            member].echo_member
        response = f"{member} has been {'' if echo_state else 'de'}registered to echo mode"
        await messageable.send(response)

    async def mimic_toggle(messageable : Messageable, guild : Guild, member : Member):
        # invert mimic_state and inform the user about it
        mimic_state = guild_states[guild].member_states[member].mimic_member = not guild_states[guild].member_states[
            member].mimic_member
        response = f"{member} has been {'' if mimic_state else 'de'}registered to mimic mode"
        await messageable.send(response)

    async def echo(messageable: Messageable, text : str):
        response = f"echo: {text}"
        await messageable.send(response)

    async def join_members_vc_if_none(guild : Guild, bot : Bot, member : Member, messageable : Messageable):
        if get_current_voice_client(guild, bot) is None and member.voice and isinstance(member.voice.channel, VoiceChannel):
            await join(member.voice.channel, messageable)


    async def join(channel: VoiceChannel, messageable: Messageable):
        #get the channel in this guild that the bot is in if its in one
        curr_vc: Optional[VoiceClient] = get_current_voice_client(channel.guild, bot)

        #if already in a vc, but not the one the user is in then we leave it so we can join their vc
        if curr_vc is not None:
            if curr_vc.channel == channel :
                print("already in the vc")
                return
            await leave(curr_vc)

        # attempt to connect to the voice channel
        try:
            await channel.connect(timeout=5)
        except TimeoutError:
            print("timeout")
            response = f"I failed to join {channel.name}"
            await messageable.send(response)
        else:
            print("joined")


    async def leave(curr_vc: VoiceClient):
        await curr_vc.disconnect()
        print("i have left")

    bot.run(TOKEN)


if __name__ == '__main__':
    main()