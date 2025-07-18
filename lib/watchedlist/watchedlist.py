"""
This file contains the class of the addon

Settings for this addon:
w_movies
    'true', 'false': save watched state of movies
w_episodes
    'true', 'false': save watched state of movies
autostart
delay
    delay after startup in minutes: '0', '5', '10', ...
starttype
    '0' = No autostart
    '1' = One Execution after Kodi start
    '2' = Periodic start of the addon
interval
watch_user
progressdialog
verbosity
    '0' = All messages (debug)
    '1' = Only info / notification
    '2' = Only warnings
    '3' = Only errors
    '4' = No Messages
db_format
    '0' = SQLite File
    '1' = MYSQL Server
drobox_enabled
extdb
    'true', 'false': Use external database file
dbpath
    String: Specify path to external database file
dbfilename
dbbackupcount
mysql_server
mysql_port
mysql_db
mysql_user
mysql_pass
"""

import sys
import os
import re
import time
import sqlite3
import base64

import xbmc
import xbmcgui
import xbmcvfs
import mysql.connector
import buggalo

import lib.watchedlist.utils as utils

try:
    import dropbox
    from dropbox.exceptions import ApiError as DropboxApiError
    DROPBOX_APP_KEY = base64.b64decode("YmhkMnY4aGdzbXF3Y2d0").decode('ascii')
    DROPBOX_APP_SECRET = base64.b64decode("dDJjZXBvZXZqcXl1Ym5k").decode('ascii')
    DROPBOX_ENABLED = True
except BaseException:
    DROPBOX_ENABLED = False
    if utils.getSetting("dropbox_enabled") == 'true':
        utils.showNotification(utils.getString(32708), utils.getString(32720), xbmc.LOGWARNING)

if utils.getSetting('dbbackupcount') != '0':
    import zipfile
    import datetime

buggalo.EMAIL_CONFIG = {"recipient": base64.b64decode("bXNhaGFkbDYwQGdtYWlsLmNvbQ==").decode('ascii'),
                        "sender": base64.b64decode("QnVnZ2FsbyA8a29kaXdhdGNoZWRsaXN0QGdtYWlsLmNvbT4=").decode('ascii'),
                        "server": base64.b64decode("c210cC5nb29nbGVtYWlsLmNvbQ==").decode('ascii'),
                        "method": "ssl",
                        "user": base64.b64decode("a29kaXdhdGNoZWRsaXN0QGdtYWlsLmNvbQ==").decode('ascii'),
                        "pass": base64.b64decode("bWNneHd1and6c3ducW1iaA==").decode('ascii')}

QUERY_MV_INSERT_SQLITE = 'INSERT OR IGNORE INTO movie_watched (idMovieImdb,playCount,lastChange,lastPlayed,title,userrating) VALUES (?, ?, ?, ?, ?, ?)'#5
QUERY_MV_INSERT_MYSQL = 'INSERT IGNORE INTO movie_watched (idMovieImdb,playCount,lastChange,lastPlayed,title,userrating) VALUES (%s, %s, FROM_UNIXTIME(%s), FROM_UNIXTIME(%s), %s, %s)'#5
QUERY_EP_INSERT_SQLITE = 'INSERT OR IGNORE INTO episode_watched (idShow,season,episode,playCount,lastChange,lastPlayed,userrating) VALUES (?, ?, ?, ?, ?, ?, ?)'#6
QUERY_EP_INSERT_MYSQL = 'INSERT IGNORE INTO episode_watched (idShow,season,episode,playCount,lastChange,lastPlayed,userrating) VALUES (%s, %s, %s, %s, FROM_UNIXTIME(%s), FROM_UNIXTIME(%s), %s)'#6

QUERY_MV_UPDATE_SQLITE = 'UPDATE movie_watched SET playCount = ?, lastplayed = ?, lastChange = ?, userrating = ? WHERE idMovieImdb LIKE ?'#3
QUERY_MV_UPDATE_MYSQL = 'UPDATE movie_watched SET playCount = %s, lastplayed = FROM_UNIXTIME(%s), lastChange = FROM_UNIXTIME(%s), userrating = %s WHERE idMovieImdb LIKE %s'#3
QUERY_EP_UPDATE_SQLITE = 'UPDATE episode_watched SET playCount = ?, lastPlayed = ?, lastChange = ?, userrating = ? WHERE idShow LIKE ? AND season LIKE ? AND episode LIKE ?'#3
QUERY_EP_UPDATE_MYSQL = 'UPDATE episode_watched SET playCount = %s, lastPlayed = FROM_UNIXTIME(%s), lastChange = FROM_UNIXTIME(%s), userrating = %s WHERE idShow LIKE %s AND season LIKE %s AND episode LIKE %s'#3

# Queries to create tables for movies ("mv"), episodes ("ep") and series ("ss") for sqlite and mysql
QUERY_CREATE_MV_SQLITE = "CREATE TABLE IF NOT EXISTS movie_watched (idMovieImdb INTEGER PRIMARY KEY,playCount INTEGER,lastChange INTEGER,lastPlayed INTEGER,title TEXT,userrating INTEGER)"
QUERY_CREATE_EP_SQLITE = "CREATE TABLE IF NOT EXISTS episode_watched (idShow INTEGER, season INTEGER, episode INTEGER, playCount INTEGER,lastChange INTEGER,lastPlayed INTEGER,userrating INTEGER, PRIMARY KEY (idShow, season, episode))"
QUERY_CREATE_SS_SQLITE = "CREATE TABLE IF NOT EXISTS tvshows (idShow INTEGER, title TEXT, userrating INTEGER, PRIMARY KEY (idShow))"

QUERY_CREATE_MV_MYSQL = ("CREATE TABLE IF NOT EXISTS `movie_watched` ("
                         "`idMovieImdb` int unsigned NOT NULL,"
                         "`playCount` tinyint unsigned DEFAULT NULL,"
                         "`lastChange` datetime NULL DEFAULT NULL,"
                         "`lastPlayed` datetime NULL DEFAULT NULL,"
                         "`title` mediumtext,"
                         "`userrating` tinyint unsigned DEFAULT NULL,"
                         "PRIMARY KEY (`idMovieImdb`)"
                         ") ENGINE=InnoDB DEFAULT CHARSET=utf8;")
QUERY_CREATE_EP_MYSQL = ("CREATE TABLE IF NOT EXISTS `episode_watched` ("
                         "`idShow` int unsigned NOT NULL DEFAULT '0',"
                         "`season` smallint unsigned NOT NULL DEFAULT '0',"
                         "`episode` smallint unsigned NOT NULL DEFAULT '0',"
                         "`playCount` tinyint unsigned DEFAULT NULL,"
                         "`lastChange` datetime NULL DEFAULT NULL,"
                         "`lastPlayed` datetime NULL DEFAULT NULL,"
                         "`userrating` tinyint unsigned DEFAULT NULL,"
                         "PRIMARY KEY (`idShow`,`season`,`episode`)"
                         ") ENGINE=InnoDB DEFAULT CHARSET=utf8;")
QUERY_CREATE_SS_MYSQL = ("CREATE TABLE IF NOT EXISTS `tvshows` ("
                         "`idShow` int unsigned NOT NULL,"
                         "`title` mediumtext,"
                         "`userrating` tinyint unsigned DEFAULT NULL,"
                         "PRIMARY KEY (`idShow`)"
                         ") ENGINE=InnoDB DEFAULT CHARSET=utf8;")

# Queries for clearing data from the tables
QUERY_CLEAR_MV_SQLITE = "DELETE FROM movie_watched;"
QUERY_CLEAR_EP_SQLITE = "DELETE FROM episode_watched;"

# Queries for selecting all table entries
QUERY_SELECT_MV_SQLITE = "SELECT idMovieImdb, lastPlayed, playCount, title, lastChange, userrating FROM movie_watched ORDER BY title"#5
QUERY_SELECT_MV_MYSQL = "SELECT `idMovieImdb`, UNIX_TIMESTAMP(`lastPlayed`), `playCount`, `title`, UNIX_TIMESTAMP(`lastChange`), `userrating` FROM `movie_watched` ORDER BY `title`"#5
QUERY_SELECT_EP_SQLITE = "SELECT idShow, season, episode, lastPlayed, playCount, lastChange, userrating FROM episode_watched ORDER BY idShow, season, episode"#6
QUERY_SELECT_EP_MYSQL = "SELECT `idShow`, `season`, `episode`, UNIX_TIMESTAMP(`lastPlayed`), `playCount`, UNIX_TIMESTAMP(`lastChange`), `userrating` FROM `episode_watched` ORDER BY `idShow`, `season`, `episode`"#6

# Queries for inserting tv series
QUERY_INSERT_SS_SQLITE = "INSERT OR IGNORE INTO tvshows (idShow,title,userrating) VALUES (?, ?, ?)"
QUERY_INSERT_SS_MYSQL = "INSERT IGNORE INTO tvshows (idShow,title,userrating) VALUES (%s, %s, %s)"


class WatchedList:
    """
    Main class of the add-on
    """

    def __init__(self, externalcall=False):
        """
        Initialize Class, default values for all class variables

        Args:
        externalcall: Flag if the class was created for use with another Addon (via the API).
        In this case some features will be deactivated for speed purpose
        """
        self.watchedmovielist_wl = list([])  # 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6lastChange #7
        self.watchedepisodelist_wl = list([])  # 0tvdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5empty, 6lastChange #7

        self.watchedmovielist_xbmc = list([])  # 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6empty, 7movieid #8
        self.watchedepisodelist_xbmc = list([])  # 0tvdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5name, 6empty, 7episodeid #8

        self.tvshows = {}  # dict: key=xbmcid, value=[tvdbnumber, showname]
        self.tvshownames = {}  # dict: key=tvdbnumber, value=showname

        self.sqlcon_wl = 0
        self.sqlcursor_wl = 0
        self.sqlcon_db = 0
        self.sqlcursor_db = 0

        self.db_method = 'file'  # either 'file' or 'mysql'

        # flag to remember copying the databasefile if requested
        self.dbbackupdone = False

        self.watch_user_changes_count = 0

        # normal access of files or access over the Kodi virtual file system (on unix)
        self.dbfileaccess = 'normal'

        self.dbpath = ''
        self.dbdirectory = ''
        self.dropbox_path = None
        self.downloaded_dropbox_timestamp = 0
        self.dbdirectory_copy = ''
        self.dbpath_copy = ''

        # monitor for shutdown detection
        self.monitor = xbmc.Monitor()

        if externalcall:
            # No Dropbox for external API calls
            self.downloaded_dropbox_timestamp = float('inf')
            # No database backup
            self.dbbackupdone = True

    def __del__(self):
        ''' Cleanup db when object destroyed '''
        self.close_db(3)  # changes have to be committed before

    def __enter__(self):  # for using the class in a with-statement
        return self

    def __exit__(self, exc_type, exc_value, traceback):  # for using the class in a with-statement
        self.close_db(3)  # changes have to be committed before

    def runProgram(self):
        """
        entry point for automatic start.
        Main function to call other functions
        infinite loop for periodic database update

        Returns:
            return codes:
            0    success
            2    undefined
            3    error/exit
            4    planned exit (no error)
        """
        try:
            # workaround to disable autostart, if requested
            if utils.getSetting("autostart") == 'false':
                return 0

            utils.buggalo_extradata_settings()
            utils.footprint()

            # wait the delay time after startup
            delaytime = int(utils.getSetting("delay")) * 60  # in seconds
            utils.log(u'Delay time before execution: %d seconds' % delaytime, xbmc.LOGDEBUG)
            utils.showNotification(utils.getString(32101), utils.getString(32004) % int(utils.getSetting("delay")), xbmc.LOGINFO)
            if self.monitor.waitForAbort(1 + delaytime):  # wait at least one second (zero waiting time waits infinitely)
                return 0

            # load all databases
            if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
                if self.load_db():
                    utils.showNotification(utils.getString(32102), utils.getString(32601), xbmc.LOGERROR)
                    return 3
            if not self.tvshownames:
                if self.sync_tvshows():
                    return 2
            if not self.watchedmovielist_wl:
                if self.get_watched_wl(1):
                    return 2
            if not self.watchedmovielist_xbmc:
                if self.get_watched_xbmc(1):
                    return 2
            executioncount = 0
            idletime = 0

            if utils.getSetting("watch_user") == 'true':
                utils.showNotification(utils.getString(32101), utils.getString(32005), xbmc.LOGINFO)

            # handle the periodic execution
            while int(utils.getSetting("starttype")) > 0 or utils.getSetting("watch_user") == 'true':
                starttime = time.time()
                # determine sleeptime before next full watched-database update
                if utils.getSetting("starttype") == '1' and executioncount == 0:  # one execution after startup
                    sleeptime = 0
                elif utils.getSetting("starttype") == '2':  # periodic execution
                    if executioncount == 0:  # with periodic execution, one update after startup and then periodic
                        sleeptime = 0
                    else:
                        sleeptime = int(utils.getSetting("interval")) * 3600  # wait interval until next startup in [seconds]
                        # wait and then update again
                        utils.log(u'wait %d seconds until next update' % sleeptime)
                        utils.showNotification(utils.getString(32101), utils.getString(32003) % (sleeptime / 3600), xbmc.LOGINFO)
                else:  # no autostart, only watch user
                    sleeptime = 3600  # arbitrary time for infinite loop

                # sleep the requested time and watch user changes
                while True:
                    if self.monitor.abortRequested():
                        return 4
                    # check if user changes arrived
                    if utils.getSetting("watch_user") == 'true':
                        idletime_old = idletime
                        idletime = xbmc.getGlobalIdleTime()  # Kodi idletime in seconds
                        # check if user could have made changes and process these changes to the wl database
                        self.watch_user_changes(idletime_old, idletime)
                    # check if time for update arrived
                    if time.time() > starttime + sleeptime:
                        break
                    if self.monitor.waitForAbort(1):
                        return 4  # wait 1 second until next check if Kodi terminates and user made changes
                # perform full update
                if utils.getSetting("starttype") == '1' and executioncount == 0 or utils.getSetting("starttype") == '2':
                    self.runUpdate(False)
                    executioncount += 1

                # check for exiting program
                if int(utils.getSetting("starttype")) < 2 and utils.getSetting("watch_user") == 'false':
                    return 0  # the program may exit. No purpose for background process

            return 0
        except SystemExit:
            return 4
        except BaseException:
            buggalo.onExceptionRaised()

    def runUpdate(self, manualstart):
        """
        entry point for manual start.
        this function is called for periodic update for automatic start
        perform the update step by step

        Args:
            manualstart: True if called manually

        Returns:
            return code:
            0    success
            2    SystemExit
            3    Error opening database
            4    Error getting watched state from addon database
            5    Error getting watched state from Kodi database
            6    Error writing WL Database
            7    Error writing Kodi database
            8    Error merging dropbox database into local watched list
            9    Error merging local database into dropbox
            10   Error performing database backup
        """

        try:
            utils.buggalo_extradata_settings()
            # check if player is running before doing the update. Only do this check for automatic start
            while xbmc.Player().isPlaying() and not manualstart:
                if self.monitor.waitForAbort(60):
                    return 1  # wait one minute until next check for active playback
                if not xbmc.Player().isPlaying():
                    if self.monitor.waitForAbort(180):
                        return 1  # wait 3 minutes so the dialogue does not pop up directly after the playback ends

            # load the addon-database
            if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
                if self.load_db(True):  # True: Manual start
                    utils.showNotification(utils.getString(32102), utils.getString(32601), xbmc.LOGERROR)
                    return 3

            if self.sync_tvshows():
                utils.showNotification(utils.getString(32102), utils.getString(32604), xbmc.LOGERROR)
                return 5

            # get the watched state from the addon
            if self.get_watched_wl(0):
                utils.showNotification(utils.getString(32102), utils.getString(32602), xbmc.LOGERROR)
                return 4

            # get watched state from xbmc
            if self.get_watched_xbmc(0):
                utils.showNotification(utils.getString(32102), utils.getString(32603), xbmc.LOGERROR)
                return 5

            if self.sync_tvshows():
                utils.showNotification(utils.getString(32102), utils.getString(32604), xbmc.LOGERROR)
                return 5

            # attempt to merge the database from dropbox
            if DROPBOX_ENABLED and utils.getSetting("dropbox_enabled") == 'true' and self.merge_dropbox_local():
                utils.showNotification(utils.getString(32102), utils.getString(32607), xbmc.LOGERROR)
                # do not abort execution of the whole addon if dropbox fails (e.g. due to network issues)
                # return 8

            # import from Kodi into addon database
            res = self.write_wl_wdata()
            if res == 2:  # user exit
                return 0
            elif res == 1:  # error
                utils.showNotification(utils.getString(32102), utils.getString(32604), xbmc.LOGERROR)
                return 6

            # export from addon database into Kodi database
            res = self.write_xbmc_wdata((utils.getSetting("progressdialog") == 'true'), 2)
            if res == 2:  # user exit
                return 0
            elif res == 1:  # error
                utils.showNotification(utils.getString(32102), utils.getString(32605), xbmc.LOGERROR)
                return 7

            utils.showNotification(utils.getString(32101), utils.getString(32107), xbmc.LOGINFO)
            utils.log(u'runUpdate exited with success', xbmc.LOGDEBUG)

            # sync with dropbox
            if DROPBOX_ENABLED and utils.getSetting("dropbox_enabled") == 'true':
                if self.merge_local_dropbox() == 0:
                    self.close_db(2)  # save the database to file.
                    self.pushToDropbox()
                else:
                    return 9

            # close the watchedlist database. Is only closed locally in case of error
            self.close_db(1)

            # delete old backup files of the database
            # do this at the end for not destroying valuable backup in case something went wrong before
            if self.database_backup_delete():
                return 10
            return 0
        except SystemExit:
            return 2
        except BaseException:
            buggalo.onExceptionRaised()

    def load_db(self, manualstart=False):
        """Load WL database

        Args:
            manualstart: True if called manually; only retry opening db once

        Returns:
            return code:
            0    successfully opened database
            1    error
            2    shutdown (serious error in subfunction)
        """

        try:
            if int(utils.getSetting("db_format")) != 1:
                # SQlite3 database in a file
                # load the db path
                if utils.getSetting("extdb") == 'false':
                    # use the default file
                    self.dbdirectory = xbmcvfs.translatePath(utils.data_dir())
                    buggalo.addExtraData('dbdirectory', self.dbdirectory)
                    self.dbpath = os.path.join(self.dbdirectory, "watchedlist.db")
                else:
                    wait_minutes = 1  # retry waittime if db path does not exist/ is offline

                    while not self.monitor.abortRequested():
                        # use a user specified file, for example to synchronize multiple clients
                        self.dbdirectory = xbmcvfs.translatePath(utils.getSetting("dbpath"))
                        self.dbfileaccess = utils.fileaccessmode(self.dbdirectory)
                        self.dbpath = os.path.join(self.dbdirectory, utils.getSetting("dbfilename"))

                        if not xbmcvfs.exists(self.dbdirectory):  # do not use os.path.exists to access smb:// paths
                            if manualstart:
                                utils.log(u'db path does not exist: %s' % self.dbdirectory, xbmc.LOGWARNING)
                                return 1  # raise error on manual start if directory not accessible (we do not want to wait in that case)
                            else:
                                utils.log(u'db path does not exist, wait %d minutes: %s' % (wait_minutes, self.dbdirectory), xbmc.LOGWARNING)

                            utils.showNotification(utils.getString(32102), utils.getString(32002) % self.dbdirectory, xbmc.LOGWARNING)
                            # Wait "wait_minutes" minutes until next check for file path (necessary on network shares, that are offline)
                            wait_minutes += wait_minutes  # increase waittime until next check
                            if self.monitor.waitForAbort(wait_minutes * 60):
                                return 2
                        else:
                            break  # directory exists, continue below

                # on unix, smb-shares can not be accessed with sqlite3 --> copy the db with Kodi file system operations and work in mirror directory
                buggalo.addExtraData('dbfileaccess', self.dbfileaccess)
                buggalo.addExtraData('dbdirectory', self.dbdirectory)
                buggalo.addExtraData('dbpath', self.dbpath)
                if self.dbfileaccess == 'copy':
                    self.dbdirectory_copy = self.dbdirectory
                    self.dbpath_copy = self.dbpath  # path to db file as in the settings (but not accessable)
                    buggalo.addExtraData('dbdirectory_copy', self.dbdirectory_copy)
                    buggalo.addExtraData('dbpath_copy', self.dbpath_copy)
                    # work in copy directory in the Kodi profile folder
                    self.dbdirectory = os.path.join(xbmcvfs.translatePath(utils.data_dir()), 'dbcopy' + os.sep)
                    if not xbmcvfs.exists(self.dbdirectory):  # directory has to end with '/' (os.sep)
                        xbmcvfs.mkdir(self.dbdirectory)
                        utils.log(u'created directory %s' % str(self.dbdirectory))
                    self.dbpath = os.path.join(self.dbdirectory, "watchedlist.db")
                    if xbmcvfs.exists(self.dbpath_copy):
                        success = xbmcvfs.copy(self.dbpath_copy, self.dbpath)  # copy the external db file to local mirror directory
                        utils.log(u'copied db file from share: %s -> %s. Success: %d' % (self.dbpath_copy, self.dbpath, success), xbmc.LOGDEBUG)

                buggalo.addExtraData('dbdirectory', self.dbdirectory)
                buggalo.addExtraData('dbpath', self.dbpath)

                # connect to the local wl database. create database if it does not exist
                self.sqlcon_wl = sqlite3.connect(self.dbpath)
                self.sqlcursor_wl = self.sqlcon_wl.cursor()
            else:
                # MySQL Database on a server
                self.sqlcon_wl = mysql.connector.connect(user=utils.getSetting("mysql_user"), password=utils.getSetting("mysql_pass"), database=utils.getSetting("mysql_db"), host=utils.getSetting("mysql_server"), port=utils.getSetting("mysql_port"))
                self.sqlcursor_wl = self.sqlcon_wl.cursor()

            # create tables if they don't exist
            if int(utils.getSetting("db_format")) != 1:  # sqlite file
                self.sqlcursor_wl.execute(QUERY_CREATE_MV_SQLITE)
                self.sqlcursor_wl.execute(QUERY_CREATE_EP_SQLITE)
                self.sqlcursor_wl.execute(QUERY_CREATE_SS_SQLITE)
            else:  # mysql network database
                self.sqlcursor_wl.execute(QUERY_CREATE_MV_MYSQL)
                self.sqlcursor_wl.execute(QUERY_CREATE_EP_MYSQL)
                self.sqlcursor_wl.execute(QUERY_CREATE_SS_MYSQL)

            # check for dropbox
            if DROPBOX_ENABLED and utils.getSetting("dropbox_enabled") == 'true':
                # Download Dropbox database only once a day to reduce traffic.
                if time.time() > self.downloaded_dropbox_timestamp + 3600.0 * 24.0:
                    if self.pullFromDropbox():
                        return 1
                    self.downloaded_dropbox_timestamp = time.time()
                # connect to the dropbox wl database.
                if self.dropbox_path is not None:
                    self.sqlcon_db = sqlite3.connect(self.dropbox_path)
                    self.sqlcursor_db = self.sqlcon_db.cursor()
                    # create tables in dropbox file, if they don't exist
                    self.sqlcursor_db.execute(QUERY_CREATE_MV_SQLITE)
                    self.sqlcursor_db.execute(QUERY_CREATE_EP_SQLITE)
                    self.sqlcursor_db.execute(QUERY_CREATE_SS_SQLITE)

            buggalo.addExtraData('db_connstatus', 'connected')
        except sqlite3.Error as err:
            try:
                errstring = err.args[0]  # TODO: Find out, why this does not work some times
            except BaseException:
                errstring = ''
            utils.log(u"Database error while opening %s. '%s'" % (self.dbpath, errstring), xbmc.LOGERROR)
            utils.showNotification(utils.getString(32109), errstring, xbmc.LOGERROR)
            self.close_db(3)
            buggalo.addExtraData('db_connstatus', 'sqlite3 error, closed')
            return 1
        except mysql.connector.Error as err:
            # Catch common mysql errors and show them to guide the user
            utils.log(u"Database error while opening mySQL DB %s [%s:%s@%s]. %s" % (utils.getSetting("mysql_db"), utils.getSetting("mysql_user"), utils.getSetting("mysql_pass"), utils.getSetting("mysql_db"), err.msg), xbmc.LOGERROR)
            if err.errno == mysql.connector.errorcode.ER_DBACCESS_DENIED_ERROR:
                utils.showNotification(utils.getString(32108), utils.getString(32210) % (utils.getSetting("mysql_user"), utils.getSetting("mysql_db")), xbmc.LOGERROR)
            elif err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
                utils.showNotification(utils.getString(32108), utils.getString(32208), xbmc.LOGERROR)
            elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
                utils.showNotification(utils.getString(32108), utils.getString(32209) % utils.getSetting("mysql_db"), xbmc.LOGERROR)
            else:
                utils.showNotification(utils.getString(32108), err.msg, xbmc.LOGERROR)
            buggalo.addExtraData('db_connstatus', 'mysql error, closed')
            self.close_db(3)
            return 1
        except SystemExit:
            return 1
        except BaseException:
            utils.log(u"Error while opening %s: %s" % (self.dbpath, sys.exc_info()[2]), xbmc.LOGERROR)
            self.close_db(3)
            buggalo.addExtraData('dbpath', self.dbpath)
            buggalo.addExtraData('db_connstatus', 'error, closed')
            buggalo.onExceptionRaised()
            return 1
        # only commit the changes if no error occured to ensure database persistence
        self.sqlcon_wl.commit()
        return 0

    def close_db(self, flag):
        """Close WL database
        Argument:
            flag
            1 for closing the WatchedList database
            2 for closing the DropBox database
            3 for closing both

        Returns:
            return code:
            0    successfully closed database
            1    error
        """
        # close watchedlist db (if it is open)
        if self.sqlcon_wl and (flag == 1 or flag == 3):
            if self.sqlcon_wl:
                self.sqlcon_wl.close()
                self.sqlcon_wl = 0
            # copy the db file back to the shared directory, if needed
            if utils.getSetting("db_format") == '0' and self.dbfileaccess == 'copy':
                if xbmcvfs.exists(self.dbpath):
                    success = xbmcvfs.copy(self.dbpath, self.dbpath_copy)
                    utils.log(u'copied db file to share: %s -> %s. Success: %d' % (self.dbpath, self.dbpath_copy, success), xbmc.LOGDEBUG)
                    if not success:
                        utils.showNotification(utils.getString(32102), utils.getString(32606) % self.dbpath, xbmc.LOGERROR)
                        return 1
            buggalo.addExtraData('db_connstatus', 'closed')
        # close dropbox db
        if flag == 2 or flag == 3:
            if self.sqlcon_db:
                self.sqlcon_db.close()
            self.sqlcon_db = 0
        return 0

    def get_watched_xbmc(self, silent):
        """Get Watched States of Kodi Database

        Args:
            silent: Do not show notifications if True

        Returns:
            return code:
            0    success
            1    error
            4    planned exit (no error)
        """
        try:

            ############################################
            # first tv shows with TheTVDB-ID, then tv episodes
            if utils.getSetting("w_episodes") == 'true':
                ############################################
                # get imdb tv-show id from Kodi database
                utils.log(u'get_watched_xbmc: Get all TV shows from Kodi database', xbmc.LOGDEBUG)
                json_response = utils.executeJSON({
                    "jsonrpc": "2.0",
                    "method": "VideoLibrary.GetTVShows",
                    "params": {
                        "properties": ["title", "uniqueid", "userrating"],
                        "sort": {"order": "ascending", "method": "title"}
                    },
                    "id": 1})
                if 'result' in json_response and json_response['result'] is not None and 'tvshows' in json_response['result']:
                    for item in json_response['result']['tvshows']:
                        if self.monitor.abortRequested():
                            self.close_db(3)
                            return 4
                        tvshowId_xbmc = int(item['tvshowid'])
                        if not 'uniqueid' in item:
                            utils.log(u'get_watched_xbmc: tv show "%s" has no field uniqueid in database. tvshowid=%d. Try rescraping.' % (item['title'], tvshowId_xbmc), xbmc.LOGINFO)
                            continue
                        try:
                            tvshowId_tvdb = int(item['uniqueid']['tvdb'])
                        except BaseException:
                            utils.log(u'get_watched_xbmc: tv show "%s" has no tvdb-number in database. tvshowid=%d. Unique IDs: %s. Try rescraping.' % (item['title'], tvshowId_xbmc, str(list(item['uniqueid'].keys()))), xbmc.LOGINFO)
                            if not silent:
                                utils.showNotification(utils.getString(32101), utils.getString(32297) % (item['title'], tvshowId_xbmc), xbmc.LOGINFO)
                            tvshowId_tvdb = int(0)
                        self.tvshows[tvshowId_xbmc] = list([tvshowId_tvdb, item['title'], item['userrating']])
                        if tvshowId_tvdb > 0:
                            self.tvshownames[tvshowId_tvdb] = item['title']

            # Get all watched movies and episodes by unique id from xbmc-database via JSONRPC
            self.watchedmovielist_xbmc = list([])
            self.watchedepisodelist_xbmc = list([])
            for modus in ['movie', 'episode']:
                if self.monitor.abortRequested():
                    self.close_db(3)
                    return 4
                buggalo.addExtraData('modus', modus)
                if modus == 'movie' and utils.getSetting("w_movies") != 'true':
                    continue
                if modus == 'episode' and utils.getSetting("w_episodes") != 'true':
                    continue
                utils.log(u'get_watched_xbmc: Get all %ss from Kodi database' % modus, xbmc.LOGDEBUG)
                if modus == 'movie':
                    # use the JSON-RPC to access the xbmc-database.
                    json_response = utils.executeJSON({
                        "jsonrpc": "2.0",
                        "method": "VideoLibrary.GetMovies",
                        "params": {
                            "properties": ["title", "year", "imdbnumber", "lastplayed", "playcount", "uniqueid", "userrating"],
                            "sort": {"order": "ascending", "method": "title"}
                        },
                        "id": 1
                    })
                else:
                    json_response = utils.executeJSON({
                        "jsonrpc": "2.0",
                        "method": "VideoLibrary.GetEpisodes",
                        "params": {
                            "properties": ["tvshowid", "season", "episode", "playcount", "showtitle", "lastplayed", "uniqueid", "userrating"]
                        },
                        "id": 1
                    })
                if modus == 'movie':
                    searchkey = 'movies'
                else:
                    searchkey = 'episodes'
                if 'result' in json_response and json_response['result'] is not None and searchkey in json_response['result']:
                    # go through all watched movies and save them in the class-variable self.watchedmovielist_xbmc
                    for item in json_response['result'][searchkey]:
                        if self.monitor.abortRequested():
                            break
                        if not 'uniqueid' in item:
                            if modus == 'movie':
                                utils.log(u'get_watched_xbmc: Movie %s has no field uniqueid in database. Try rescraping.' % (item['title']), xbmc.LOGINFO)
                            else:  # episode
                                utils.log(u'get_watched_xbmc: Episode id %d (show %d, S%02dE%02d) has no field uniqueid in database. Try rescraping.' % (item['episodeid'], item['tvshowid'], item['season'], item['episode']), xbmc.LOGINFO)
                            continue
                        if modus == 'movie':
                            name = item['title'] + ' (' + str(item['year']) + ')'
                            try:
                                # check if movie number is in imdb-format (scraper=imdb)
                                res = re.compile(r'tt(\d+)').findall(item['uniqueid']['imdb'])
                                imdbId = int(res[0])
                            except BaseException: 
                                # no imdb-number for this movie in database. Skip
                                utils.log(u'get_watched_xbmc: Movie %s has no imdb-number in database. movieid=%d. IDs are %s. Try rescraping' % (name, int(item['movieid']), str(list(item['uniqueid'].keys()))), xbmc.LOGINFO)
                                imdbId = 0
                                continue
                        else:  # episodes
                            tvshowId_xbmc = item['tvshowid']
                            try:
                                tvshowName_xbmc = item['showtitle']
                            except BaseException:
                                # TODO: Something is wrong with the database or the json output since the field tvshowid is missing although requested. Check if this error still occurs and remove try-except
                                utils.log(u'get_watched_xbmc: TV episode id %d (show %d, S%02dE%02d) has no associated showtitle. Skipping.' % (item['episodeid'], item['tvshowid'], item['season'], item['episode']), xbmc.LOGWARNING)
                                continue
                            name = '%s S%02dE%02d' % (tvshowName_xbmc, item['season'], item['episode'])
                            try:
                                tvshowId_tvdb = self.tvshows[tvshowId_xbmc][0]
                            except BaseException:
                                utils.log(u'get_watched_xbmc: Kodi tv showid %d is not in Kodi-table tvshows. Skipping episode id %d (%s)' % (item['tvshowid'], item['episodeid'], name), xbmc.LOGINFO)
                                continue
                            if tvshowId_tvdb == 0:
                                utils.log(u'get_watched_xbmc: tvshow %d has no tvdb-number. Skipping episode id %d (%s)' % (item['tvshowid'], item['episodeid'], name), xbmc.LOGDEBUG)
                                continue
                        lastplayed = utils.sqlDateTimeToTimeStamp(item['lastplayed'])  # convert to integer-timestamp
                        playcount = int(item['playcount'])
                        userrating = int(item['userrating'])
                        # add data to the class-variables
                        if modus == 'movie':
                            self.watchedmovielist_xbmc.append(list([imdbId, 0, 0, lastplayed, playcount, name, 0, int(item['movieid']), userrating]))  # 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6empty, 7movieid
                        else:
                            self.watchedepisodelist_xbmc.append(list([tvshowId_tvdb, int(item['season']), int(item['episode']), lastplayed, playcount, name, 0, int(item['episodeid']), userrating]))  # 0tvdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5name, 6empty, 7episodeid
            if not silent:
                utils.showNotification(utils.getString(32101), utils.getString(32299) % (len(self.watchedmovielist_xbmc), len(self.watchedepisodelist_xbmc)), xbmc.LOGINFO)
            if self.monitor.abortRequested():
                self.close_db(3)
                return 4
            return 0
        except SystemExit:
            return 4
        except BaseException:
            utils.log(u'get_watched_xbmc: error getting the Kodi database : %s' % sys.exc_info()[2], xbmc.LOGERROR)
            self.close_db(3)
            buggalo.onExceptionRaised()
            return 1

    def get_watched_wl(self, silent):
        """Get Watched States of WL Database

        Args:
            silent: Do not show notifications if True

        Returns:
            return code:
            0    successfully got watched states from WL-database
            1    unknown error (programming related)
            2    shutdown (error in subfunction)
            3    error related to opening the database
            4    exit requested (no error)
        """

        try:
            buggalo.addExtraData('self_sqlcursor', self.sqlcursor_wl)
            buggalo.addExtraData('self_sqlcon', self.sqlcon_wl)
            if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
                if self.load_db():
                    return 2

            # get watched movies from addon database
            self.watchedmovielist_wl = list([])
            if utils.getSetting("w_movies") == 'true':
                utils.log(u'get_watched_wl: Get watched movies from WL database', xbmc.LOGDEBUG)
                if int(utils.getSetting("db_format")) != 1:  # SQLite3 File. Timestamp stored as integer
                    self.sqlcursor_wl.execute(QUERY_SELECT_MV_SQLITE)
                else:  # mySQL: Create integer timestamp with the request
                    self.sqlcursor_wl.execute(QUERY_SELECT_MV_MYSQL)
                rows = self.sqlcursor_wl.fetchall()
                for row in rows:
                    if self.monitor.abortRequested():
                        self.close_db(1)
                        return 4
                    #watchedmovielist_wl 7 #row 5
                    self.watchedmovielist_wl.append(list([int(row[0]), 0, 0, int(row[1]), int(row[2]), row[3], int(row[4]), row[5]]))  # 0tvdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6lastChange

            # get watched episodes from addon database
            self.watchedepisodelist_wl = list([])
            if utils.getSetting("w_episodes") == 'true':
                utils.log(u'get_watched_wl: Get watched episodes from WL database', xbmc.LOGDEBUG)
                if int(utils.getSetting("db_format")) != 1:  # SQLite3 File. Timestamp stored as integer
                    self.sqlcursor_wl.execute(QUERY_SELECT_EP_SQLITE)#6
                else:  # mySQL: Create integer timestamp with the request
                    self.sqlcursor_wl.execute(QUERY_SELECT_EP_MYSQL)#6

                rows = self.sqlcursor_wl.fetchall()
                for row in rows:
                    if self.monitor.abortRequested():
                        self.close_db(1)
                        return 4
                    try:
                        name = '%s S%02dE%02d' % (self.tvshownames[int(row[0])], int(row[1]), int(row[2]))
                    except BaseException:
                        name = 'tvdb-id %d S%02dE%02d' % (int(row[0]), int(row[1]), int(row[2]))
                    #watchedepisodelist_wl 7 #row 6
                    self.watchedepisodelist_wl.append(list([int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]), name, int(row[5]), int(row[6])]))  # 0tvdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5name, 6lastChange

            if not silent:
                utils.showNotification(utils.getString(32101), utils.getString(32298) % (len(self.watchedmovielist_wl), len(self.watchedepisodelist_wl)), xbmc.LOGINFO)
            return 0
        except sqlite3.Error as err:
            try:
                errstring = err.args[0]  # TODO: Find out, why this does not work some times
            except BaseException:
                errstring = ''
            utils.log(u'get_watched_wl: SQLite Database error getting the wl database. %s' % errstring, xbmc.LOGERROR)
            self.close_db(1)
            # error could be that the database is locked (for tv show strings). This is not an error to disturb the other functions
            return 3
        except mysql.connector.Error as err:
            utils.log(u'get_watched_wl: MySQL Database error getting the wl database. %s' % err, xbmc.LOGERROR)
            return 3
        except SystemExit:
            return 4
        except BaseException:
            utils.log(u'get_watched_wl: Error getting the wl database : %s' % sys.exc_info()[2], xbmc.LOGERROR)
            self.close_db(1)
            buggalo.onExceptionRaised()
            return 1

    def sync_tvshows(self):
        """Sync List of TV Shows from Kodi to WL Database

        Returns:
            return code:
            0    successfully synched tv shows
            1    database access error
            2    database loading error
            4    exit requested (no error)
        """

        try:
            utils.log(u'sync_tvshows: sync tvshows with wl database : %s' % sys.exc_info()[2], xbmc.LOGDEBUG)
            if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
                if self.load_db():
                    return 2
            # write eventually new tv shows to wl database
            for xbmcid in self.tvshows:
                if self.monitor.abortRequested():
                    break  # all queries will be commited
                values = self.tvshows[xbmcid]
                if values[0] == 0:
                    # no imdb-id saved for this tv show. Nothing to process.
                    continue
                if int(utils.getSetting("db_format")) != 1:  # sqlite3
                    self.sqlcursor_wl.execute(QUERY_INSERT_SS_SQLITE, values)
                else:  # mysql
                    self.sqlcursor_wl.execute(QUERY_INSERT_SS_MYSQL, values)
            self.database_backup()
            self.sqlcon_wl.commit()
            if self.monitor.abortRequested():
                self.close_db(1)
                return 4
            # get all known tv shows from wl database
            self.sqlcursor_wl.execute("SELECT idShow, title, userrating FROM tvshows")
            rows = self.sqlcursor_wl.fetchall()
            for row_i in rows:
                if self.monitor.abortRequested():
                    break
                self.tvshownames[int(row_i[0])] = row_i[1]
        except sqlite3.Error as err:
            try:
                errstring = err.args[0]  # TODO: Find out, why this does not work some times
            except BaseException:
                errstring = ''
            utils.log(u'sync_tvshows: SQLite Database error accessing the wl database: ''%s''' % errstring, xbmc.LOGERROR)
            self.close_db(1)
            # error could be that the database is locked (for tv show strings).
            return 1
        except mysql.connector.Error as err:
            utils.log(u"sync_tvshows: MySQL Database error accessing the wl database: ''%s''" % (err), xbmc.LOGERROR)
            self.close_db(1)
            return 1
        except SystemExit:
            return 4
        except BaseException:
            utils.log(u'sync_tvshows: Error getting the wl database: ''%s''' % sys.exc_info()[2], xbmc.LOGERROR)
            self.close_db(1)
            buggalo.onExceptionRaised()
            return 1
        if self.monitor.abortRequested():
            return 4
        return 0

    def write_wl_wdata(self):
        """Go through all watched movies from Kodi and check whether they are up to date in the addon database

        Returns:
            return code:
            0    successfully written WL
            1    program exception
            2    database loading error
            4    SystemExit
        """

        buggalo.addExtraData('self_sqlcursor', self.sqlcursor_wl)
        buggalo.addExtraData('self_sqlcon', self.sqlcon_wl)
        if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
            if self.load_db():
                return 2
        for modus in ['movie', 'episode']:
            buggalo.addExtraData('modus', modus)
            if modus == 'movie' and utils.getSetting("w_movies") != 'true':
                continue
            if modus == 'episode' and utils.getSetting("w_episodes") != 'true':
                continue
            utils.log(u'write_wl_wdata: Write watched %ss to WL database' % modus, xbmc.LOGDEBUG)
            count_insert = 0
            count_update = 0
            if utils.getSetting("progressdialog") == 'true':
                DIALOG_PROGRESS = xbmcgui.DialogProgress()
                DIALOG_PROGRESS.create(utils.getString(32101), utils.getString(32105))
            if modus == 'movie':
                list_length = len(self.watchedmovielist_xbmc)
            else:
                list_length = len(self.watchedepisodelist_xbmc)

            for i in range(list_length):
                if self.monitor.abortRequested():
                    break  # this loop can take some time in debug mode and prevents Kodi to exit
                if utils.getSetting("progressdialog") == 'true' and DIALOG_PROGRESS.iscanceled():
                    if modus == 'movie':
                        strno = 32202
                    else:
                        strno = 32203
                    utils.showNotification(utils.getString(strno), utils.getString(32301) % (count_insert, count_update), xbmc.LOGINFO)
                    return 2
                if modus == 'movie':
                    row_xbmc = self.watchedmovielist_xbmc[i]#row_xbmc 8 #watchedmovielist_xbmc 8
                else:
                    row_xbmc = self.watchedepisodelist_xbmc[i]#row_xbmc 8 #watchedepisodelist_xbmc 8

                if utils.getSetting("progressdialog") == 'true':
                    DIALOG_PROGRESS.update(int(100 * (i + 1) / list_length), (utils.getString(32105)+"\n"+utils.getString(32610) % (i + 1, list_length, row_xbmc[5])))

                try:
                    res = self._wl_update_media(modus, row_xbmc, 0, 0, 0)
                    count_insert += res['num_new']
                    count_update += res['num_update']

                except sqlite3.Error as err:
                    try:
                        errstring = err.args[0]  # TODO: Find out, why this does not work some times
                    except BaseException:
                        errstring = ''
                    utils.log(u'write_wl_wdata: SQLite Database error ''%s'' while updating %s %s' % (errstring, modus, row_xbmc[5]), xbmc.LOGERROR)
                    # error at this place is the result of duplicate movies, which produces a DUPLICATE PRIMARY KEY ERROR
                    return 1
                except mysql.connector.Error as err:
                    utils.log(u'write_wl_wdata: MySQL Database error ''%s'' while updating %s %s' % (err, modus, row_xbmc[5]), xbmc.LOGERROR)
                    self.close_db(1)
                    return 1  # error while writing. Do not continue with episodes, if movies raised an exception
                except SystemExit:
                    return 4
                except BaseException:
                    utils.log(u'write_wl_wdata: Error while updating %s %s: %s' % (modus, row_xbmc[5], sys.exc_info()[2]), xbmc.LOGERROR)
                    self.close_db(1)
                    if utils.getSetting("progressdialog") == 'true':
                        DIALOG_PROGRESS.close()
                    buggalo.addExtraData('count_update', count_update)
                    buggalo.addExtraData('count_insert', count_insert)
                    buggalo.onExceptionRaised()
                    return 1
            if utils.getSetting("progressdialog") == 'true':
                DIALOG_PROGRESS.close()
            if self.monitor.abortRequested():
                break  # break outer loop if exit requested. Do not do any database operations below
            # only commit the changes if no error occured to ensure database persistence
            if count_insert > 0 or count_update > 0:
                self.database_backup()
                self.sqlcon_wl.commit()
            if modus == 'movie':
                strno = [32202, 32301]
            else:
                strno = [32203, 32301]
            utils.showNotification(utils.getString(strno[0]), utils.getString(strno[1]) % (count_insert, count_update), xbmc.LOGINFO)
        return 0

    def write_xbmc_wdata(self, progressdialogue, notifications):
        """Go through all watched movies/episodes from the wl-database and check,
        if the xbmc-database is up to date

        Args:
            progressdialogue: Show Progress Bar if True
            notifications: 0= no, 1=only changed info, 2=all

        Returns:
            return code:
            0    successfully written Kodi database
            1    program exception
            2    cancel by user interaction
            4    SystemExit
        """

        for modus in ['movie', 'episode']:
            buggalo.addExtraData('modus', modus)
            if modus == 'movie' and utils.getSetting("w_movies") != 'true':
                continue
            if modus == 'episode' and utils.getSetting("w_episodes") != 'true':
                continue

            utils.log(u'write_xbmc_wdata: Write watched %ss to Kodi database (pd=%d, noti=%d)' % (modus, progressdialogue, notifications), xbmc.LOGDEBUG)
            count_update = 0
            if progressdialogue:
                DIALOG_PROGRESS = xbmcgui.DialogProgress()
                DIALOG_PROGRESS.create(utils.getString(32101), utils.getString(32106))

            # list to iterate over
            if modus == 'movie':
                list_length = len(self.watchedmovielist_wl)#7
            else:
                list_length = len(self.watchedepisodelist_wl)#7
            # iterate over wl-list
            for j in range(list_length):
                if self.monitor.abortRequested():
                    break  # this loop can take some time in debug mode and prevents Kodi to exit
                if progressdialogue and DIALOG_PROGRESS.iscanceled():
                    if notifications > 0:
                        utils.showNotification(utils.getString(32204), utils.getString(32302) % (count_update), xbmc.LOGINFO)
                    return 2
                # get media-specific list items
                if modus == 'movie':
                    row_wl = self.watchedmovielist_wl[j]#row_wl 7 #watchedepisodelist_wl 7
                else:
                    row_wl = self.watchedepisodelist_wl[j]#row_wl 7 #watchedepisodelist_wl 7
                    season = row_wl[1]
                    episode = row_wl[2]
                imdbId = row_wl[0]
                name = row_wl[5]

                if progressdialogue:
                    DIALOG_PROGRESS.update(int(100 * (j + 1) / list_length), (utils.getString(32106)+"\n"+utils.getString(32610) % (j + 1, list_length, name)))
                try:
                    # search the unique movie/episode id in the xbmc-list
                    if modus == 'movie':
                        indices = [i for i, x in enumerate(self.watchedmovielist_xbmc) if x[0] == imdbId]  # the movie can have multiple entries in xbmc
                    else:
                        indices = [i for i, x in enumerate(self.watchedepisodelist_xbmc) if x[0] == imdbId and x[1] == season and x[2] == episode]
                    lastplayed_wl = row_wl[3]
                    playcount_wl = row_wl[4]
                    userrating_wl = row_wl[7]
                    lastchange_wl = row_wl[6]
                    if indices:
                        # the movie/episode is already in the xbmc-list
                        for i in indices:
                            if modus == 'movie':
                                row_xbmc = self.watchedmovielist_xbmc[i]#row_xbmc 8 #watchedmovielist_xbmc 8
                            else:
                                row_xbmc = self.watchedepisodelist_xbmc[i]#row_xbmc 8 #watchedepisodelist_xbmc 8

                            lastplayed_xbmc = row_xbmc[3]
                            playcount_xbmc = row_xbmc[4]
                            userrating_xbmc = row_xbmc[8]

                            change_xbmc_db = False
                            # check if movie/episode is set as unwatched in the wl database   # ???
                            if (userrating_wl != userrating_xbmc or playcount_wl != playcount_xbmc) and lastchange_wl > lastplayed_xbmc:
                                change_xbmc_db = True
                            # compare playcount and lastplayed (update if Kodi data is older)   # ???
                            if (userrating_wl != userrating_xbmc or playcount_xbmc < playcount_wl) or (lastplayed_xbmc < lastplayed_wl and playcount_wl > 0):
                                change_xbmc_db = True
                            if not change_xbmc_db:
                                # utils.log(u'write_xbmc_wdata: Kodi database up-to-date for tt%d, %s' % (imdbId, row_xbmc[2]), xbmc.LOGDEBUG)
                                continue
                            # check if the lastplayed-timestamp in wl is useful
                            if playcount_wl == 0:
                                lastplayed_new = 0
                            else:
                                if lastplayed_wl == 0:
                                    lastplayed_new = lastplayed_xbmc
                                else:
                                    lastplayed_new = lastplayed_wl
                            # update database
                            mediaid = row_xbmc[7]
                            if modus == 'movie':
                                jsonmethod = "VideoLibrary.SetMovieDetails"
                                idfieldname = "movieid"
                            else:
                                jsonmethod = "VideoLibrary.SetEpisodeDetails"
                                idfieldname = "episodeid"
                            jsondict = {
                                "jsonrpc": "2.0",
                                "method": jsonmethod,
                                "params": {idfieldname: mediaid, "playcount": playcount_wl, "lastplayed": utils.TimeStamptosqlDateTime(lastplayed_new), "userrating": userrating_wl},
                                "id": 1
                            }
                            json_response = utils.executeJSON(jsondict)
                            if 'result' in json_response and json_response['result'] == 'OK':
                                utils.log(u'write_xbmc_wdata: Kodi database updated for %s. playcount: {%d -> %d}, lastplayed: {"%s" -> "%s"} (%sid=%d)' % (name, playcount_xbmc, playcount_wl, utils.TimeStamptosqlDateTime(lastplayed_xbmc), utils.TimeStamptosqlDateTime(lastplayed_new), modus, mediaid), xbmc.LOGINFO)
                                if playcount_wl == 0:
                                    if notifications > 0:
                                        utils.showNotification(utils.getString(32404), name, xbmc.LOGDEBUG)
                                else:
                                    if notifications > 0:
                                        utils.showNotification(utils.getString(32401), name, xbmc.LOGDEBUG)
                                count_update += 1
                                # update the xbmc-db-mirror-variable
                                if modus == 'movie':
                                    self.watchedmovielist_xbmc[i][3] = lastplayed_new
                                    self.watchedmovielist_xbmc[i][4] = playcount_wl
                                    self.watchedmovielist_xbmc[i][8] = userrating_wl
                                else:
                                    self.watchedepisodelist_xbmc[i][3] = lastplayed_new
                                    self.watchedepisodelist_xbmc[i][4] = playcount_wl
                                    self.watchedepisodelist_xbmc[i][8] = userrating_wl
                            else:
                                utils.log(u'write_xbmc_wdata: error updating Kodi database. %s. json_response=%s' % (name, str(json_response)), xbmc.LOGERROR)

                    else:
                        # the movie is in the watched-list but not in the xbmc-list -> no action
                        # utils.log(u'write_xbmc_wdata: movie not in Kodi database: tt%d, %s' % (imdbId, row_xbmc[2]), xbmc.LOGDEBUG)
                        continue
                except SystemExit:
                    return 4
                except BaseException:
                    utils.log(u"write_xbmc_wdata: Error while updating %s %s: %s" % (modus, name, sys.exc_info()[2]), xbmc.LOGERROR)
                    if progressdialogue:
                        DIALOG_PROGRESS.close()
                    buggalo.addExtraData('count_update', count_update)
                    buggalo.onExceptionRaised()
                    return 1

            if progressdialogue:
                DIALOG_PROGRESS.close()
            if self.monitor.abortRequested():
                break  # break the outer loop (movie/episode if exit requested)
            if notifications > 1:
                if modus == 'movie':
                    strno = [32204, 32302]
                else:
                    strno = [32205, 32303]
                utils.showNotification(utils.getString(strno[0]), utils.getString(strno[1]) % (count_update), xbmc.LOGINFO)
        return 0

    def database_backup(self):
        """create a copy of the database, in case something goes wrong (only if database file is used)

        Returns:
            return code:
            0    successfully copied database
            1    file writing error
            2    program exception
            4    SystemExit
        """

        if utils.getSetting("db_format") != '0':
            return 0  # no backup needed since we are using mysql database

        if utils.getSetting('dbbackupcount') == '0':
            return 0  # no backup requested in the addon settings

        if not self.dbbackupdone:
            if not xbmcvfs.exists(self.dbpath):
                utils.log(u'database_backup: directory %s does not exist. No backup possible.' % self.dbpath, xbmc.LOGERROR)
                return 1
            now = datetime.datetime.now()
            timestr = u'%04d%02d%02d_%02d%02d%02d' % (now.year, now.month, now.day, now.hour, now.minute, now.second)
            zipfilename = os.path.join(self.dbdirectory, timestr + u'-watchedlist.db.zip')
            try:
                with zipfile.ZipFile(zipfilename, 'w') as zf:
                    zf.write(self.dbpath, arcname='watchedlist.db', compress_type=zipfile.ZIP_DEFLATED)
                self.dbbackupdone = True
                utils.log(u'database_backup: database backup copy created to %s' % zipfilename, xbmc.LOGINFO)
                # copy the zip file with Kodi file system, if needed
                if self.dbfileaccess == 'copy':
                    xbmcvfs.copy(zipfilename, os.path.join(self.dbdirectory_copy, timestr + u'-watchedlist.db.zip'))
                    xbmcvfs.delete(zipfilename)
            except ValueError as err: # e.g. "timestamps before 1980"
                utils.showNotification(utils.getString(32102), utils.getString(32608) % str(err), xbmc.LOGERROR)
                utils.log(u'database_backup: Error creating database backup %s: %s' % (zipfilename, str(err)), xbmc.LOGERROR)
                self.dbbackupdone = True # pretend this was done to avoid log spamming
                return 2
            except IOError as err: # e.g. "permission denied"
                utils.showNotification(utils.getString(32102), utils.getString(32608) % err.strerror, xbmc.LOGERROR)
                utils.log(u'database_backup: Error creating database backup %s: (%s) %s' % (zipfilename, err.errno, err.strerror), xbmc.LOGERROR)
                self.dbbackupdone = True # pretend this was done to avoid log spamming
                return 2
            except SystemExit:
                return 4
            except BaseException:
                buggalo.addExtraData('zipfilename', zipfilename)
                buggalo.onExceptionRaised()
                return 2
        return 0

    def database_backup_delete(self):
        """delete old backup files

        Returns:
            return code:
            0    no operation done or operation successful
            1    error deleting the backups
        """

        if not self.dbbackupdone:
            return 0
        # Limit number of backup files to the specified value
        backupsize = int(utils.getSetting('dbbackupcount'))
        if backupsize == -1:
            return 0  # do not delete old backup files
        if self.dbfileaccess == 'copy':
            # Database is on a network share. The backup is also copied to that location. Delete old backups there.
            backupdir = self.dbdirectory_copy
        else:
            # Database and backups are in the default folders
            backupdir = self.dbdirectory

        files = xbmcvfs.listdir(backupdir)[1]
        # find database copy files among all files in that directory
        files_match = []
        for i, f in enumerate(files):
            if self.monitor.abortRequested():
                break
            if re.match(r'\d+_\d+-watchedlist\.db\.zip', f) is not None:  # match the filename string from database_backup()
                files_match.append(f)
        files_match = sorted(files_match, reverse=True)
        # Iterate over backup files starting with newest. Delete oldest
        for i, f in enumerate(files_match):
            if self.monitor.abortRequested():
                break
            if i >= int(utils.getSetting('dbbackupcount')):
                # delete file
                utils.log(u'database_backup_delete: Delete old backup file %d/%d (%s)' % (i + 1, len(files_match), f), xbmc.LOGINFO)
                try:
                    xbmcvfs.delete(os.path.join(backupdir, f))
                except BaseException:
                    utils.log(u'database_backup_delete: Error deleting old backup file %d (%s)' % (i, os.path.join(backupdir, f)), xbmc.LOGERROR)
                    return 1
        return 0

    def watch_user_changes(self, idletime_old, idletime):
        """check if the user made changes in the watched states. Especially setting movies as "not watched".
        This can not be recognized by the other functions

        Args:
            idletime_old: Old Idle Time
            idletime: New Idle Time

        Returns:
            return code:
            0    no operation done
            1    operation successful
            2    database error
            4    system exit (no error)
        """

        if xbmc.Player().isPlaying():
            return 0
        if idletime > idletime_old:
            # the idle time increased. No user interaction probably happened
            return 0
        self.watch_user_changes_count = self.watch_user_changes_count + 1
        utils.log(u'watch_user_changes: Check for user changes (no. %d)' % self.watch_user_changes_count, xbmc.LOGDEBUG)

        # save previous state
        old_watchedmovielist_xbmc = self.watchedmovielist_xbmc
        old_watchedepisodelist_xbmc = self.watchedepisodelist_xbmc
        # get new state
        self.get_watched_xbmc(1)
        # save exception information
        buggalo.addExtraData('len_old_watchedmovielist_xbmc', len(old_watchedmovielist_xbmc))
        buggalo.addExtraData('len_old_watchedepisodelist_xbmc', len(old_watchedepisodelist_xbmc))
        buggalo.addExtraData('len_self_watchedmovielist_xbmc', len(self.watchedmovielist_xbmc))
        buggalo.addExtraData('len_self_watchedepisodelist_xbmc', len(self.watchedepisodelist_xbmc))
        # Separate the change detection and the change in the database to 
        # prevent circle reference: Two steps for watching user changes
        # First step: Compare states of movies/episodes
        for modus in ['movie', 'episode']:
            if self.monitor.abortRequested():
                return 4
            buggalo.addExtraData('modus', modus)
            if modus == 'movie' and utils.getSetting("w_movies") != 'true':
                continue
            if modus == 'episode' and utils.getSetting("w_episodes") != 'true':
                continue
            if modus == 'movie':
                list_new = self.watchedmovielist_xbmc#list_new 8 #watchedmovielist_xbmc 8
                list_old = old_watchedmovielist_xbmc#list_old 8 #old_watchedmovielist_xbmc 8
            else:
                list_new = self.watchedepisodelist_xbmc#list_new 8 #watchedepisodelist_xbmc 8
                list_old = old_watchedepisodelist_xbmc#list_old 8 #old_watchedepisodelist_xbmc 8
            if not list_old or not list_new:
                # one of the lists is empty: nothing to compare. No user changes noticable
                continue
            indices_changed = list([])  # list for corresponding new/old indices
            for i_n, row_xbmc in enumerate(list_new):#row_xbmc 8 #list_new 8
                if self.monitor.abortRequested():
                    return 4
                mediaid = row_xbmc[7]
                lastplayed_new = row_xbmc[3]
                playcount_new = row_xbmc[4]
                userrating_new = row_xbmc[8]#row_xbmc 8 #list_new 8
                # index of this movie/episode in the old database (before the change by the user)
                if (len(list_old) > i_n) and (list_old[i_n][7] == mediaid):
                    i_o = i_n  # db did not change
                else:  # search the movieid
                    i_o = [i for i, x in enumerate(list_old) if x[7] == mediaid]
                    if not i_o:
                        continue  # movie is not in old array
                    i_o = i_o[0]  # convert list to int
                lastplayed_old = list_old[i_o][3]
                playcount_old = list_old[i_o][4]
                userrating_old = list_old[i_o][8]#list_old 8

                if userrating_new != userrating_old or playcount_new != playcount_old or lastplayed_new != lastplayed_old:
                    if userrating_new == userrating_old and playcount_new == playcount_old and playcount_new == 0:
                        continue  # do not add lastplayed to database, when playcount = 0
                    # The user changed the playcount or lastplayed.
                    # update wl with new watched state
                    indices_changed.append([i_n, i_o])

            # Second step: Go through all movies changed by the user
            for icx in indices_changed:
                if self.monitor.abortRequested():
                    return 4
                i_o = icx[1]
                i_n = icx[0]
                row_xbmc = list_new[i_n]#row_xbmc 8 #list_new 8
                row_xbmc_old = list_old[i_o]#row_xbmc_old 8 #list_old 8
                lastplayed_old = row_xbmc_old[3]
                playcount_old = row_xbmc_old[4]
                userrating_old = row_xbmc_old[8]
                lastplayed_new = row_xbmc[3]
                playcount_new = row_xbmc[4]
                userrating_new = row_xbmc[8]
                mediaid = row_xbmc[7]
                utils.log(u'watch_user_changes: %s "%s" changed playcount {%d -> %d} lastplayed {"%s" -> "%s"}. %sid=%d' % (modus, row_xbmc[5], playcount_old, playcount_new, utils.TimeStamptosqlDateTime(lastplayed_old), utils.TimeStamptosqlDateTime(lastplayed_new), modus, mediaid))
                try:
                    self._wl_update_media(modus, row_xbmc, 1, 1, 0)
                except sqlite3.Error as err:
                    try:
                        errstring = err.args[0]  # TODO: Find out, why this does not work some times
                    except BaseException:
                        errstring = ''
                    utils.log(u'watch_user_changes: SQLite Database error (%s) while updating %s %s' % (errstring, modus, row_xbmc[5]))
                    utils.showNotification(utils.getString(32102), utils.getString(32606) % ('(%s)' % errstring), xbmc.LOGERROR)
                    # error because of db locked or similar error
                    self.close_db(1)
                    return 2
                except mysql.connector.Error as err:
                    # Catch common mysql errors and show them to guide the user
                    utils.log(u'watch_user_changes: MySQL Database error (%s) while updating %s %s' % (err, modus, row_xbmc[5]))
                    utils.showNotification(utils.getString(32102), utils.getString(32606) % ('(%s)' % err), xbmc.LOGERROR)
                    self.close_db(1)
                    return 2

            # update Kodi watched status, e.g. to set duplicate movies also as watched
            if indices_changed:
                self.write_xbmc_wdata(0, 1)  # this changes self.watchedmovielist_xbmc
        return 1

    def _wl_update_media(self, mediatype, row_xbmc, saveanyway, commit, lastChange):
        """update the wl database for one movie/episode with the information in row_xbmc.

        This function is intended to be private and should not be called externally

        Args:
            mediatype: 'episode' or 'movie'
            row_xbmc: One row of the Kodi media table self.watchedmovielist_xbmc.
            saveanyway: Skip checks whether not to save the changes
            commit: The db change is committed directly (slow with many movies, but safe)
            lastChange: Last change timestamp of the given data.
                        If 0: Data from kodi.
                        If >0: Data from other watchedlist database for merging

        Returns: Dict with fields
            errcode:
                0    No errors
                2    error loading the database
            num_new, num_update:
                Number of new and updated entries
        """
        retval = {'errcode': 0, 'num_new': 0, 'num_update': 0}
        buggalo.addExtraData('self_sqlcursor', self.sqlcursor_wl)
        buggalo.addExtraData('self_sqlcon', self.sqlcon_wl)
        buggalo.addExtraData('len_self_watchedmovielist_wl', len(self.watchedmovielist_wl))
        buggalo.addExtraData('len_self_watchedepisodelist_wl', len(self.watchedepisodelist_wl))
        buggalo.addExtraData('len_self_tvshownames', len(self.tvshownames))
        buggalo.addExtraData('row_xbmc', row_xbmc)#row_xbmc 8
        buggalo.addExtraData('saveanyway', saveanyway)
        if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
            if self.load_db():
                retval['errcode'] = 2
                return retval

        buggalo.addExtraData('modus', mediatype)
        # row_xbmc: 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6empty, 7movieid #8
        imdbId = row_xbmc[0]
        lastplayed_xbmc = row_xbmc[3]
        playcount_xbmc = row_xbmc[4]
        userrating_xbmc = row_xbmc[8]#row_xbmc 8
        name = row_xbmc[5]
        if mediatype == 'episode':
            season = row_xbmc[1]
            episode = row_xbmc[2]

        self.database_backup()
        if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
            if self.load_db():
                retval['errcode'] = 2
                return retval
        if not saveanyway and playcount_xbmc == 0 and lastChange == 0:# ???
            # playcount in xbmc-list is empty. Nothing to save
            # utils.log(u'wl_update_%s: not watched in xbmc: tt%d, %s' % (modus, imdbId, name), xbmc.LOGDEBUG)
            return retval
        if lastChange == 0:
            lastchange_new = int(time.time())
        else:  # data from WL database with given last change timestamp
            lastchange_new = lastChange
        if lastplayed_xbmc == -1:  # used for external calls
            lastplayed_xbmc = int(time.time())
        if mediatype == 'movie':
            j = [ii for ii, x in enumerate(self.watchedmovielist_wl) if x[0] == imdbId]
        else:  # if mediatype == 'episode':
            j = [ii for ii, x in enumerate(self.watchedepisodelist_wl) if x[0] == imdbId and x[1] == season and x[2] == episode]
        if j:  # j is the list of indexes of the occurences of the given row
            j = j[0]  # there can only be one valid index j, since only one entry in wl per imdbId
            # the movie is already in the watched-list
            if mediatype == 'movie':
                row_wl = self.watchedmovielist_wl[j]#row_wl 7 #watchedmovielist_wl 7
            else:
                row_wl = self.watchedepisodelist_wl[j]#row_wl 7 #watchedepisodelist_wl 7
            lastplayed_wl = row_wl[3]
            playcount_wl = row_wl[4]
            userrating_wl = row_wl[7]
            lastchange_wl = row_wl[6]

            if not saveanyway:
                # check if an update of the wl database is necessary (xbmc watched status newer)
                if lastChange == 0:  # information from xbmc: Criterion Playcount and lastplayed-timestamp
                    if lastchange_wl > lastplayed_xbmc:
                        return retval  # no update of WL-db. Return
                    if playcount_wl >= playcount_xbmc and lastplayed_wl >= lastplayed_xbmc:
                        return retval  # everything up-to-date
                elif lastChange <= lastchange_wl:  # information from watchedlist. Only criterion: lastChange-timestamp
                    return retval

                # check if the lastplayed-timestamp in Kodi is useful
                if lastplayed_xbmc == 0 and lastChange == 0:
                    lastplayed_new = lastplayed_wl
                else:
                    lastplayed_new = lastplayed_xbmc
            else:
                lastplayed_new = lastplayed_xbmc

            if mediatype == 'movie':
                if int(utils.getSetting("db_format")) != 1:  # sqlite3
                    sql = QUERY_MV_UPDATE_SQLITE# 3
                else:  # mysql
                    sql = QUERY_MV_UPDATE_MYSQL# 3
                values = list([playcount_xbmc, lastplayed_new, lastchange_new, userrating_xbmc, imdbId])
            else:
                if int(utils.getSetting("db_format")) != 1:  # sqlite3
                    sql = QUERY_EP_UPDATE_SQLITE#3
                else:  # mysql
                    sql = QUERY_EP_UPDATE_MYSQL#3
                    # fix timestamp/timezone; from https://github.com/SchapplM/xbmc-addon-service-watchedlist/issues/28#issuecomment-1890145879
                    if lastplayed_new == 0:
                        lastplayed_new = 1
                    if lastchange_new == 0:
                        lastchange_new = 1
                values = list([playcount_xbmc, lastplayed_new, lastchange_new, userrating_xbmc, imdbId, season, episode])
            self.sqlcursor_wl.execute(sql, values)
            retval['num_update'] = self.sqlcursor_wl.rowcount
            # update the local mirror variable of the wl database: # 0imdbnumber, season, episode, 3lastPlayed, 4playCount, 5title, 6lastChange
            if mediatype == 'movie':
                self.watchedmovielist_wl[j] = list([imdbId, 0, 0, lastplayed_new, playcount_xbmc, name, lastchange_new, userrating_xbmc])#watchedmovielist_wl 7
            else:
                self.watchedepisodelist_wl[j] = list([imdbId, season, episode, lastplayed_new, playcount_xbmc, name, lastchange_new, userrating_xbmc])#watchedepisodelist_wl 7
            utils.log(u'wl_update_%s: updated wl db for "%s" (id %d). playcount: {%d -> %d}. lastplayed: {"%s" -> "%s"}. lastchange: "%s. Affected %d row."' % (mediatype, name, imdbId, playcount_wl, playcount_xbmc, utils.TimeStamptosqlDateTime(lastplayed_wl), utils.TimeStamptosqlDateTime(lastplayed_new), utils.TimeStamptosqlDateTime(lastchange_new), self.sqlcursor_wl.rowcount), xbmc.LOGDEBUG)
            if playcount_xbmc > 0:
                utils.showNotification(utils.getString(32403), name, xbmc.LOGDEBUG)
            else:
                utils.showNotification(utils.getString(32405), name, xbmc.LOGDEBUG)
        else:
            # the movie is not in the watched-list -> insert the movie
            # order: idMovieImdb,playCount,lastChange,lastPlayed,title
            if mediatype == 'movie':
                if int(utils.getSetting("db_format")) != 1:  # sqlite3
                    sql = QUERY_MV_INSERT_SQLITE#5
                else:  # mysql
                    sql = QUERY_MV_INSERT_MYSQL#5
                values = list([imdbId, playcount_xbmc, lastchange_new, lastplayed_xbmc, name, userrating_xbmc])
            else:  # episode
                if int(utils.getSetting("db_format")) != 1:  # sqlite3
                    sql = QUERY_EP_INSERT_SQLITE#6
                else:  # mysql
                    sql = QUERY_EP_INSERT_MYSQL#6
                values = list([imdbId, season, episode, playcount_xbmc, lastchange_new, lastplayed_xbmc, userrating_xbmc])
            self.sqlcursor_wl.execute(sql, values)
            utils.log(u'wl_update_%s: new entry for wl database: "%s", lastChange="%s", lastPlayed="%s", playCount=%d. Affected %d row.' % (mediatype, name, utils.TimeStamptosqlDateTime(lastchange_new), utils.TimeStamptosqlDateTime(lastplayed_xbmc), playcount_xbmc, self.sqlcursor_wl.rowcount))
            retval['num_new'] = self.sqlcursor_wl.rowcount
            # update the local mirror variable of the wl database
            if mediatype == 'movie':
                self.watchedmovielist_wl.append(list([imdbId, 0, 0, lastplayed_xbmc, playcount_xbmc, name, lastchange_new, userrating_xbmc]))#7
            else:
                self.watchedepisodelist_wl.append(list([imdbId, season, episode, lastplayed_xbmc, playcount_xbmc, name, lastchange_new, userrating_xbmc]))#7
            if playcount_xbmc > 0:
                utils.showNotification(utils.getString(32402), name, xbmc.LOGDEBUG)
            else:
                utils.showNotification(utils.getString(32405), name, xbmc.LOGDEBUG)
        if commit:
            self.sqlcon_wl.commit()
        return retval

    def wl_update_media(self, mediatype, row_xbmc, saveanyway, commit, lastChange):
        """update the wl database for one movie/episode with the information in row_xbmc.

        Function for external access with basic error handling

        Args:
            mediatype: 'episode' or 'movie'
            row_xbmc: One row of the Kodi media table self.watchedmovielist_xbmc or self.watchedepisodelist_xbmc.
                    List with [0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6empty, 7movieid]
                    or [0tvdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5name, 6empty, 7episodeid]
            saveanyway: Skip checks whether not to save the changes
            commit: The db change is committed directly (slow with many movies, but safe)
            lastChange: Last change timestamp of the given data.
                        If 0: Data from kodi.
                        If >0: Data from other watchedlist database for merging

        Returns: Dict with fields
            errcode:
                0    No errors
                1    error with the database
                2    error loading the database
            num_new, num_update:
                Number of new and updated entries
        """
        retval = {'errcode': 0, 'num_new': 0, 'num_update': 0}
        try:
            return self._wl_update_media(mediatype, row_xbmc, saveanyway, commit, lastChange)
        except sqlite3.Error as err:
            try:
                errstring = err.args[0]  # TODO: Find out, why this does not work some times
            except BaseException:
                errstring = ''
            utils.log(u'wl_update_media: SQLite Database error accessing the wl database: ''%s''' % errstring, xbmc.LOGERROR)
            utils.showNotification(utils.getString(32109), errstring, xbmc.LOGERROR)
            self.close_db(1)
            retval['errcode'] = 1
        except mysql.connector.Error as err:
            utils.log(u"wl_update_media: MySQL Database error accessing the wl database: ''%s''" % (err.msg), xbmc.LOGERROR)
            utils.showNotification(utils.getString(32108), err.msg, xbmc.LOGERROR)
            self.close_db(1)
            retval['errcode'] = 1
        return retval

    def merge_dropbox_local(self):
        """
        Merge the remote (eg: Dropbox) database into the local one
        The resulting merged database contains all watched movies and episodes of both databases

        Returns:
            return code:
            0    successfully synched databases
            1    database access error
            2    database loading error
            4    exit requested (no error)
        """

        if not self.dropbox_path:
            utils.log(u'merge_dropbox_local: no dropbox path -- assuming download failed. not merging remote database.')
            return 1

        try:
            if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
                if self.load_db():
                    return 2

            # do not merge tvshows between dropbox and local wl database.
            # Only movies and episodes
            count_insert = 0
            count_update = 0
            for mediatype in ['movie', 'episode']:
                # strno: number of string for heading of notifications
                # sql_select_dropbox: Definitions of SQL queries to get data from the dropbox database
                if mediatype == 'movie':
                    strno = 32711
                    sql_select_dropbox = QUERY_SELECT_MV_SQLITE#5
                else:
                    strno = 32712
                    sql_select_dropbox = QUERY_SELECT_EP_SQLITE#6
                utils.log(u'wl_merge_dropbox_local (%s): Start merging the remote into the local database' % mediatype)
                self.sqlcursor_db.execute(sql_select_dropbox)
                # loop through all rows of the remote (dropbox) database and merge it into the local database with
                # with the function for merging the Kodi database
                if utils.getSetting("progressdialog") == 'true':
                    DIALOG_PROGRESS = xbmcgui.DialogProgress()
                    DIALOG_PROGRESS.create(utils.getString(strno), utils.getString(32105))
                rows = self.sqlcursor_db.fetchall()
                list_length = len(rows)
                for i in range(list_length):
                    if self.monitor.abortRequested():
                        break
                    row = rows[i]  # see definition of sql_select_dropbox for contents of `row`
                    if mediatype == 'movie':  # idMovieImdb, 1lastPlayed, 2playCount, 3title, 4lastChange
                        name = "%s" % row[3]
                        playCount = row[2]
                        userrating = row[5]#row 5
                        lastChange = row[4]
                        lastPlayed = row[1]
                    else:  # 0idShow, 1season, 2episode, 3lastPlayed, 4playCount, 5lastChange
                        try:
                            name = '%s S%02dE%02d' % (self.tvshownames[int(row[0])], int(row[1]), int(row[2]))
                        except BaseException:
                            name = 'tvdb-id %d S%02dE%02d' % (int(row[0]), int(row[1]), int(row[2]))
                        playCount = row[4]
                        userrating = row[6]#row 6
                        lastChange = row[5]
                        lastPlayed = row[3]

                    # handle the row from the dropbox database as if it came from the Kodi database and
                    # store it in the local WL database (same function call)
                    # row_xbmc_sim: 0imdbnumber, 1seasonnumber, 2episodenumber, 3lastPlayed, 4playCount, 5title, 6empty, 7movieid
                    row_xbmc_sim = [0, 0, 0, lastPlayed, playCount, name, 0, userrating]# ??? #8 ?
                    if mediatype == 'movie':
                        row_xbmc_sim[0] = row[0]# ???
                    else:
                        row_xbmc_sim[0:3] = row[0:3]# ???
                    res = self._wl_update_media(mediatype, row_xbmc_sim, 0, 0, lastChange)
                    count_insert += res['num_new']
                    count_update += res['num_update']

                    # check if update is canceled
                    if utils.getSetting("progressdialog") == 'true' and DIALOG_PROGRESS.iscanceled():
                        return 2
                    if utils.getSetting("progressdialog") == 'true':
                        DIALOG_PROGRESS.update(int(100 * (i + 1) / list_length), (utils.getString(32105)+"\n"+utils.getString(32610) % (i + 1, list_length, row_xbmc_sim[5])))

                utils.showNotification(utils.getString(strno), utils.getString(32301) % (count_insert, count_update), xbmc.LOGINFO)
                if utils.getSetting("progressdialog") == 'true':
                    DIALOG_PROGRESS.close()
                if self.monitor.abortRequested():
                    return 4
        except sqlite3.Error as err:
            try:
                errstring = err.args[0]  # TODO: Find out, why this does not work some times
            except BaseException:
                errstring = ''
            utils.log(u'merge_dropbox_local: SQLite Database error accessing the wl database: ''%s''' % errstring, xbmc.LOGERROR)
            self.close_db(3)
            # error could be that the database is locked (for tv show strings).
            if utils.getSetting("progressdialog") == 'true':
                DIALOG_PROGRESS.close()
            return 1
        except SystemExit:
            return 4
        except BaseException:
            utils.log(u'merge_dropbox_local: Error getting the wl database: ''%s''' % sys.exc_info()[2], xbmc.LOGERROR)
            self.close_db(3)
            buggalo.onExceptionRaised()
            if utils.getSetting("progressdialog") == 'true':
                DIALOG_PROGRESS.close()
            return 1
        # commit all changes: This saves the database file physically
        self.sqlcon_wl.commit()
        return 0

    def merge_local_dropbox(self):
        """
        Merge the local database into the remote one (e.g. dropbox) by copying all tables directly
        the content is already merged after loading the remote database (merge_dropbox_local)

        Returns:
            return code:
            0    successfully synched databases
            1    database access error
            2    database loading error
            4    exit requested (no error)
        """

        if not self.dropbox_path:
            utils.log(u'merge_dropbox: no dropbox path -- assuming download failed. not merging remote database.')
            return 1

        try:
            if self.sqlcursor_wl == 0 or self.sqlcon_wl == 0:
                if self.load_db():
                    return 2

            # do not merge tvshows between dropbox and local wl database

            # clear dropbox database and just insert all rows from the local db
            self.sqlcursor_db.execute(QUERY_CLEAR_MV_SQLITE)
            self.sqlcursor_db.execute(QUERY_CLEAR_EP_SQLITE)

            for mediatype in ['movie', 'episode']:
                # strno: number of string for heading of notifications
                # sql_select_wl: Definitions of SQL queries to get data from the local database
                utils.log(u'merge_local_dropbox (%s): Start merging the local into the remote database' % mediatype)
                if mediatype == 'movie':
                    strno = 32718
                    rows = self.watchedmovielist_wl  # 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6lastChange
                else:
                    strno = 32719
                    rows = self.watchedepisodelist_wl  # 0tvdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5empty, 6lastChange

                # loop through all rows of the local database and merge it into the remote (dropbox) database
                if utils.getSetting("progressdialog") == 'true':
                    DIALOG_PROGRESS = xbmcgui.DialogProgress()
                    DIALOG_PROGRESS.create(utils.getString(strno), utils.getString(32716))
                list_length = len(rows)
                for i in range(list_length):
                    if self.monitor.abortRequested():
                        break
                    row = rows[i]  # see definition of queries for contents of `row`
                    if mediatype == 'movie':
                        name = row[5]
                        sql = QUERY_MV_INSERT_SQLITE  # idMovieImdb,playCount,lastChange,lastPlayed,title
                        values = list([row[0], row[4], row[6], row[3], row[5], row[7]])
                    else:
                        try:
                            name = '%s S%02dE%02d' % (self.tvshownames[int(row[0])], int(row[1]), int(row[2]))
                        except BaseException:
                            name = 'tvdb-id %d S%02dE%02d' % (int(row[0]), int(row[1]), int(row[2]))
                        sql = QUERY_EP_INSERT_SQLITE  # idShow,season,episode,playCount,lastChange,lastPlayed
                        values = list([row[0], row[1], row[2], row[4], row[6], row[3], row[7]])
                    self.sqlcursor_db.execute(sql, values)

                    # check if update is canceled DIALOG_PROGRESS.close()
                    if utils.getSetting("progressdialog") == 'true' and DIALOG_PROGRESS.iscanceled():
                        return 2
                    if utils.getSetting("progressdialog") == 'true':
                        DIALOG_PROGRESS.update(int(100 * (i + 1) / list_length), (utils.getString(32716)+"\n"+utils.getString(32610) % (i + 1, list_length, name)))
                utils.showNotification(utils.getString(strno), (utils.getString(32717)) % list_length, xbmc.LOGINFO)
                if utils.getSetting("progressdialog") == 'true':
                    DIALOG_PROGRESS.close()
                if self.monitor.abortRequested():
                    return 4  # no further database operations
        except sqlite3.Error as err:
            try:
                errstring = err.args[0]  # TODO: Find out, why this does not work some times
            except BaseException:
                errstring = ''
            utils.log(u'merge_local_dropbox: SQLite Database error accessing the wl database: ''%s''' % errstring, xbmc.LOGERROR)
            self.close_db(3)
            # error could be that the database is locked (for tv show strings).
            if utils.getSetting("progressdialog") == 'true':
                DIALOG_PROGRESS.close()
            return 1
        except SystemExit:
            return 4
        except BaseException:
            utils.log(u'merge_local_dropbox: Error getting the wl database: ''%s''' % sys.exc_info()[2], xbmc.LOGERROR)
            self.close_db(3)
            buggalo.onExceptionRaised()
            if utils.getSetting("progressdialog") == 'true':
                DIALOG_PROGRESS.close()
            return 1
        # only commit the changes if no error occured above (to ensure database persistence)
        self.sqlcon_db.commit()
        self.close_db(2)  # close dropbox database
        return 0

    def pushToDropbox(self):
        dropbox_key = utils.getSetting('dropbox_apikey')

        #utils.showNotification(utils.getString(32204), utils.getString(32302)%(count_update))
        # feign success if there is no local dropbox database file
        if not (self.dropbox_path and dropbox_key):
            return

        dest_file = '/' + 'watchedlist.db'
        old_file = '/old' + 'watchedlist.db'

        client = dropbox.Dropbox(dropbox_key)

        # delete the old watched list. Failure here doesn't really matter
        try:
            client.files_delete(old_file)
        except BaseException:
            utils.log(u'Dropbox error: Unable to delete previous old watched list (%s)' % old_file)

        # rename the previously uploaded watchlist to "oldWHATEVER"
        try:
            client.files_move_v2(dest_file, old_file)
        except BaseException:
            utils.log(u'Dropbox error: Unable rename previous watched list')

        f = open(self.dropbox_path, 'rb')
        try:
            client.files_upload(f.read(), dest_file)
        except DropboxApiError as err:
            utils.log(u'Dropbox upload error: ' + str(err))
            utils.showNotification(utils.getString(32708), utils.getString(32709), xbmc.LOGERROR)
            return
        finally:
            f.close()
        utils.showNotification(utils.getString(32713), utils.getString(32714), xbmc.LOGINFO)
        utils.log(u'Dropbox upload complete: %s -> %s' % (self.dropbox_path, dest_file))

    def pullFromDropbox(self):
        """
        Downloads the dropbox database

        Returns:
            return code:
            0    successfully downloaded databases
            1    database download error
        """
        dropbox_key = utils.getSetting('dropbox_apikey')

        if not dropbox_key:
            # no dropbox authorization key entered. Feature does not work.
            utils.showNotification(utils.getString(32708), utils.getString(32715), xbmc.LOGWARNING)
            return 0

        utils.log(u'Downloading WatchedList from dropbox')

        client = dropbox.Dropbox(dropbox_key)

        # save the dropbox database file in the user data directory (this is only a temporary file for upload and download)
        self.dropbox_path = os.path.join(utils.data_dir(), "dropbox.db")
        dropbox_file_exists = False

        remote_file = '/' + 'watchedlist.db'
        old_file = '/old' + 'watchedlist.db'
        # first: Try downloading the database file (if existent).
        # if that fails, try restoring the backup file (if existent).
        # if that also fails, the database will be rewritten (in other function)
        try:
            trycount = 0
            while trycount <= 4:  # two tries for db file (trycount 1, 2), then try copying backup and download that (trycount 3,4)
                if self.monitor.abortRequested():
                    break
                trycount = trycount + 1
                try:
                    client.files_download_to_file(self.dropbox_path, remote_file)
                    dropbox_file_exists = True
                    break
                except DropboxApiError as err:
                    # file not available, e.g. deleted or first execution.
                    utils.log(u'Dropbox database download failed. %s.' % str(err))
                    time.sleep(0.5)  # wait to avoid immediate re-try
                    if err[1].is_path() and isinstance(err[1].get_path(), dropbox.files.LookupError):
                        # Error reason: file does not exist
                        trycount = trycount + 1  # do not try second time on downloading non-existing file
                if trycount == 2 and not dropbox_file_exists:
                    try:
                        # No file was downloaded after second try. That means the dropbox file does not exist
                        # Try restoring the backup file, if existent
                        client.files_copy(old_file, remote_file)
                    except DropboxApiError as err:  # files_copy raises RelocationError
                        # file not available, e.g. deleted or not existing
                        utils.log(u'Dropbox restore database backup failed. %s.' % str(err))
                        break
        except BaseException:  # catch this error, the dropbox mode will be disabled
            utils.log(u'Dropbox download error: ' + str(sys.exc_info()))
            utils.showNotification(utils.getString(32708), utils.getString(32710), xbmc.LOGERROR)
            self.dropbox_path = ''
            return 1
        # check if file was written
        if dropbox_file_exists:
            utils.log(u'Dropbox database downloaded: %s -> %s' % (remote_file, self.dropbox_path))
        else:
            utils.log(u'Dropbox database download failed. No remote file available.')
        return 0

    def get_movie_status(self, imdbId):
        """
        Return the watched state of one movie from the internal WL database copy
        requires this class to have a loaded database

        Args:
            imdbId (Integer)

        Returns:
            List with [Playcount, lastPlayed (integer timestamp), lastChange (integer timestamp)]
            if no entry is available, playcount is -1
        """
        j = [ii for ii, x in enumerate(self.watchedmovielist_wl) if x[0] == imdbId]#watchedmovielist_wl 7
        if not j:
            return [-1, 0, 0]
        return [self.watchedmovielist_wl[j[0]][x] for x in [4, 3, 6, 7]]  # return 4playCount, 3lastPlayed, 6lastChange

    def get_episode_status(self, tvdbId, season, episode):
        """
        Return the watched state of one tv series episode from the internal WL database copy
        requires this class to have a loaded database

        Args:
            tvdbId, season, episode (Integer)

        Returns:
            List with [Playcount, lastPlayed (integer timestamp), lastChange (integer timestamp)]
            if no entry is available, playcount is -1
        """
        j = [ii for ii, x in enumerate(self.watchedepisodelist_wl) if x[0] == tvdbId and x[1] == season and x[2] == episode]#watchedepisodelist_wl 7
        if not j:
            return [-1, 0, 0]
        return [self.watchedepisodelist_wl[j[0]][x] for x in [4, 3, 6, 7]]  # return 4playCount, 3lastPlayed, 6lastChange
