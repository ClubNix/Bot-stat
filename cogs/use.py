import datetime
import json
import os
import random
from json import JSONDecodeError
from math import ceil

import discord
from discord import ApplicationContext, option
from discord.ext import commands, tasks

import pkg.logwrite as log
from cogs.events import Events
from database.services import (
    birthday_service,
    discord_service,
    guild_service,
)
from josix import Josix
from pkg.bot_utils import JosixCog, JosixSlash, get_permissions_str, josix_slash


class Poll(discord.ui.Modal):
    """A class representing a modal to create custom polls on discord"""

    def __init__(self) -> None:
        super().__init__(title="Poll", timeout=300.0)
        self.add_item(discord.ui.InputText(
            label="Title (optional)",
            max_length=64,
            style=discord.InputTextStyle.singleline,
            row=0,
            required=False
        ))
        self.add_item(discord.ui.InputText(
            label="Content",
            min_length=1,
            max_length=512,
            style=discord.InputTextStyle.paragraph,
            row=1
        ))

    async def callback(self, interaction: discord.Interaction):
        if not interaction:
            return

        title = self.children[0]
        content = self.children[1]
        text = (f"# {title.value} :\n\n" if title.value else "") + (content.value if content.value else "")

        msg = await interaction.response.send_message(content=text)
        og = await msg.original_response()
        await og.add_reaction("✅")
        await og.add_reaction("❌")


class Usage(JosixCog):
    """
    Represents the common use functions extension of the bot

    Attributes
    ----------
    bot : Josix
        The bot that loaded this extension
    """
        
    _SCRIPT_DIR = os.path.dirname(__file__)
    _FILE_PATH = os.path.join(_SCRIPT_DIR, '../configs/config.json')

    def __init__(self, bot: Josix, showHelp: bool):
        super().__init__(showHelp=showHelp)
        self.bot = bot
        self.checkBirthday.start()

    @josix_slash(description="Get the help menu")
    @option(
        input_type=str,
        name="command_name",
        description="Name of the command",
        default=None,
    )
    async def help(self, ctx: ApplicationContext, command_name: str):
        def clean_commands(raw_commands: list[JosixSlash | commands.Command]) -> list[JosixSlash | commands.Command]:
            cleaned_commands: list[JosixSlash | commands.Command] = []
            for command in raw_commands:
                if isinstance(command, JosixSlash) and command.hidden:
                    continue
                elif isinstance(command, commands.Command) and command.hidden:
                    continue
                cleaned_commands.append(command)
            return cleaned_commands

        if not self.bot.user:
            await ctx.respond("Unexpected data error")
            return

        if not command_name:
            helpEmbed = discord.Embed(title="Help embed",
                                      description="Use /help [command_name] to see more info for a command",
                                      color=0x0089FF)
            helpEmbed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
            helpEmbed.set_thumbnail(url=self.bot.user.display_avatar)
            
            gamesCmd: list[str] = []
            for cogName, cog in self.bot.cogs.items():
                lstCmd = ""

                if not isinstance(cog, JosixCog):
                    continue

                josix_cog: JosixCog = cog
                if (
                    not josix_cog or
                    not josix_cog.showHelp or
                    (josix_cog.isOwner and not (await self.bot.is_owner(ctx.author) or ctx.author.guild_permissions.administrator))
                ):
                    continue

                if josix_cog.isGame:
                    gamesCmd.extend(list(map(str, clean_commands(josix_cog.get_commands())))) # type: ignore
                    continue

                cleaned_commands: list[JosixSlash | commands.Command] = clean_commands(josix_cog.get_commands()) # type: ignore
                if len(cleaned_commands) == 0:
                    lstCmd = "No commands available"
                else:
                    for cmd in cleaned_commands:
                        lstCmd += "`" + cmd.qualified_name + "`, "
                    lstCmd = lstCmd[:len(lstCmd) - 2]
                helpEmbed.add_field(name=cogName, value=lstCmd, inline=False)

            if len(gamesCmd) > 0:
                helpEmbed.add_field(name="Games", value="`" + "`, `".join(gamesCmd) + "`", inline=False)
            await ctx.respond(embed=helpEmbed)

        else:
            command_name = command_name.lower()
            command: discord.SlashCommand = self.bot.get_application_command(name=command_name,
                                                                             type=discord.SlashCommand) # type: ignore
            if not command:
                await ctx.respond((
                    "This option is only possible for slash commands" if self.bot.get_command(command_name)
                    else ":x: Unknown command, see /help :x:"
                ))
                return

            if command.cog and command.cog.qualified_name.lower() == "owner" and not (
                await self.bot.is_owner(ctx.author) or ctx.author.guild_permissions.administrator
            ):
                await ctx.respond(":x: Unknown command, see /help :x:")
                return

            if command.description == "":
                desc = "No description"
            else:
                desc = command.description

            usage = f"/{command.name} "
            param = command.options
            options = ""

            if command.default_member_permissions:
                cmd_perms = get_permissions_str(command.default_member_permissions)
            else:
                cmd_perms = [] 

            for val in param:
                default = val.default
                if default:
                    default = f" = {default}"
                else:
                    default = ""

                if val.required:
                    usage += f"<{val.name}{default}> "
                else:
                    usage += f"[{val.name}{default}] "

                options += f"**{val.name}** : {val.description}\n"

            embed2 = discord.Embed(title="Help command",
                                   description=f"Description of the command **{command.name}**\n <> -> Required "
                                               f"parameters | [] -> Optional parameters",
                                   color=0x0089FF)
            embed2.set_thumbnail(url=self.bot.user.display_avatar)
            embed2.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
            embed2.add_field(name="Description :", value=desc)
            embed2.add_field(name="Usage :", value=usage, inline=False)
            embed2.add_field(name="Options : ", value=options, inline=False)
            embed2.add_field(
                name="Permissions Required", value=", ".join(cmd_perms)[:1023] if cmd_perms else "No permissions required"
            )
            await ctx.respond(embed=embed2)

    @josix_slash(description="All the links related to the bot and club")
    async def links(self, ctx: ApplicationContext):
        if not self.bot.user:
            await ctx.respond("Unexpected data error")
            return

        try:
            with open(Usage._FILE_PATH, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, JSONDecodeError) as e:
            if isinstance(e, FileNotFoundError):
                log.writeError("Config file does not exist")
            elif isinstance(e, JSONDecodeError):
                log.writeError("Json error, make sure the config file is not empty")

            await ctx.respond("Configuration error")
            return

        try:
            links = [f"[{name}]({link})" for name, link in data["links"].items() if name and link]
        except KeyError:
            await ctx.respond("Configuration error")
            return

        embed = discord.Embed(
            title="Links",
            description="All the related and useful links",
            color=0x0089FF
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url=self.bot.user.display_avatar)
        embed.add_field(name="", value="\n".join(links))
        await ctx.respond(embed=embed)

    @josix_slash(description="Randomly choose a sentence from a list", give_xp=True)
    @option(
        input_type=str,
        name="sentences",
        description="List of sentences separated by a `;`",
        max_length=512,
        required=True
    )
    async def choose(self, ctx: ApplicationContext, sentences: str):
        values = sentences.split(";")
        embed = discord.Embed(title="Result", description=random.choice(values))
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        await ctx.respond(embed=embed)

    @josix_slash(
        description="Close a thread in the forum channel. Can only be used by the creator of the thread or a moderator")
    @commands.guild_only()
    @option(
        name="lock",
        description="Lock the thread (moderator only)",
        type=bool,
        default=False
    )
    async def close(self, ctx: ApplicationContext, lock: bool):
        thread = ctx.channel
        if not (isinstance(thread, discord.Thread) and isinstance(thread.parent, discord.ForumChannel)):
            await ctx.respond("You can only close a thread created in the forum")
            return

        testMod = ctx.author.guild_permissions.manage_threads  # Check if permissions are greater than manage_threads
        if (ctx.author != thread.owner and not testMod) or (lock and not testMod):
            await ctx.respond("You don't have the required permissions to do this")
            return

        if lock:
            closeName = ""
            try:
                with open(Usage._FILE_PATH, "r") as f:
                    data = json.load(f)

                closeName = data["tags"]["closed"]
                openName = data["tags"]["open"]
            except (JSONDecodeError, FileNotFoundError, KeyError):
                pass

            if closeName != "" and openName != "":
                result = await Events.getTags(thread, closeName, openName)
                if not result:
                    await ctx.respond("Forum tags error")
                    return

                cTag, oTag = result
                if not (cTag and oTag):
                    await ctx.respond("Forum tags error")
                    return

                tags = thread.applied_tags.copy()
                if cTag and cTag not in tags:
                    tags.append(cTag)

                try:
                    del tags[tags.index(oTag)]
                except (ValueError, IndexError):
                    pass

                await thread.edit(applied_tags=tags)

        await ctx.respond(f"Closing the thread.\nLocking : {lock}")
        await thread.archive(locked=lock)

    @josix_slash(description="Get full price for a 3D print")
    @option(
        input_type=float,
        name="cura_price",
        description="Price given by Cura in €",
        required=True,
        min_value=0.1
    )
    @option(
        input_type=int,
        name="minutes_count",
        description="Number of minutes for the print (rounded up)",
        required=True,
        min_value=1
    )
    @option(
        input_type=bool,
        name="is_member",
        description="Is the person asking for the print is a member or no",
        required=True
    )
    async def print_price(
        self,
        ctx: ApplicationContext,
        cura_price: float,
        minutes_count: float,
        is_member: bool
    ):
        """ function : https://cdn.discordapp.com/attachments/751051007110283365/987326536837373992/Screenshot_from_2022-06-17_14-02-05.png """
        if cura_price <= 0.0 or minutes_count <= 0.0:
            await ctx.respond("The cura price and number of minutes should be greater than zero.")
            return

        factor = 1 if is_member else 1.5
        minutesFactor = 1 + (((minutes_count // 30) + (1 if minutes_count % 30 > 0 else 0)) / 20)
        finalPrice = ceil(10*(cura_price * minutesFactor * factor)) / 10
        await ctx.respond(f"The price for this print is : **{finalPrice} €**")

    @josix_slash(description="Create a poll on this server")
    @commands.guild_only()
    @discord.default_permissions(manage_messages=True)
    async def create_poll(self, ctx: ApplicationContext):
        await ctx.send_modal(Poll())

    @josix_slash(description="Add your birthday in the database !", give_xp=True)
    @commands.guild_only()
    @option(
        input_type=int,
        name="day",
        description="Day number of your birthday",
        required=True
    )
    @option(
        input_type=int,
        name="month",
        description="Month number of your birthday",
        required=True
    )
    @option(
        input_type=discord.User,
        name="user",
        description="Mention of the user's birthday you want to add",
        default=None
    )
    async def add_birthday(self, ctx: ApplicationContext, day: int, month: int, user: discord.User):
        await ctx.defer(ephemeral=False, invisible=False)

        month_days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        testReject = not ((1 <= month and month <= 12) and (1 <= day and day <= month_days[month - 1]))
        userId = ctx.author.id
        testUser = None
        testGuild = None
        testBoth = None
        bdYear = 0
        stringRes = ""
        handler = self.bot.get_handler()

        if testReject:
            await ctx.respond("Invalid date !")
            return

        if user and user != ctx.author:
            if ctx.author.guild_permissions.moderate_members:
                userId = user.id
                stringRes = f"Birthday added for **{user.name}** !"
            else:
                await ctx.respond("Sorry but you lack permissions (skill issue)")
                return
        else:
            stringRes = "Your birthday has been added !"

        testUser = discord_service.get_user(handler, userId)
        if not testUser:
            discord_service.add_user(handler, userId)

        testGuild = discord_service.get_guild(handler, ctx.guild_id)
        if not testGuild:
            discord_service.add_guild(handler, ctx.guild_id)

        testBoth = discord_service.get_user_in_guild(handler, userId, ctx.guild_id)
        if not testBoth:
            discord_service.add_user_in_guild(handler, userId, ctx.guild_id)

        today = datetime.date.today()
        if today.month < month or (today.month == month and today.day < day):
            bdYear = today.year - 1
        else:
            bdYear = today.year

        birthday_service.update_user_birthday(handler, userId, day, month, bdYear)
        await ctx.respond(stringRes)

    @josix_slash(description="Remove a birthday date")
    @commands.guild_only()
    @option(
        name="member",
        input_type=discord.Member,
        description="The target member who will get its birthday removed",
        required=True
    )
    async def remove_birthday(self, ctx: ApplicationContext, member: discord.Member):
        await ctx.defer(ephemeral=False, invisible=False)

        if member != ctx.author and ctx.author.guild_permissions.moderate_members:
            await ctx.respond("You don't have the required permissions to remove another user birthday")
            return

        birthday_service.remove_user_birthday(self.bot.get_handler(), member.id)
        await ctx.respond("Birthday successfully removed !")

    def getMonthField(self, embed: discord.Embed, idGuild: int, monthInt: int):
        months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December"]
        res = []

        values = birthday_service.get_birthday_month(self.bot.get_handler(), idGuild, monthInt)
        if not values:
            return embed

        for val in values:
            res.append(f"`{val.day}/{val.month}` (<@{val.idUser}>)")

        return embed.add_field(name=months[monthInt - 1], value=" , ".join(res))

    @josix_slash(description="See all the birthdays of this server")
    @commands.guild_only()
    @option(
        input_type=int,
        name="month",
        description="Number of the month you want to get all the birthdays from",
        min_value=1,
        max_value=12,
        default=None
    )
    async def birthdays(self, ctx: ApplicationContext, month: int):
        await ctx.defer(ephemeral=False, invisible=False)
        embed = discord.Embed(
            title=f"Birthdays of **{ctx.guild.name}**",
            description="All the birthdays from the server",
            color=0x0089FF
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)

        if month:
            embed = self.getMonthField(embed, ctx.guild_id, month)
        else:
            for i in range(12):
                embed = self.getMonthField(embed, ctx.guild_id, i + 1)
        await ctx.respond(embed=embed)

    @josix_slash(description="Get the birthday of a user")
    @commands.guild_only()
    @option(
        input_type=discord.User,
        name="user",
        description="Mention of the user",
        required=True
    )
    async def user_birthday(self, ctx: ApplicationContext, user: discord.User):
        await ctx.defer(ephemeral=False, invisible=False)
        res = discord_service.get_user(self.bot.get_handler(), user.id)
        if not res:
            await ctx.respond("User not registered")
            return

        hbDate = res.hbDate
        embed = discord.Embed(title=f"Birthday of {user}", color=0x0089FF)
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.add_field(name="Date", value=f"**{hbDate.strftime('%d/%m')}**")
        await ctx.respond(embed=embed)

    @tasks.loop(hours=6.0)
    async def checkBirthday(self):
        today = datetime.date.today()
        handler = self.bot.get_handler()

        bd = birthday_service.check_birthday(handler, today.day, today.month)
        if not bd:
            return

        for value in bd:
            idUser = value.idUser
            results = guild_service.get_news_chan_from_user(handler, idUser)
            if not results:
                continue

            for idChan in results:
                chan = await self.bot.fetch_channel(idChan)
                if not chan:
                    continue

                today = datetime.date.today()
                await chan.send(f"Happy birthday to <@{idUser}> :tada: !")
                birthday_service.update_user_birthday(
                    handler,
                    idUser,
                    today.day, today.month, today.year
                )


def setup(bot: Josix):
    bot.add_cog(Usage(bot, True))
