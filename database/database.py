import datetime as dt
import os
from shutil import copyfile
from typing import Any, Callable

import discord
import psycopg2
from dotenv import load_dotenv

import logwrite as log
from database.db_utils import *

SCRIPT_DIR = os.path.dirname(__file__)
BACKUP_PATH = os.path.join(SCRIPT_DIR, 'backup.sql')
DAILY_BACKUP_PATH = os.path.join(SCRIPT_DIR, 'daily_backup.sql')
OLD_PATH = os.path.join(SCRIPT_DIR, 'daily_backup.sql.old')
TABLE_ORDER_PATH = os.path.join(SCRIPT_DIR, 'table_order.sql')

class DatabaseHandler():
    """
    Represents an handler for the database.
    Allows to execute queries on the database
    """
    def __init__(self) -> None:
        load_dotenv(".env.dev")

        conn = psycopg2.connect(
            host=os.getenv("HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )

        log.writeLog(" - Connection on the database for Josix done")

        self.conn = conn
        self.cursor = conn.cursor()

    # TODO : Use it in another way
    def safeExecute(
        self,
        func: Callable[[Any], Any],
        *args
        ) -> Any:
        try:
            return func(*args)
        except Exception as e:
            log.writeError(log.formatError(e))


    def _error_handler(func: Callable):
        def wrapper(ref, *args):
            try:
                return func(ref, *args)
            except psycopg2.Error as dbError:
                ref: DatabaseHandler = ref
                ref.conn.rollback()
                raise dbError
            except Exception as commonError:
                raise commonError
        return wrapper


    def execute(self, query: str, raiseError: bool = False) -> str:
        if query.startswith("--") or query.startswith("\n") or len(query) == 0:
            return "Empty query"

        try:
            self.cursor.execute(query)
            self.conn.commit()

            try:
                return str(self.cursor.fetchall())
            except psycopg2.ProgrammingError as prgError:
                if raiseError:
                    raise prgError
                return "Query executed : nothing to fetch"

        except psycopg2.Error as commonError:
            self.conn.rollback()
            if raiseError:
                raise commonError
            return str(commonError)


    @_error_handler
    def backup(self, table: str, daily: bool = False) -> None:
        if table:
            query = f"SELECT table_name FROM information_schema.tables WHERE table_schema = 'josix' AND table_name = '{table}';"
        else:
            with open(TABLE_ORDER_PATH, 'r') as order_file:
                query = order_file.read()

        self.cursor.execute(query)
        res = self.cursor.fetchall()

        file = DAILY_BACKUP_PATH if daily else BACKUP_PATH
        if daily:
            copyfile(DAILY_BACKUP_PATH, OLD_PATH)

        with open(file, "w") as f:
            f.write("-- Last backup : " + str(dt.datetime.now()) + "\n")
            for rowTable in res[::-1]:
                f.write("DELETE FROM josix." + rowTable[0] + ";\n")
            for rowTable in res:
                table_name = rowTable[0]
                f.write("\n-- Records for table : josix." + table_name + "\n")

                self.cursor.execute("SELECT * FROM josix.%s" % (table_name))
                column_names = []
                columns_descr = self.cursor.description

                for c in columns_descr:
                    column_names.append(c[0])
                insert_prefix = 'INSERT INTO josix.%s (%s) VALUES ' % (table_name, ', '.join(column_names))
                rows = self.cursor.fetchall()

                for row in rows:
                    row_data = []
                    for rd in row:
                        if rd is None:
                            row_data.append('NULL')
                        elif isinstance(rd, dt.date):
                            row_data.append("'%s'" % (rd.strftime('%Y-%m-%d')))
                        elif isinstance(rd, dt.datetime):
                            row_data.append("'%s'" % (rd.strftime('%Y-%m-%d %H:%M:%S')))
                        elif isinstance(rd, str):
                            row_data.append("E'%s'" % (rd.replace("'", "\\'")))
                        elif isinstance(rd, list):
                            row_data.append("ARRAY%s::BIGINT[]" % (repr(rd)))
                        else:
                            row_data.append(repr(rd))
                    f.write('%s (%s);\n' % (insert_prefix, ', '.join(row_data)))


    ###############
    # Getters
    ###############


    @_error_handler
    def getXpLeaderboard(self, id_guild: int, limit: int | None) -> list[LinkUserGuild] | None:
        query = """SELECT * FROM josix.UserGuild
                   WHERE idGuild = %s
                   ORDER BY xp DESC
                   LIMIT %s"""
        params = (id_guild, limit)
        self.cursor.execute(query, params)
        res = self.cursor.fetchall()
        if res:
            return [LinkUserGuild(*row) for row in res]


    @_error_handler
    def getLeaderboardPos(self, id_user: int, id_guild: int) -> int | None:
        query = """SELECT COUNT(DISTINCT idUser) + 1
                   FROM josix.UserGuild
                   WHERE idGuild = %s AND
                         xp > (SELECT xp FROM josix.UserGuild WHERE idUser = %s AND idGuild = %s);"""
        params = (id_guild, id_user, id_guild)
        self.cursor.execute(query, params)
        res = self.cursor.fetchone()
        if res:
            return res[0]


    def getNewSeasonID(self, id_guild: int) -> int:
        query = "SELECT COUNT(idSeason) FROM josix.Season WHERE idGuild = %s;"
        self.cursor.execute(query, (id_guild,))
        res = self.cursor.fetchone()
        newLabelID = 1 if not res else res[0]+1

        if self.getSeasonByLabel(id_guild, str(newLabelID)):
            raise ValueError(f"The label '{newLabelID}' is already used in a season for this server")
        return newLabelID


    def getSeason(self, id_season: int) -> Season | None:
        query = "SELECT * FROM josix.Season WHERE idSeason = %s;"
        self.cursor.execute(query, (id_season,))
        res = self.cursor.fetchone()
        if res:
            return Season(*res)


    def getSeasonByLabel(self, id_guild: int, label: str) -> Season | None:
        query = "SELECT * FROM josix.Season WHERE idGuild = %s AND LOWER(label) = LOWER(%s);"
        params = (id_guild, label)
        self.cursor.execute(query, params)
        res = self.cursor.fetchone()
        if res:
            return Season(*res)


    def getSeasons(self, id_guild: int, limit: int) -> list[Season] | None:
        query = "SELECT * FROM josix.Season WHERE idGuild = %s ORDER BY idSeason DESC LIMIT %s;"
        params = (id_guild, limit)
        self.cursor.execute(query, params)
        res = self.cursor.fetchall()

        if res:
            return [Season(*row) for row in res]


    def getUserHistory(self, id_guild: int, id_user: int) -> list[UserScore] | None:
        query = """
                SELECT sc.idUser, sc.idSeason, sc.score, sc.ranking, se.label
                FROM josix.Score sc INNER JOIN josix.Season se ON sc.idSeason = se.idSeason
                WHERE sc.idUser = %s AND se.idGuild = %s ORDER BY sc.idSeason DESC;
                """
        params = (id_user, id_guild)
        self.cursor.execute(query, params)
        res = self.cursor.fetchall()

        if res:
            return [UserScore(*score) for score in res]


    def getScores(self, id_season: int) -> list[Score] | None:
        query = """SELECT * FROM josix.Score WHERE idSeason = %s ORDER BY ranking;"""
        self.cursor.execute(query, (id_season,))
        res = self.cursor.fetchall()
        
        if res:
            return [Score(*score) for score in res]


    def getUserScore(self, id_season: int, id_user: int) -> Score | None:
        query = "SELECT * FROM josix.Score WHERE idSeason = %s AND idUser = %s;"
        params = (id_season, id_user)
        self.cursor.execute(query, params)
        res = self.cursor.fetchone()

        if res:
            return Score(*res)


    ###############
    # Adders
    ###############


    @_error_handler
    def storeSeason(self, id_guild: int, label: str) -> int:
        if label == "":
            label = str(self.getNewSeasonID(id_guild))
        else:
            if self.getSeasonByLabel(id_guild, str(label)):
                raise ValueError(f"The label '{label}' is already used in a season for this server")

        query = "INSERT INTO josix.Season(idGuild, label) VALUES(%s, LOWER(%s)) RETURNING idSeason;"
        params = (id_guild, label)
        self.cursor.execute(query, params)
        self.conn.commit()
        
        res = self.cursor.fetchone()
        if res:
            return res[0]


    @_error_handler
    def storeScores(self, id_guild: int, id_season: int):
        scores = self.getXpLeaderboard(id_guild, None)
        if not scores:
            return
        
        season = self.getSeason(id_season)
        if not season:
            return

        for i, score in enumerate(scores):
            query = "INSERT INTO josix.Score VALUES(%s, %s, %s, %s);"
            params = (score.idUser, season.idSeason, score.xp, i+1)
            self.cursor.execute(query, params)
        self.conn.commit()


    ###############
    # Modifiers
    ###############


    @_error_handler
    def updateUserXP(self, id_user: int, id_guild: int, lvl: int, xp: int, last_send: dt.datetime) -> None:
        query = """UPDATE josix.UserGuild
                   SET lvl = %s,
                       xp = %s,
                       lastMessage = %s
                    WHERE idUser = %s AND idGuild = %s;"""
        params = (lvl, xp, last_send, id_user, id_guild)
        self.cursor.execute(query, params)
        self.conn.commit()

    @_error_handler
    def changeXPChan(self, id_guild: int, id_chan: int) -> None:
        query = """UPDATE josix.Guild
                   SET xpNews = %s
                   WHERE idGuild = %s;"""
        params = (id_chan, id_guild)
        self.cursor.execute(query, params)
        self.conn.commit()

    @_error_handler
    def updateGuildXpEnabled(self, id_guild: int) -> None:
        query = """UPDATE josix.Guild
                   SET enableXP = NOT enableXP
                   WHERE idGuild = %s"""
        self.cursor.execute(query, (id_guild,))
        self.conn.commit()

    @_error_handler
    def updateUserBlock(self, id_user: int, id_guild: int) -> None:
        query = """UPDATE josix.UserGuild
                   SET xpBlocked = NOT xpBlocked
                   WHERE idUser = %s AND idGuild = %s;"""
        params = (id_user, id_guild)
        self.cursor.execute(query, params)
        self.conn.commit()

    @_error_handler
    def blockCategory(self, id_category: int, id_guild: int) -> None:
        query = """UPDATE josix.Guild
                   SET blockedCategories = ARRAY_APPEND(blockedCategories, %s)
                   WHERE idGuild = %s;"""
        params = (id_category, id_guild)
        self.cursor.execute(query, params)
        self.conn.commit()

    @_error_handler
    def unblockCategory(self, id_category: int, id_guild: int) -> None:
        query = """UPDATE josix.Guild
                   SET blockedCategories = ARRAY_REMOVE(blockedCategories, %s)
                   WHERE idGuild = %s;"""
        params = (id_category, id_guild)
        self.cursor.execute(query, params)
        self.conn.commit()

    @_error_handler
    def updateWelcomeGuild(self, id_guild: int, id_chan: int | None, id_role: int | None, message: str) -> None:
        if not id_chan:
            id_chan = 0
        if not id_role:
            id_role = 0

        query = """UPDATE josix.Guild
                   SET enableWelcome = TRUE,
                       welcomeChan = %s,
                       welcomeRole = %s,
                       welcomeText = %s
                   WHERE idGuild = %s;"""
        params = (id_chan, id_role, message, id_guild)
        self.cursor.execute(query, params)
        self.conn.commit()

    @_error_handler
    def updateGuildWelcomeEnabled(self, id_guild: int) -> None:
        query = """UPDATE josix.Guild
                   SET enableWelcome = NOT enableWelcome
                   WHERE idGuild = %s"""
        self.cursor.execute(query, (id_guild,))
        self.conn.commit()


    @_error_handler
    def updateSeasonLabel(self, season: Season, new_label: str) -> None:
        query = "UPDATE josix.Season SET label = %s WHERE idSeason = %s;"
        params = (new_label, season.idSeason)
        self.cursor.execute(query, params)
        self.conn.commit()


    ###############
    # Deleters
    ###############


    @_error_handler
    def cleanXPGuild(self, id_guild: int) -> None:
        query = "DELETE FROM josix.UserGuild WHERE idGuild = %s;"
        self.cursor.execute(query, (id_guild,))
        self.conn.commit()


    @_error_handler
    def deleteSeason(self, season: Season) -> None:
        query = "DELETE FROM josix.Score WHERE idSeason = %s;"
        query2 = "DELETE FROM josix.Season WHERE idSeason = %s;"
        self.cursor.execute(query, (season.idSeason,))
        self.cursor.execute(query2, (season.idSeason,))
        self.conn.commit()
