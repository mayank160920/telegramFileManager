import os
import curses
import configparser
import pyrCaller
import threading

cfg = configparser.ConfigParser()
cfg.read(os.path.expanduser("~/.config/tgFileManager.ini"))

class transferHandler:
    def __init__(self, telegram_channel_id, api_id, api_hash, data_path,
                 tmp_path, max_sessions):

        self.freeSessions = []
        for i in range(1, max_sessions+1):
            self.freeSessions.append(str(i))

        self.telegram_channel_id = telegram_channel_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.data_path = data_path
        self.tmp_path = tmp_path
        self.max_sessions = max_sessions


    def useSession(self):
        if not len(self.freeSessions):
            return '' # no free sessions

        retSession = self.freeSessions[0]
        self.freeSessions.pop(0)
        return retSession


    def freeSession(self, sessionStr=''):
        if (not sessionStr) or not (type(sessionStr) is str):
            raise TypeError("Bad or empty value given.")
        if not int(sessionStr) in range(1, self.max_sessions+1):
            raise IndexError("sessionStr should be between 1 and {}.".format(max_sessions))

        self.freeSessions.append(sessionStr)


    def upload()


tg = transferHandler(cfg['telegram']['channel_id'], cfg['telegram']['api_id'],
                     cfg['telegram']['api_hash'], cfg['paths']['data_path'],
                     cfg['paths']['tmp_path'], int(cfg['telegram']['max_sessions']))

# initialize the screen
scr = curses.initscr()

curses.noecho()
curses.cbreak()
curses.curs_set(False)
scr.keypad(True)
scr.nodelay(True)
scr.timeout(5000)
# wait for 5 seconds or a key to be pressed to refresh the screen

try:
    while True:
        scr.erase()
        tlX, tlY = os.get_terminal_size(0)

        usedSessionStr="[ {} of {} ]".format(tg.max_sessions-len(tg.freeSessions),
                                             tg.max_sessions)

        scr.addstr(1, max(tlX-len(usedSessionStr), 0),
                   usedSessionStr, curses.A_NORMAL)

        ch = scr.getch()
        if ch == 17: # Ctrl+Q
            break
except KeyboardInterrupt:
    pass

# exit
curses.endwin()
