#!/usr/bin/env python3

from typing import Optional
from collections import defaultdict, deque
from dataclasses import dataclass, field

import os
import sys
from dotenv import load_dotenv

import discord
from discord import VoiceClient, Message, TextChannel, Member, Guild, VoiceChannel, VoiceState, StageChannel
from discord.abc import Messageable
from discord.ext.commands import Context, Bot

from gtts import gTTS

import logging
import traceback

import threading

import time

#useful links
# https://realpython.com/how-to-make-a-discord-bot-python/
# https://murf.ai/blog/discord-voice-bot-api-guide
# https://discordpy.readthedocs.io/en/stable/api.html
# https://www.pythondiscord.com/pages/tags/on-message-event/
# https://discordpy.readthedocs.io/en/latest/ext/commands/commands.html
# https://pypi.org/project/replit-ffmpeg/



@dataclass()
class MemberState:
    # represents whether a member's messages should be echoed in text channel
    echo_member : bool = False
    # represents whether a member's messages should be echoed in voice channel via text-to-speech
    mimic_member : bool = False

@dataclass()
class GuildState:
    # dictionary of members states
    member_states : defaultdict[Member, MemberState] = field(default_factory=lambda : defaultdict(MemberState))
    #queue of the mp3s to be played in the guilds voice channel
    mp3_queue : deque = field(default_factory=deque)
    #lock to access mp3 queue
    mp3_lock : threading.Lock = field(default_factory= threading.Lock)
    #list of a mp3 file names of file which failed to be deleted,
    # hence need to be deleted at a later point
    cleanup_stack : list[str] = field(default_factory= list)
    #lock to use the cleanup list
    cleanup_lock : threading.Lock = field(default_factory= threading.Lock)

#get the current voice client of the bot
def get_current_voice_client(guild : Guild, bot: Bot) -> Optional[VoiceClient]:
    return discord.utils.get(bot.voice_clients, guild=guild)

#get the voice client of the bot if it's in the passed in voice states channel
def get_shared_voice_client(user_vs: Optional[VoiceState], bot: Bot) -> Optional[VoiceClient]:
    if user_vs is None:
        return None
    return discord.utils.get(bot.voice_clients, channel=user_vs.channel)

def cleanup(file_name, guild_state : GuildState):
    # try to delete a mp3
    path = f"{MP3DIR}{file_name}"
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"File '{file_name}' deleted successfully.")
        else:
            logger.info(f"File '{file_name}' not found.")
    except PermissionError:
        # if you aren't allowed access to the file then note the file so it can be cleaned up later
        logger.info(f"File '{file_name}' failed clean up")
        with guild_state.cleanup_lock:
            guild_state.cleanup_stack.append(file_name)

def process_cleanup_stack(guild_state : GuildState):
    # attempt to delete the mp3s which have failed to be deleted in cleanup
    with guild_state.cleanup_lock:
        to_clean_up_cpy = guild_state.cleanup_stack.copy()
        guild_state.cleanup_stack.clear()
    for file_name in to_clean_up_cpy:
        cleanup(file_name, guild_state)

def end_of_playing_cleanup(guild_state : GuildState):
    #make sure you have guild_state.mp3_lock acquired when this function is ran
    #this function marks all unused mp3s for deletion
    while guild_state.mp3_queue:
        file_name = guild_state.mp3_queue.popleft()
        cleanup(file_name, guild_state)
    process_cleanup_stack(guild_state)

def play_next_mp3(curr_vc: VoiceClient, guild_state : GuildState):
    with guild_state.mp3_lock:
        # if the queue is empty then all mp3s have been played
        if not guild_state.mp3_queue:
            logger.info("played last mp3")
            end_of_playing_cleanup(guild_state)
        else:
            # get the file name of the next mp3 to play
            file_name = guild_state.mp3_queue.popleft()

    def finished_playing(e : Optional[Exception]):
        cleanup(file_name, guild_state)
        if e:
            logger.error(f"Error when playing audio: {e}")
            with guild_state.mp3_lock:
                end_of_playing_cleanup(guild_state)
        else:
            play_next_mp3(curr_vc, guild_state)

    # attempt to play the audio
    path = f"{MP3DIR}{file_name}"
    try:
        curr_vc.play(discord.FFmpegPCMAudio(path, executable=FFMPEG_EXECUTABLE), after=finished_playing)
    except discord.ClientException:
        logger.error("Error when playing audio: bot disconnected from the voice channel")
        cleanup(file_name, guild_state)
        with guild_state.mp3_lock:
            end_of_playing_cleanup(guild_state)

async def mimic(guild_state : GuildState, messageable : Messageable, curr_vc : VoiceClient, text : str):
    if text == "":
        logger.debug("mimic: no text to mimic")
        return

    guild_state.mp3_lock.acquire()
    if len(guild_state.mp3_queue) >= MAX_MP3_PER_SERVER:
        logger.info("mimic: reached maximum allowed amount of mp3s")
        response = f"This server is only allowed to queue {MAX_MP3_PER_SERVER} sentences."
        guild_state.mp3_lock.release()
        await messageable.send(response)
        return

    #makes the file name of the new mp3
    file_name = f"{time.time()}-{len(guild_state.mp3_queue)}.mp3"
    guild_state.mp3_lock.release()

    path = f"{MP3DIR}{file_name}"
    #generate and save text-to-speech mp3
    tts_obj = gTTS(text=text, lang=LANGUAGE, slow=False)
    tts_obj.save(path)
    #add the mp3 to the play queue
    with guild_state.mp3_lock:
        guild_state.mp3_queue.append(file_name)


    # start playing if the bot isn't already
    if not curr_vc.is_playing():
        play_next_mp3(curr_vc, guild_state)

async def auto_join(messageable : Messageable, guild : Guild, member : Member, bot : Bot):
    # auto join vc if not already in one
    await join_members_vc_if_none(guild, bot, member, messageable)
    # tell the person who activated the command to join a vc with the bot if not already
    if get_shared_voice_client(member.voice, bot) is None:
        response = f"{member} is not in a vc with me. Join a vc with me to hear the registered user"
        await messageable.send(response)

async def echo_toggle(messageable : Messageable, guild_state : GuildState, member : Member):
    # toggle the echo state and inform the user about it
    echo_state = guild_state.member_states[member].echo_member = not guild_state.member_states[
        member].echo_member
    response = f"{member} has been {'' if echo_state else 'de'}registered to echo mode"
    await messageable.send(response)

async def mimic_toggle(messageable : Messageable, guild_state : GuildState, member : Member):
    # invert mimic_state and inform the user about it
    mimic_state = guild_state.member_states[member].mimic_member = not guild_state.member_states[
        member].mimic_member
    response = f"{member} has been {'' if mimic_state else 'de'}registered to mimic mode"
    await messageable.send(response)

async def echo(messageable: Messageable, text : str):
    response = f"echo: {text}"
    await messageable.send(response)

async def join_members_vc_if_none(guild : Guild, bot : Bot, member : Member, messageable : Messageable):
    if get_current_voice_client(guild, bot) is None and member.voice and isinstance(member.voice.channel, VoiceChannel):
        await join(member.voice.channel, messageable, bot)

async def join(channel: VoiceChannel, messageable: Messageable, bot : Bot):
    #get the channel in this guild that the bot is in if its in one
    curr_vc: Optional[VoiceClient] = get_current_voice_client(channel.guild, bot)

    #if already in a vc, but not the one the user is in then we leave it so we can join their vc
    if curr_vc is not None:
        if curr_vc.channel == channel :
            logger.info("already in the vc")
            return
        await leave(curr_vc)

    # attempt to connect to the voice channel
    try:
        await channel.connect(timeout=5)
    except TimeoutError:
        logger.error("timeout on the attempt to join voice channel")
        response = f"I failed to join {channel.name}"
        await messageable.send(response)
    else:
        logger.info(f"joined {channel.name}")

async def leave(curr_vc: VoiceClient):
    await curr_vc.disconnect()
    logger.info("leave: successfully left voice channel")

if __name__ == "__main__":
    #Set up a basic logger
    logger = logging.getLogger(__name__)
    logging.basicConfig(
        format='[%(asctime)s] [%(levelname)-8s] %(message)s',
        level=logging.DEBUG,
        datefmt='%Y-%m-%d %H:%M:%S')

    #load constants
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')

    LANGUAGE = "en"
    MAX_MP3_PER_SERVER = 100
    MP3DIR = r"mp3s/"

    logger.debug(f"{sys.platform = }")
    if sys.platform == "linux":
        FFMPEG_EXECUTABLE = r"/bin/ffmpeg"
        OPUS = r"/usr/lib/x86_64-linux-gnu/libopus.so.0"
        discord.opus.load_opus(OPUS)
    elif sys.platform == "win32":
        FFMPEG_EXECUTABLE = os.getenv('FFMPEG_EXECUTABLE')
    else:
        logger.error("unsupported platform")
        exit()

def main():
    # setup state dictionary
    guild_states : defaultdict[Guild,GuildState] = defaultdict(GuildState)

    command_prefix = "!"

    intents : discord.Intents = discord.Intents.all()
    bot: Bot = Bot(command_prefix=command_prefix, intents=intents)

    @bot.event
    async def on_ready():
        for guild in bot.guilds:
            logger.debug(f"{guild.name = } : {guild.id = }")

    @bot.event
    async def on_error(event, *args, **kwargs):
        logger.error(traceback.format_exc())

    @bot.event
    async def on_voice_state_update(member : Member, before : VoiceState, after: VoiceState):
        vc = get_current_voice_client(member.guild, bot)
        if not vc:
            return
        logger.debug(f"{len(vc.channel.members) = }")
        if len(vc.channel.members) == 1:
            logger.debug(f"on_voice_state_update: leaving channel because it's alone")
            await leave(vc)

    @bot.command(name= "echo_toggle", help="The bot toggles echoing a member")
    async def echo_toggle_command(ctx: Context, member: Optional[Member]):
        logger.info(f"echo_toggle command ran")

        guild : Guild = ctx.guild

        if member is None:
            member = ctx.author

        await echo_toggle(ctx, guild_states[guild], member)

    @bot.command(name = "mimic_toggle", help="The bot toggles mimicking a member with text-to-speech")
    async def mimic_toggle_command(ctx: Context, member: Optional[Member]):
        logger.info(f"register command ran")
        guild : Guild = ctx.guild

        if member is None:
            member = ctx.author

        await mimic_toggle(ctx, guild_states[guild], member)
        await auto_join(ctx, guild, member, bot)

    @bot.command(name = "mimic_all", help = "Set the bot to mimic all users in this server")
    async def mimic_all_command(ctx: Context):
        logger.info(f"mimic_all command ran")
        guild : Guild = ctx.guild

        for member in guild.members:
            if member != bot.user:
                guild_states[guild].member_states[member].mimic_member = True
        response = f"all members set to be mimicked"

        await ctx.send(response)

        member = ctx.author
        await auto_join(ctx, guild, member, bot)

    @bot.command(name = "mimic_none", help = "Set the bot to mimic no users in this server")
    async def mimic_none_command(ctx: Context):
        logger.info(f"mimic_none command ran")
        guild: Guild = ctx.guild

        for member in guild.members:
            guild_states[guild].member_states[member].mimic_member = False

        response = f"all members set to not be mimicked"
        await ctx.send(response)

    @bot.command(name = "mimic_role", help = "Set the bot to mimic members of a given role in this server")
    async def mimic_role_command(ctx: Context, role : discord.Role):
        logger.info(f"mimic_role command ran")
        guild: Guild = ctx.guild

        for member in guild.members:
            if role in member.roles and member != bot.user:
                guild_states[guild].member_states[member].mimic_member = True

        response = f"all members of role {role} set to be mimicked"
        await ctx.send(response)

        member = ctx.author
        await auto_join(ctx, guild, member, bot)

    @bot.command(name = "stop_mimic_role", help = "Set the bot to not mimic members of a given role in this server")
    async def stop_mimic_role_command(ctx: Context, role : discord.Role):
        logger.info(f"stop_mimic_role command ran")
        guild: Guild = ctx.guild

        for member in guild.members:
            if role in member.roles:
                guild_states[guild].member_states[member].mimic_member = False

        response = f"all members of role {role} set to not be mimicked"
        await ctx.send(response)

    @bot.command(name = "echo", help="Echos the following words")
    async def echo_command(ctx: Context, *words : str):
        logger.info(f"echo command ran")
        await echo(ctx, " ".join(words))

    def verify_voice_channel(channel : Optional[VoiceChannel | StageChannel], guild : Guild ):
        #checks that a voice channel is in a guild and is not a stage channel
        return isinstance(channel, VoiceChannel) and channel.guild == guild

    @bot.command(name = "join", help="Joins current channel or a specified channel")
    async def join_command(ctx: Context, channel: Optional[VoiceChannel]):
        logger.info(f"join command ran")
        guild : Optional[Guild] = ctx.guild

        # if the user didn't give a channel, try and get the channel they're in
        if not channel:
            voice: Optional[VoiceState] = ctx.author.voice
            # check that the channel exists and is in the guild the user put the command in
            if not voice or not (channel := voice.channel) or not verify_voice_channel(channel, guild):
                logger.warning("join: There was no voice channel to join")
                response = f"I failed to join the voice channel because you are not in one to join and you didn't provide one to join"
                await ctx.send(response)
                return

        await join(channel, ctx, bot)

    @bot.command(name = "mimic", help="Mimics the following sentence in text-to-speech")
    async def mimic_command(ctx: Context, *words):
        logger.info(f"mimic command ran")

        guild: Guild = ctx.guild
        member : Member = ctx.author

        await auto_join(ctx, guild, member, bot)

        #get voice client of the bot
        curr_vc = get_current_voice_client(guild, bot)
        if curr_vc is None:
            logger.warning(f"mimic: bot not in a voice channel")
            return
        curr_vc : VoiceClient

        text = " ".join(words)
        await mimic(guild_states[guild], ctx, curr_vc, text)

    @bot.command(name = "leave", help="Leave the channel its in")
    async def leave_command(ctx: Context):
        logger.info("leave command ran")

        # get voice client of the bot
        curr_vc = get_current_voice_client(ctx.guild, bot)
        if not curr_vc:
            logger.warning("leave: no voice connection")
            response = f"I cant leave a voice channel im not in one"
            await ctx.send(response)
            return

        await leave(curr_vc)

    @bot.listen()
    async def on_message(message: Message):
        if not message.guild:
            return
        guild: Guild = message.guild

        # checks that the message author is a member
        if not isinstance(message.author, Member):
            return
        member: Member = message.author

        # checks if the message was from the bot so it can be ignored
        if message.author == bot.user:
            #logger.debug(f"on_message: message is from the bot")
            return

        # check if the message is a command so it can be ignored by this function
        if (m := message.content) and m[0: len(command_prefix)] == command_prefix:
            #logger.debug(f"on_message: message is a command")
            return

        # if the channel isn't a text channel then we ignore the message
        if not isinstance((channel := message.channel), TextChannel):
            #logger.debug(f"on_message: message not in text channel")
            return
        channel: TextChannel

        if guild_states[guild].member_states[member].mimic_member:
            logger.debug(f"mimicking {message.content =}")
            vc = get_current_voice_client(guild, bot)
            if vc:
                await mimic(guild_states[guild], channel, vc,  message.content)

        if guild_states[guild].member_states[member].echo_member:
            logger.debug(f"echoing {message =}")
            await echo(channel, message.content )

    bot.run(TOKEN)

if __name__ == '__main__':
    main()