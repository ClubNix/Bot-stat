import discord
from discord.ext import commands, tasks
from discord import ApplicationContext, option

from database.database import DatabaseHandler
from logwrite import LOG_FILE, ERROR_FILE
from psycopg2 import Error as DBError

import os
import logwrite as log

class Owner(commands.Cog):
    _SCRIPT_DIR = os.path.dirname(__file__)
    _SQL_FILE = os.path.join(_SCRIPT_DIR, '../database/backup.sql')
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DatabaseHandler(os.path.basename(__file__))
        self.daily_backup.start()

    def cog_check(self, ctx: ApplicationContext):
        return self.bot.is_owner(ctx.author) or ctx.author.guild_permissions.administrator

    @commands.slash_command(description="Stop the bot")
    async def stop_josix(self, ctx: ApplicationContext):
        await ctx.respond("Stopping...")
        await self.bot.close()

    @commands.slash_command(description="Create a backup for the database")
    @option(
        input_type=str,
        name="table",
        description="Name of the table to backup",
        default=""
    )
    async def create_backup(self, ctx: ApplicationContext, table: str):
        await ctx.defer(ephemeral=False, invisible=False)
        self.db.backup(table)
        await ctx.respond("Backup done !")

    @commands.slash_command(description="Execute a query")
    @commands.is_owner()
    @option(
        input_type=str,
        name="query",
        description="Query to execute",
        required=True
    )
    async def execute(self, ctx: ApplicationContext, query: str):
        await ctx.defer(ephemeral=False, invisible=False)
        try:
            await ctx.respond(self.db.execute(query))
        except discord.HTTPException as e:
            await ctx.respond(e)

    @commands.slash_command(description="Execute the backup file")
    @commands.is_owner()
    async def execute_backup(self, ctx: ApplicationContext):
        await ctx.defer(ephemeral=False, invisible=False)
        count = 0
        tmp = ""
        msg = ""

        with open(Owner._SQL_FILE, 'r') as f:
            lines = f.readlines()
        for index, line in enumerate(lines):
            try:
                self.db.execute(line, True)
            except DBError as db_error:
                tmp = f"**l.{index+1}** : {str(db_error)}\n"
                lenTmp = len(tmp)
                if lenTmp + count > 2000:
                    await ctx.respond(msg)
                    count = lenTmp
                    msg = tmp
                else:
                    count += lenTmp
                    msg += tmp

            except Exception as error:
                tmp = f"**l.{index+1}** : Unexcepted error\n"
                lenTmp = len(tmp)
                if lenTmp + count > 2000:
                    await ctx.respond(msg)
                    count = lenTmp
                    msg = tmp
                else:
                    count += lenTmp
                    msg += tmp
                log.writeError(log.formatError(error))
        
        if count > 0:
            await ctx.respond(msg)
        await ctx.respond("Backup execute done !")

    async def lineDisplay(self, ctx: ApplicationContext, filePath: str, limit: int, isError: bool):
        count = 0
        msg = ""

        with open(filePath, "r") as f:
            for line in (f.readlines()[-limit:]):
                newLine = "\n" + log.adjustLog(line, isError)
                lenLine = len(newLine)

                if lenLine + count > 2000:
                    await ctx.respond(f"```{msg}```")
                    count = lenLine
                    msg = lenLine
                else:
                    count += lenLine
                    msg += newLine

        await ctx.respond(f"```{msg}```")

    @commands.slash_command(description="Display the last logs")
    @option(
        input_type=int,
        name="count",
        description="Number of lines to get",
        default=10
    )
    async def display_logs(self, ctx: ApplicationContext, count: int):
        await ctx.defer(ephemeral=False, invisible=False)
        await self.lineDisplay(ctx, LOG_FILE, count, False)

    @commands.slash_command(description="Display the last errors")
    @option(
        input_type=int,
        name="count",
        description="Number of lines to get",
        default=10
    )
    async def display_errors(self, ctx: ApplicationContext, count: int):
        await ctx.defer(ephemeral=False, invisible=False)
        await self.lineDisplay(ctx, ERROR_FILE, count, True)

    
    @tasks.loop(hours=24.0)
    async def daily_backup(self):
        try:
            self.db.backup("", True)
        except Exception as e:
            log.writeError(log.formatError(e))


def setup(bot: commands.Bot):
    bot.add_cog(Owner(bot))
