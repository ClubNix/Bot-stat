import discord
from discord.ext import commands
from discord.errors import NotFound, Forbidden
from discord.ext.commands import BotMissingPermissions, MissingPermissions, MissingRequiredArgument, NoPrivateMessage, \
    CommandOnCooldown, NotOwner
from discord import RawReactionActionEvent, RawThreadUpdateEvent ,ApplicationContext, DiscordException
from discord.utils import get as discordGet

from database.database import DatabaseHandler
from json import JSONDecodeError

import logwrite as log
import os
import json


class Events(commands.Cog):
    _SCRIPT_DIR = os.path.dirname(__file__)
    _FILE_PATH = os.path.join(_SCRIPT_DIR, '../config.json')

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DatabaseHandler(os.path.basename(__file__))

        self.close = ""
        self.open = ""

        try:
            with open(Events._FILE_PATH, "r") as f:
                data = json.load(f)

            self.close = data["tags"]["closed"]
            self.open = data["tags"]["open"]
        except (JSONDecodeError, FileNotFoundError, KeyError):
            pass

    async def updateRole(self, payload: RawReactionActionEvent, add: bool):
        emoji = payload.emoji
        if emoji.is_custom_emoji():
            return

        msgId = payload.message_id
        resMsg = self.db.getMsg(msgId)
        if resMsg is None or len(resMsg) == 0:
            return

        if payload.message_id in resMsg:
            userId = payload.user_id
            guildId = payload.guild_id
            emojiName = emoji.name

            guild = self.bot.get_guild(guildId)
            member = guild.get_member(userId)

            resRoles = self.db.getRoleFromReact(msgId, emojiName)
            if resRoles is None:
                return

            roleId = resRoles[0]
            role = guild.get_role(roleId)

            if add:
                if not member.get_role(roleId):
                    await member.add_roles(role)
            else:
                if member.get_role(roleId):
                    await member.remove_roles(role)

    async def getTags(thread: discord.Thread, close: str, open: str) -> tuple[discord.ForumTag | None]:
        cTag: discord.ForumTag = None
        oTag: discord.ForumTag = None

        if close != "":
            cTag = discordGet(thread.parent.available_tags, name=close)

        if open != "":
            oTag = discordGet(thread.parent.available_tags, name=open)

        newTags = thread.parent.available_tags.copy()
        if not cTag:
            cTag = discord.ForumTag(name=close, emoji="🔴")
            newTags.append(cTag)
        if not oTag:
            oTag = discord.ForumTag(name=open, emoji="🟢")
            newTags.append(oTag)

        if len(newTags) > len(thread.parent.available_tags):
            await thread.parent.edit(available_tags=newTags)

        return (cTag, oTag)

# ==================================================
# ==================================================
# ==================================================

    @commands.Cog.listener()
    async def on_ready(self):
        log.writeLog(f"==> Bot ready : py-cord v{discord.__version__}\n")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        await self.updateRole(payload, True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        await self.updateRole(payload, False)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if not isinstance(thread.parent, discord.ForumChannel):
            return

        _, oTag = await Events.getTags(thread, self.close, self.open)
        if oTag and oTag not in thread.applied_tags:
            tags = thread.applied_tags.copy()
            if not tags or len(tags <= 0):
                tags = [oTag]
            else:
                tags.append(oTag)

            await thread.edit(applied_tags=tags)
        await thread.send("This thread is now open. You can close it automatically by using `/close`")

    @commands.Cog.listener()
    async def on_raw_thread_update(self, payload: RawThreadUpdateEvent):
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        if not payload.thread:
            thread = guild.get_thread(payload.thread_id)
            if not thread:
                return
        else:
            thread = payload.thread

        if not isinstance(thread.parent, discord.ForumChannel):
            return

        data = payload.data
        cTag, oTag = await Events.getTags(thread, self.close, self.open)
        tags = thread.applied_tags.copy()
        if data["thread_metadata"]["archived"] and data["thread_metadata"]["locked"]:
            # You can't edit archived thread and this current method creates useless loop
            """
            try:
                if oTag:
                    try:
                        del tags[tags.index(oTag)]
                    except (ValueError, IndexError):
                        pass

                if cTag and not cTag in tags:
                    tags.append(cTag)
                    await thread.unarchive()
                    await thread.edit(applied_tags=tags)
                    await thread.archive()
            except Exception as e:
                log.writeError(log.formatError(e))
            """

        elif not data["thread_metadata"]["archived"]:
            try:
                if cTag:
                    try:
                        del tags[tags.index(cTag)]
                    except (ValueError, IndexError):
                        pass

                if oTag and not oTag in tags:
                    tags.append(oTag)
                    await thread.edit(applied_tags=tags)
            except Exception as e:
                log.writeError(log.formatError(e))

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx: ApplicationContext, error: DiscordException):
        if isinstance(error, Forbidden):
            await ctx.respond("Ho no i can't do something :(")
        elif isinstance(error, NotFound):
            await ctx.respond("Bip Boup **Error 404**")
        elif isinstance(error, BotMissingPermissions):
            await ctx.respond("HEY ! Gimme more permissions...")
        elif isinstance(error, MissingPermissions):
            await ctx.respond("Sorry but you lack permissions (skill issue)")
        elif isinstance(error, MissingRequiredArgument):
            await ctx.respond("An argument is missing in your command (skill issue n°2)")
        elif isinstance(error, NoPrivateMessage):
            await ctx.respond("This command can only be used in a server (get some friends)")
        elif isinstance(error, CommandOnCooldown):
            error: CommandOnCooldown = error
            await ctx.respond(f"Too fast bro, wait {round(error.retry_after, 2)} seconds to retry this command")
        elif isinstance(error, NotOwner):
            await ctx.respond("This command is only for my master ! (skill issue n°3)")
        else:
            await ctx.respond("Unknown error occured")
            log.writeError(log.formatError(error))
        

def setup(bot: commands.Bot):
    bot.add_cog(Events(bot))
