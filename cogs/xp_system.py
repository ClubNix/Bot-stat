import datetime as dt

import discord
from discord import (
    AllowedMentions,
    ApplicationContext,
    DMChannel,
    GroupChannel,
    PartialMessageable,
    TextChannel,
    VoiceChannel,
    option,
)
from discord.abc import PrivateChannel
from discord.ext import commands, tasks

import pkg.logwrite as log
from database.services import (
    discord_service,
    season_service,
    xp_service,
)
from josix import Josix
from pkg.bot_utils import JosixCog, JosixSlash, josix_slash


class XP(JosixCog):
    """
    Represents the XP system extension of the bot

    Attributes
    ----------
    bot : Josix
        The bot that loaded this extension
    """

    def __init__(self, bot: Josix, showHelp: bool):
        super().__init__(showHelp=showHelp)
        self.bot = bot
        self.check_temporary.start()

    @staticmethod
    def nextLevelXP(lvl: int, xp: int = 0) -> int:
        """
        Calculate the XP needed to get to the next level

        Stolen from MEE6 : https://github.com/Mee6/Mee6-documentation/blob/master/docs/levels_xp.md

        Parameters
        ----------
        lvl : int
            Current level
        xp : int
            XP obtained so far

        Returns
        -------
        int
            The remaining xp needed
        """
        return 5 * (lvl**2) + (50 * lvl) + 100 - xp


    @staticmethod
    def totalLevelXP(lvl: int) -> int:
        """
        Calculate the XP needed to get to reach a level starting from 0

        Stolen from MEE6 : https://github.com/Mee6/Mee6-documentation/blob/master/docs/levels_xp.md

        Parameters
        ----------
        lvl : int
            Current level

        Returns
        -------
        int
            The amount of xp a user needs
        """
        if lvl <= 0:
            return 0

        res = 0
        for i in range(0, lvl):
            res += XP.nextLevelXP(i, 0)
        return res


    async def _updateUser(self, idTarget: int, idGuild: int, xp: int, idCat: int = 0) -> None:
        """
        Updates a user xp and level in the database

        Checks the state of the player then calculate the profits...
        and updates the values

        Parameters
        ----------
        idTarget : int
            ID of the user obtaining XP
        idGuild : int
            ID of the server where the interaction comes from
        xp : int
            The XP the user will obtain
        """
        handler = self.bot.get_handler()
        userDB, guildDB, userGuildDB = discord_service.fetch_user_guild_relationship(handler, idTarget, idGuild)

        if not (guildDB and userGuildDB):
            return

        xpChanId = guildDB.xpNews
        xpEnabled = guildDB.enableXp

        currentXP = userGuildDB.xp
        currentLvl = userGuildDB.lvl
        lastSend = userGuildDB.lastMessage
        userBlocked = userGuildDB.isUserBlocked

        if not xpEnabled or userBlocked:
            return

        if idCat != 0 and idCat in guildDB.blockedCat:
            return

        nowTime = dt.datetime.now()
        if ((nowTime - lastSend).seconds < 60):
            return

        xpNeed = self.nextLevelXP(currentLvl, currentXP - self.totalLevelXP(currentLvl))
        newLvl = xpNeed <= xp

        currentLvl = currentLvl + 1 if newLvl else currentLvl
        currentXP = min(1_899_250, currentXP+xp)

        xp_service.update_user_xp(handler, idTarget, idGuild, currentLvl, currentXP, nowTime)

        if newLvl and xpChanId:
            ping = currentLvl == 1 or userDB.pingUser
            info = ""
            if currentLvl == 1:
                info = "\nYou can toggle the ping with `/toggle_ping` command"

            mentions = AllowedMentions.none()
            if ping:
                mentions = AllowedMentions.all()

            if ((xpChan := self.bot.get_channel(xpChanId)) or (xpChan := await self.bot.fetch_channel(xpChanId))) and isinstance(xpChan, TextChannel):

                await xpChan.send(
                    f"Congratulations <@{idTarget}>, you are now level **{currentLvl}** with **{currentXP}** exp. ! 🎉" + info,
                    allowed_mentions=mentions
                )


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.bot.process_commands(message)
        if (
            message.author.bot or 
            isinstance(message.channel, (DMChannel, GroupChannel, VoiceChannel, PartialMessageable)) or
            not message.guild
        ):
            return

        idCat = message.channel.category_id
        msgLen = len(message.content)
        xp = 75 if msgLen >= 100 else 50 if msgLen >= 30 else 25

        try:
            await self._updateUser(
                message.author.id,
                message.guild.id,
                xp,
                idCat if idCat else 0
            )
        except Exception as e:
            log.writeError(log.formatError(e))

    @commands.Cog.listener()
    async def on_application_command_completion(self, ctx: ApplicationContext):
        if (
            ctx.author.bot or 
            isinstance(ctx.channel, discord.DMChannel) or
            isinstance(ctx.channel, discord.GroupChannel) or
            not isinstance(ctx.command, JosixSlash)
        ):
            return

        idCat = ctx.channel.category_id
        cmd: JosixSlash = ctx.command
        if not cmd.give_xp:
            return

        try:
            await self._updateUser(
                ctx.author.id,
                ctx.guild.id,
                25,
                idCat if idCat else 0
            )
        except Exception as e:
            log.writeError(log.formatError(e))


    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not (channel := self.bot.get_channel(payload.channel_id)) and not (channel := await self.bot.fetch_channel(payload.channel_id)):
            return

        if (
            not payload.member or
            not payload.guild_id or
            payload.member.bot or
            isinstance(channel, (DMChannel, GroupChannel, VoiceChannel, PartialMessageable, PrivateChannel))
        ):
            return

        idCat = channel.category_id
        try:
            await self._updateUser(
                payload.user_id,
                payload.guild_id,
                25,
                idCat if idCat else 0
            )
        except Exception as e:
            log.writeError(log.formatError(e))


####################
#
# Commands 
# 
####################


    @staticmethod
    def checkUpdateXP(currentXP: int, amount: int) -> tuple[int, int]:
        """Check the new level and xp after an update and returns these values"""
        newXP = currentXP + amount
        if newXP < 0:
            newXP = 0
        elif newXP > 1_899_250:
            newXP = 1_899_250

        level = 0
        xpNeed = XP.nextLevelXP(level)
        while xpNeed < newXP:
            level += 1
            xpNeed += XP.nextLevelXP(level)

        return newXP, level


    def _xp_update(self, member: discord.Member, amount: int) -> None:
        guild = member.guild
        handler = self.bot.get_handler()
        _, _, userGuildDB = discord_service.fetch_user_guild_relationship(handler, member.id, guild.id)

        if not userGuildDB:
            return

        if userGuildDB.isUserBlocked:
            return

        currentXP = userGuildDB.xp
        newXP, level = self.checkUpdateXP(currentXP, amount)
        xp_service.update_user_xp(handler, member.id, guild.id, level, newXP, dt.datetime.now())


    def _lvl_update(self, member: discord.Member, amount: int) -> None:
        guild = member.guild
        handler = self.bot.get_handler()
        _, _, userGuildDB = discord_service.fetch_user_guild_relationship(handler, member.id, guild.id)

        if not userGuildDB:
            return

        if userGuildDB.isUserBlocked:
            return

        currentLvl = userGuildDB.lvl
        newLvl = currentLvl + amount
        if newLvl < 0:
            newLvl = 0
        elif newLvl > 100:
            newLvl = 100

        xp = self.totalLevelXP(newLvl)
        xp_service.update_user_xp(handler, member.id, guild.id, newLvl, xp, dt.datetime.now())


    @josix_slash(description="Gives XP to a user")
    @discord.default_permissions(moderate_members=True)
    @commands.guild_only()
    @option(
        input_type=discord.Member,
        name="member",
        description="Mention of the target member",
        required=True
    )
    @option(
        input_type=int,
        name="amount",
        description="The amount of XP to give",
        min_value=1,
        required=True
    )
    async def give_xp(self, ctx: ApplicationContext, member: discord.Member, amount: int):
        await ctx.defer(ephemeral=False, invisible=False)
        if member.bot:
            await ctx.respond("You can't edit a bot's xp !")
            return

        try:
            if not discord_service.get_user_in_guild(self.bot.get_handler(), member.id, ctx.guild.id):
                await ctx.respond("User not registered.")
                return

            self._xp_update(member, amount)
        except Exception as e:
            log.writeError(log.formatError(e))

        await ctx.respond("Done !")


    @josix_slash(description="Removes XP to a user")
    @discord.default_permissions(moderate_members=True)
    @commands.guild_only()
    @option(
        input_type=discord.Member,
        name="member",
        description="Mention of the target member",
        required=True
    )
    @option(
        input_type=int,
        name="amount",
        description="The amount of XP to remove",
        min_value=1,
        required=True
    )
    async def remove_xp(self, ctx: ApplicationContext, member: discord.Member, amount: int):
        await ctx.defer(ephemeral=False, invisible=False)
        if member.bot:
            await ctx.respond("You can't edit a bot's xp !")
            return

        try:
            if not discord_service.get_user_in_guild(self.bot.get_handler(), member.id, ctx.guild.id):
                await ctx.respond("User not registered.")
                return

            self._xp_update(member, -amount)
        except Exception as e:
            log.writeError(log.formatError(e))

        await ctx.respond("Done !")


    @josix_slash(description="Gives levels to a user")
    @discord.default_permissions(moderate_members=True)
    @commands.guild_only()
    @option(
        input_type=discord.Member,
        name="member",
        description="Mention of the target member",
        required=True
    )
    @option(
        input_type=int,
        name="amount",
        description="The amount of levels to give",
        min_value=1,
        required=True
    )
    async def give_levels(self, ctx: ApplicationContext, member: discord.Member, amount: int):
        await ctx.defer(ephemeral=False, invisible=False)
        if member.bot:
            await ctx.respond("You can't edit a bot's levels !")
            return

        try:
            if not discord_service.get_user_in_guild(self.bot.get_handler(), member.id, ctx.guild.id):
                await ctx.respond("User not registered.")
                return

            self._lvl_update(member, amount)
        except Exception as e:
            log.writeError(log.formatError(e))

        await ctx.respond("Done !")


    @josix_slash(description="Removes levels to a user")
    @discord.default_permissions(moderate_members=True)
    @commands.guild_only()
    @option(
        input_type=discord.Member,
        name="member",
        description="Mention of the target member",
        required=True
    )
    @option(
        input_type=int,
        name="amount",
        description="The amount of levels to remove",
        min_value=1,
        required=True
    )
    async def remove_levels(self, ctx: ApplicationContext, member: discord.Member, amount: int):
        await ctx.defer(ephemeral=False, invisible=False)
        if member.bot:
            await ctx.respond("You can't edit a bot's levels !")
            return

        try:
            if not discord_service.get_user_in_guild(self.bot.get_handler(), member.id, ctx.guild.id):
                await ctx.respond("User not registered.")
                return

            self._lvl_update(member, -amount)
        except Exception as e:
            log.writeError(log.formatError(e))

        await ctx.respond("Done !")


    @josix_slash(description="Leaderboard of users based on their xp points in the server")
    @commands.cooldown(1, 30.0, commands.BucketType.user)
    @option(
        input_type=int,
        name="limit",
        description="Limit of users in the leaderboard (default 10)",
        default=10,
        min_value=1,
        max_value=50
    )
    @option(
        input_type=bool,
        name="all_time",
        description="Show the all-time leaderboard",
        default=False
    )
    async def leaderboard(self, ctx: ApplicationContext, limit: int, all_time: bool):
        await ctx.defer(ephemeral=False, invisible=False)
        idGuild = ctx.guild.id
        handler = self.bot.get_handler()

        if not self.bot.user:
            await ctx.respond("Unexpected error on data")
            return

        try:
            guildDB = discord_service.get_guild(handler, idGuild)
            if not guildDB:
                discord_service.add_guild(handler, idGuild)
                await ctx.respond("Server registered now. Try this command later")
                return
            elif not guildDB.enableXp:
                await ctx.respond("The xp system is not enabled in this server.")
                return

            lb = (
                xp_service.get_all_time_leaderboard(handler, idGuild, limit) if all_time else
                xp_service.get_leaderboard(handler, idGuild, limit)
            )
        except Exception as e:
            log.writeError(log.formatError(e))
            return

        embed = discord.Embed(
            title="XP Leaderboard",
            description=f"Current leaderboard for the server {ctx.guild.name}",
            color=0x0089FF
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url=self.bot.user.display_avatar)
        if not lb:
            await ctx.respond(embed=embed)
            return

        count = 0
        nbFields = 0
        res = ""
        for i, row in enumerate(lb):
            idUser, xp = row.idUser, row.xp
            text = f"**{i+1}** - <@{idUser}> ({xp})\n"
            if len(text) + count > 1024:
                embed.append_field(
                    discord.EmbedField(name="", value=res)
                )
                count = 0
                nbFields += 1
                res = ""
            if nbFields == 25:
                break
            
            res += text
            count += len(text)
        if len(text) > 0 and nbFields < 25:
            embed.append_field(
                discord.EmbedField(name="", value=res)
            )
        await ctx.respond(embed=embed)


    @josix_slash(description="Show the XP card of the user")
    @commands.cooldown(1, 30.0, commands.BucketType.user)
    @option(
        input_type=discord.Member,
        name="member",
        description="Mention of the target member",
        default=None
    )
    async def profile(self, ctx: ApplicationContext, member: discord.Member):
        await ctx.defer(ephemeral=False, invisible=False)
        if not member:
            member = ctx.author

        if member.bot:
            await ctx.respond("You can't use this command on a bot user.")
            return

        handler = self.bot.get_handler()
        idGuild = ctx.guild.id
        stats = discord_service.get_user_in_guild(handler, member.id, idGuild)
        if not stats:
            await ctx.respond("This user is not registered")
            return

        xp, lvl = stats.xp, stats.lvl
        lastNeed = self.totalLevelXP(lvl)
        xpNeed = lastNeed + self.nextLevelXP(lvl, 0)
        nextXp = self.nextLevelXP(lvl, xp-lastNeed)
        progress = round((xp / xpNeed) * 100, 2)
        pos = xp_service.get_ranking(handler, member.id, idGuild)

        embed = discord.Embed(
            title=f"{member}'s card",
            color=0x0089FF
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url=member.display_avatar)
        embed.add_field(name="", value="\n".join((
            f"`XP` : **{xp}**",
            f"`Level` : **{lvl}**",
            f"`Progress` : **{progress}%**"
        )))
        embed.add_field(name="", value="\n".join((
            f"`Next Level XP` : **{nextXp}**",
            f"`Total XP needed` : **{xpNeed}**",
            f"`Leaderboard` : **{'?' if pos is None else pos}**"
        )))
        await ctx.respond(embed=embed)


    @josix_slash(description="Block or unblock xp progression for a member")
    @discord.default_permissions(moderate_members=True)
    @commands.guild_only()
    @option(
        input_type=discord.Member,
        name="member",
        description="Mention of the targeted user",
        required=True
    )
    async def block_user_xp(self, ctx: ApplicationContext, member: discord.Member):
        await ctx.defer(ephemeral=False, invisible=False)
        if member.bot:
            await ctx.respond("You can't perform this action on a bot")
            return

        idTarget = member.id
        idGuild = ctx.guild_id
        handler = self.bot.get_handler()
        
        _, _, userGuildDB = discord_service.fetch_user_guild_relationship(handler, idTarget, idGuild)

        if not userGuildDB:
            await ctx.respond("Could not fetch data")
            return

        blocked = userGuildDB.isUserBlocked
        xp_service.switch_user_xp_blocking(handler, idTarget, idGuild)
        await ctx.respond(f"The block status for {member.mention} is set to **{not blocked}**")

    
    @josix_slash(description="See all past seasons in this server")
    @commands.guild_only()
    @option(
        input_type=int,
        name="limit",
        description="Limit number of seasons to display (default : 10) between [1, 25]",
        default=10,
        min_value=1,
        max_value=25
    )
    async def show_seasons(self, ctx: ApplicationContext, limit: int):
        await ctx.defer(ephemeral=False, invisible=False)
        guild = ctx.guild
        if not guild:
            await ctx.respond("Data not found")
            return

        seasons = season_service.get_seasons(self.bot.get_handler(), guild.id, limit)
        if not seasons:
            seasons = []

        embed = discord.Embed(
            title="Seasons",
            description=f"List of all seasons for server {guild.name}",
            color=0x0089FF
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url=ctx.author.display_avatar)
        
        content = ""
        newLine = ""
        lineLength = 0
        currentLength = 0
        nbField = 0
        for i, season in enumerate(seasons):
            newLine = f"- **{i+1}** : {season.label}\n"
            lineLength = len(newLine)
            if currentLength + lineLength >= 1024:
                embed.add_field(name="", value=content, inline=False)
                nbField += 1
                content = newLine
                currentLength = lineLength

                if nbField >= 25:
                    break
            
            else:
                content += newLine
                currentLength += lineLength
        
        if nbField < 25:
            embed.add_field(name="", value=content, inline=False)
        await ctx.respond(embed=embed)


    @josix_slash(description="See user history in all the seasons")
    @commands.guild_only()
    @option(
        input_type=discord.Member,
        name="member",
        description="Mention of the member you want to see the history",
        required=False
    )
    async def user_history(self, ctx: ApplicationContext, member: discord.Member):
        await ctx.defer(ephemeral=False, invisible=False)
        guild = ctx.guild
        if not guild:
            await ctx.respond("Data not found")
            return

        if not member:
            member = ctx.author

        if member.bot:
            await ctx.respond("This action can't be done on a bot user")
            return

        scores = season_service.get_user_history(self.bot.get_handler(), guild.id, member.id)
        embed = discord.Embed(
            title="Scores",
            description=f"Scores history from {member.name}",
            color=0x0089FF
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url=member.display_avatar)

        content = ""
        newLine = ""
        lineLength = 0
        currentLength = 0
        nbField = 0
        for score in scores:
            newLine = f"- **{score.label}** : {score.score} ({score.ranking})\n"
            lineLength = len(newLine)
            if currentLength + lineLength >= 1024:
                embed.add_field(name="", value=content, inline=False)
                nbField += 1
                content = newLine
                currentLength = lineLength

                if nbField >= 25:
                    break
            
            else:
                content += newLine
                currentLength += lineLength
        
        if nbField < 25:
            embed.add_field(name="", value=content, inline=False)
        await ctx.respond(embed=embed)


    @josix_slash(description="Display all the informations of a season")
    @commands.guild_only()
    @option(
        input_type=str,
        name="label",
        description="Label of the targeted season",
        required=True
    )
    async def info_season(self, ctx: ApplicationContext, label: str):
        await ctx.defer(ephemeral=False, invisible=False)

        handler = self.bot.get_handler()
        guild = ctx.guild
        if not guild:
            await ctx.respond("Data not found")
            return

        if not (season := season_service.get_season_by_label(handler, guild.id, label)):
            await ctx.respond("Unknown season, make sure you entered the right label")
            return

        scores = season_service.get_scores(handler, season.idSeason)
        embed = discord.Embed(
            title="Season information",
            color=0x0089FF
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url=guild.icon)
        embed.add_field(name="Label", value=season.label)
        embed.add_field(name="Ended at", value=season.ended_at.strftime("%d/%m/%Y %H:%M:%S"))

        res = ""
        if scores:
            medals = ["🥇", "🥈", ":third_place:"]
            for i, score in enumerate(scores):
                if i >= 3:
                    break

                try:
                    if not (member := guild.get_member(score.idUser)) and not (member := await guild.fetch_member(score.idUser)):
                        continue
                except discord.HTTPException:
                    continue
                res += f"{medals[i]} {member.name} (**{score.score}**)\n"
        
        else:
            res = "No data available for the ranking of this season"
        embed.add_field(name="Ranking", value=res, inline=False)
        await ctx.respond(embed=embed)

    
    @josix_slash(description="Show the profile of the user on a specific season")
    @commands.guild_only()
    @option(
        input_type=str,
        name="label",
        description="Label of the targeted season"
    )
    async def user_season_profile(self, ctx: ApplicationContext, label: str):
        await ctx.defer(ephemeral=False, invisible=False)

        handler = self.bot.get_handler()
        guild = ctx.guild
        if not guild:
            await ctx.respond("Data not found")
            return

        if not (season := season_service.get_season_by_label(handler, guild.id, label)):
            await ctx.respond("Unknown season, make sure you entered the right label")
            return

        score = season_service.get_user_score(handler, season.idSeason, ctx.author.id)
        if not score:
            await ctx.respond("No profile found in this season")
            return

        level = 0
        totalXP = self.nextLevelXP(level, 0)
        while totalXP < score.score:
            level += 1
            totalXP += self.nextLevelXP(level, 0)

        embed = discord.Embed(
            title=f"{ctx.author.name}'s Season Profile",
            color=0x0089FF
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url=guild.icon)
        embed.add_field(name="Label", value=season.label)
        embed.add_field(name="Score", value=score.score)
        embed.add_field(name="Ranking", value=score.ranking)
        embed.add_field(name="Level", value=str(level))
        await ctx.respond(embed=embed)


    @tasks.loop(seconds=1.0)
    async def check_temporary(self):
        handler = self.bot.get_handler()
        guilds = season_service.get_guilds_ended_temporary(handler)
        if not guilds:
            return

        for guild in guilds:
            try:
                season_service.stop_temporary_season(handler, guild.id)
                if not guild.xpNews:
                    continue

                if not (xpChan := self.bot.get_channel(guild.xpNews)) and not (xpChan := await self.bot.fetch_channel(guild.xpNews)):
                    continue

                await xpChan.send("The temporary season has ended ! Rolling back to the previous season")
            except Exception as e:
                log.writeError(log.formatError(e))
                continue


    @josix_slash(description="Toggle the ping on level up")
    async def toggle_ping(self, ctx: ApplicationContext):
        await ctx.defer(ephemeral=False, invisible=False)
        handler = self.bot.get_handler()

        user = discord_service.get_user(handler, ctx.author.id)
        if not user:
            user = discord_service.add_user(handler, ctx.author.id)
            if not user:
                await ctx.respond("Error on registration")
                return

        xp_service.toggle_ping_xp(handler, ctx.author.id)
        await ctx.respond(f"Ping on level up is now **{'enabled' if not user.pingUser else 'disabled'}**")


def setup(bot: Josix):
    bot.add_cog(XP(bot, True))