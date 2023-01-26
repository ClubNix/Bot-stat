import discord
from discord.ext import commands, tasks
from discord import ApplicationContext
from discord import option

import random
import datetime

from . import FILES
from database.database import DatabaseHandler

class Usage(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DatabaseHandler()
        self.checkBirthday.start()

    @commands.slash_command(
        description="Get the help menu",
        options=[discord.Option(input_type=str,
            name="command_name",
            description="Name of the command",
            default=None,
        )]
    )
    async def help(self, ctx: ApplicationContext, command_name: str):
        av_aut = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar
        av_bot = self.bot.user.avatar.url if self.bot.user.avatar else self.bot.user.default_avatar

        if not command_name:
            helpEmbed = discord.Embed(title="Help embed", description=f"Use /help [command_name] to see more info for a command", color = 0x0089FF)
            helpEmbed.set_author(name=ctx.author, icon_url=av_aut)
            helpEmbed.set_thumbnail(url=av_bot)
            for cogName in FILES:
                lstCmd = ""
                cog = self.bot.get_cog(FILES[cogName])

                if not cog:
                    continue
                commands = cog.get_commands()
                if len(commands) == 0:
                    lstCmd = "No commands available"
                else:
                    for command in commands:
                        lstCmd += "`" + command.qualified_name + "`, "
                    lstCmd = lstCmd[:len(lstCmd)-2]
                helpEmbed.add_field(name=cogName, value=lstCmd, inline=False)
            await ctx.respond(embed=helpEmbed)

        else:
            command_name = command_name.lower()
            command: discord.SlashCommand = self.bot.get_application_command(name=command_name, type=discord.SlashCommand)

            if not command:
                await ctx.respond(f":x: Unknown command, see /help :x:")
                return

            if command.description == "":
                desc = "No description"
            else:
                desc = command.description

            usage = f"/{command.name} "
            param = command.options
            options = ""
            
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
                    

            embed2 = discord.Embed(title = "Help command", description = f"Description of the command **{command.name}**\n <> -> Required parameters | [] -> Optional parameters", color = 0x0089FF)
            embed2.set_thumbnail(url = av_bot)
            embed2.set_author(name = ctx.author, icon_url = av_aut)
            embed2.add_field(name = "Description :", value = desc)
            embed2.add_field(name = "Usage :", value = usage, inline = False)
            embed2.add_field(name = "Options : ", value = options, inline = False)
            await ctx.respond(embed = embed2)

    @commands.slash_command(
        description="Randomly choose a sentence from a list",
        options=[discord.Option(input_type=str,
            name="sentences",
            description="List of sentences separated by a `;`",
            required=True
        )]
    )
    async def choose(self, ctx: ApplicationContext, sentences: str):
        values = sentences.split(";")
        embed = discord.Embed(title="Result", description=random.choice(values))
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar.url)
        await ctx.respond(embed=embed)

    @commands.slash_command(description="Close a thread in the forum channel. Can only be used by the creator of the thread or a moderator")
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
    
        testMod = ctx.author.guild_permissions >= discord.Permissions(17179869184) # Check if permissions are greater than manage_threads
        if (ctx.author != thread.owner and not testMod) or (lock and not testMod): 
            await ctx.respond("You don't have the required permissions to do this")
            return

        await ctx.respond(f"Closing the thread.\nLocking : {lock}")
        await thread.archive(locked=lock)
        
    @commands.slash_command(description="Add your birthday in the database !")
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
    async def add_birthday(self, ctx: ApplicationContext, day: int, month: int):
        month_days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        testReject = not ((1 <= month and month <= 12) and (1 <= day and day <= month_days[month-1]))
        userId = ctx.author.id
        testUser = None
        testGuild = None
        testBoth = None
        bdYear = 0

        if testReject:
            ctx.respond("Invalid date !")
            return

        testUser = self.db.getUser(userId)
        if not testUser or len(testUser) == 0:
            self.db.addUser(userId)

        testGuild = self.db.getGuild(ctx.guild_id)
        if not testGuild or len(testGuild) == 0:
            self.db.addGuild(ctx.guild_id)

        testBoth = self.db.getUserInGuild(userId, ctx.guild_id)
        if not testBoth or len(testBoth) == 0:
            self.db.addUserGuild(userId, ctx.guild_id)

        today = datetime.date.today()
        if today.month < month or (today.month == month and today.day <= day):
            bdYear = today.year
        else:
            bdYear = today.year - 1

        self.db.updateUserBD(userId, day, month, bdYear)
        await ctx.respond("Your birthday has been added !")



    def getMonthField(self, embed: discord.Embed, idGuild:int, monthInt: int):
        months=["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        res=[]

        values = self.db.getBDMonth(idGuild, monthInt)
        if values == None or len(values) == 0:
            return embed

        for val in values:
            res.append(f"`{val[0]}/{val[1]}` (<@{val[2]}>)")

        return embed.add_field(name=months[monthInt-1], value=" , ".join(res))


    @commands.slash_command(description="See all the birthdays of this server")
    @option(
        input_type=int,
        name="month",
        description="Number of the month you want to get all the birthdays from",
        min_value=1,
        max_value=12,
        default=None
    )
    async def birthdays(self, ctx: ApplicationContext, month: int): 
        embed = discord.Embed(
            title=f"Birthdays of **{ctx.guild.name}**",
            description="All the birthdays form the server",
            color=0x0089FF
        )

        av_aut = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar
        embed.set_author(name=ctx.author, icon_url=av_aut)

        if month:
            embed = self.getMonthField(embed, ctx.guild_id, month)
        else:
            for i in range(12):
                embed = self.getMonthField(embed, ctx.guild_id, i+1)
        await ctx.respond(embed=embed)

    @commands.slash_command(description="Get the birthday of a user")
    @option(
        input_type=discord.User,
        name="user",
        description="Mention of the user",
        required=True
    )
    async def user_birthday(self, ctx: ApplicationContext, user: discord.User):
        res = self.db.getBDUser(user.id)
        if not res or len(res) == 0:
            await ctx.respond("User not registered")
            return

        av_aut = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar
        embed = discord.Embed(title=f"Birthday of {user}", color=0x0089FF)
        embed.set_author(name=ctx.author, icon_url=av_aut)
        embed.add_field(name="Date", value=res[0])
        await ctx.respond(embed=embed)


    @tasks.loop(minutes=1.0)
    async def checkBirthday(self):
        bd = self.db.checkBD()

        for value in bd:
            idUser = value[0]
            results = self.db.getNewsChan(idUser)

            for row in results:
                chan = self.bot.get_channel(row[0])
                if not chan:
                    continue


                today = datetime.date.today()
                self.db.updateUserBD(idUser, today.day, today.month, today.year)
                await chan.send(f"Happy birthday to <@{idUser}> :tada: !")


def setup(bot: commands.Bot):
    bot.add_cog(Usage(bot))
