import discord
from discord.ext import commands
from discord import ApplicationContext
from discord import ExtensionFailed, ExtensionNotLoaded, ExtensionAlreadyLoaded, ExtensionNotFound, NoEntryPointError

from . import FILES
from database.database import DatabaseHandler

import logwrite as log
import os

SCRIPT_DIR = os.path.dirname(__file__)
FILE_PATH = os.path.join(SCRIPT_DIR, 'backup.sql')

class Owner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DatabaseHandler()

    def load(self, name):
        name = "cogs." + name
        try:
            self.bot.load_extension(name)
            log.writeLog(f"### Loaded extension : {name}")
        except (ModuleNotFoundError, ExtensionNotFound, ExtensionAlreadyLoaded, NoEntryPointError, ExtensionFailed) as error:
            log.writeError(log.formatError(error))

    def unload(self, name):
        name = "cogs." + name
        try:
            self.bot.unload_extension(name)
            log.writeLog(f"### Unloaded extension : {name}")
        except (ModuleNotFoundError, ExtensionNotFound, ExtensionNotLoaded) as error:
            log.writeError(log.formatError(error))

    def reload(self, name):
        name = "cogs." + name
        try:
            self.bot.reload_extension(name)
            log.writeLog(f"### Reloaded extension : {name}")
        except (ModuleNotFoundError, ExtensionNotFound, ExtensionNotLoaded, NoEntryPointError, ExtensionFailed) as error:
            log.writeError(log.formatError(error))


######################################
#                                    #
# ------------ Commands ------------ #
#                                    #
######################################


    @commands.slash_command(description="Stop the bot")
    @commands.is_owner()
    async def stop_josix(self, ctx: ApplicationContext):
        await ctx.respond("Stopping...")
        await self.bot.close()

    @commands.slash_command(
        description="Load a specific cog",
        options=[discord.Option(
            input_type=str,
            name="name",
            description="Extension name",
            required=True
        )]
    )
    @commands.is_owner()
    async def load_cog(self, ctx: ApplicationContext, name: str):
        self.load(name)
        await ctx.respond("Load done !")


    @commands.slash_command(
        description="Unload a specific cog",
        options=[discord.Option(
            input_type=str,
            name="name",
            description="Extension name",
            required=True
        )]
    )
    @commands.is_owner()
    async def unload_cog(self, ctx: ApplicationContext, name: str):
        self.unload(name)
        await ctx.respond("Unload done !")


# --------------------------------------------- #


    @commands.slash_command(
        description="reload a specific cog",
        options=[discord.Option(
            input_type=str,
            name="name",
            description="Extension name",
            required=True
        )]
    )
    @commands.is_owner()
    async def reload_cog(self, ctx: ApplicationContext, name: str):
        self.reload(name)
        await ctx.respond("Reload done !")

    @commands.slash_command(description="Load all the cogs")
    async def load_all(self, ctx: ApplicationContext):
        for name in FILES:
            if name == "owner":
                continue

            self.load(name)
        await ctx.respond("Load done !")

    @commands.slash_command(description="Unoad all the cogs")
    async def unload_all(self, ctx: ApplicationContext):
        for name in FILES:
            if name == "owner":
                continue

            self.unload(name)
        await ctx.respond("Unload done !")

    @commands.slash_command(description="Reload all the cogs")
    async def reload_all(self, ctx: ApplicationContext):
        for name in FILES:
            if name == "owner":
                continue

            self.reload(name)
        await ctx.respond("Reload done !")


# ---------------------------------------- #

    
    @commands.slash_command(
        description="Create a backup for the databse",
        options=[discord.Option(
            input_type=str,
            name="table",
            description="Name of the table to backup",
            default=None
        )]
    )
    @commands.is_owner()
    async def backup_database(self, ctx: ApplicationContext, table: str):
        self.db.backup(table)
        await ctx.respond("Backup done !")

    @commands.slash_command(
        description="Execute a query",
        options=[discord.Option(
            input_type=str,
            name="query",
            description="Query to execute",
            required=True
        )]
    )
    @commands.is_owner()
    async def execute(self, ctx: ApplicationContext, query: str):
        await ctx.respond(self.db.execute(query))

    @commands.slash_command(description="Execute the backup file")
    @commands.is_owner()
    async def backup_execute(self, ctx: ApplicationContext):
        with open(FILE_PATH, 'r') as f:
            lines = f.readlines()

        for line in lines:
            self.db.execute(line)
        
        await ctx.respond("Backup execute done !")


def setup(bot: commands.Bot):
    bot.add_cog(Owner(bot))