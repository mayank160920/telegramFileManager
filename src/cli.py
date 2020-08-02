import curses
import misc

from backend.sessionsHandler import SessionsHandler

class UserInterface:
    def __init__(self):
        self.notifBuf = ''
        self.selected = 0

        self.cfg = misc.loadConfig()

        try:
            realChannelID = int(self.cfg['telegram']['channel_id'])
        except ValueError:
            realChannelID = self.cfg['telegram']['channel_id']

        self.sHandler = SessionsHandler(
                realChannelID, self.cfg['telegram']['api_id'],
                self.cfg['telegram']['api_hash'], self.cfg['paths']['data_path'],
                self.cfg['paths']['tmp_path'], int(self.cfg['telegram']['max_sessions'])
        )

        self.scr = curses.initscr()

        curses.noecho()
        curses.cbreak()
        curses.curs_set(False)
        self.scr.keypad(True)
        self.scr.nodelay(True)
        self.scr.timeout(5000)
        # waits for 5 seconds or a key to be pressed to refresh the screen


    def _getInputs(self, title, prompts):
        self.scr.nodelay(False)
        curses.echo()
        curses.curs_set(True)

        self.scr.addstr(0, 0, title)
        i = 2
        inputs = {}
        for key, prompt in prompts.items():
            self.scr.addstr(i, 0, prompt)
            inputs[key] = self.scr.getstr(i + 1, 0).decode(encoding='utf-8')

            if not inputs[key]: # User wants to cancel
                break

            i+=3

        curses.curs_set(False)
        curses.noecho()
        self.scr.nodelay(True)
        self.scr.timeout(5000)
        self.scr.erase()
        return inputs


    def _selectFromList(self, title, prompts):
        self.scr.nodelay(False)

        MAX_PAD_X = 250
        promptCount = len(prompts)
        scrPad = curses.newpad(promptCount+10, MAX_PAD_X) # Y, X max size
        selected = showX = showY = 0
        inputKey = None
        action = 'download'

        while inputKey != ord('\n'): # Enter
            scrPad.addstr(0, 0, title, curses.A_STANDOUT)

            for i in range(promptCount):
                scrPad.addstr(2 + i, 2, prompts[i]['title'],
                              curses.A_STANDOUT if selected == i else curses.A_NORMAL)

            tlX, tlY = os.get_terminal_size(0)
            self.scr.refresh()
            scrPad.refresh(showY, showX, 0, 0, tlY-1, tlX-1)

            inputKey = self.scr.getch()

            if inputKey == curses.KEY_DOWN and selected < promptCount-1:
                selected += 1
                if selected + 4 > showY + tlY:
                    showY += 1

            elif inputKey == curses.KEY_UP and selected > 0:
                selected -= 1
                if selected < showY:
                    showY -= 1

            elif inputKey == curses.KEY_NPAGE: # Page Down
                selected += tlY-1
                showY += tlY-1
                if selected > promptCount-1:
                    selected = promptCount-1
                if showY > promptCount-(tlY-5):
                    showY = promptCount-(tlY-5)

            elif inputKey == curses.KEY_PPAGE: # Page Up
                selected -= tlY-1
                showY -= tlY-1
                if selected < 0:
                    selected = 0
                if showY < 0:
                    showY = 0

            elif inputKey == curses.KEY_RIGHT and showX < MAX_PAD_X:
                showX += round(tlX/2)
                if showX > MAX_PAD_X-1:
                    showX = MAX_PAD_X-1
            elif inputKey == curses.KEY_LEFT and showX >= 0:
                showX -= round(tlX/2)
                if showX < 0:
                    showX = 0

            elif inputKey in [ord('d'), ord('D')]:
                action = 'delete'
                break

            elif inputKey in [ord('r'), ord('R')]:
                action = 'rename'
                break

            elif inputKey in [ord('q'), ord('Q')]:
                action = 'quit'
                break

        self.scr.nodelay(True)
        self.scr.timeout(5000)
        self.scr.erase()

        if action == 'quit':
            return None
        else:
            return {'selected' : prompts[selected],
                    'action' : action}


    def resumeHandler(self):
        inDict = {}
        for sFile, info in self.sHandler.resumeData.items():
            if info and info['handled'] == 2:
                # has resume data that was ignored for later
                inDict[sFile] = "Session {}, '{}' - {}:".format(sFile,
                    '/'.join(info['rPath']), misc.bytesConvert(info['size'])
                )

        if not inDict:
            self.notifBuf = "No resume information."
            return

        resumeOpts = self._getInputs("Resume files found, choose an option for each: (1) Finish the transfer (2) Ignore for now (3) Delete resume file",
                                     inDict)

        for sFile, selected in resumeOpts.items():
            if selected:
                try:
                    intSelected = int(selected)
                except ValueError:
                    continue

                self.sHandler.resumeHandler(sFile, intSelected)


    def cancelHandler(self):
        if not self.selected:
            self.notifBuf = "No transfer selected to cancel."
            return

        # Only solution I found for cancelling the right transfer
        i = 0
        for sFile, info in self.sHandler.transferInfo.items():
            if not info['type']: # empty
                continue
            i += 1
            if i == self.selected:
                if info['size'] <= 2000*1024*1024: # no chunks
                    self.notifBuf = "Can't cancel single chunk transfers"
                    return

                try:
                    if self._getInputs("Cancel transfer {}?".format('/'.join(info['rPath'])),
                            {'selected' : "Type 'yes' if you are sure:"})['selected'] == 'yes':
                        self.sHandler.cancelTransfer(sFile)
                        self.notifBuf = "Transfer {} cancelled".format('/'.join(info['rPath']))
                except ValueError:
                    self.notifBuf = "Transfer already cancelled."

                break


    def uploadHandler(self):
        if not self.sHandler.freeSessions:
            self.notifBuf = 'All sessions are currently used.'
            return

        inData = self._getInputs("Upload", {'path'  : "File Path:",
                                            'rPath' : "Relative Path:"})

        if not inData['path'] or not inData['rPath']:
            return

        if not os.path.isfile(inData['path']):
            self.notifBuf = "There is no file with this path."
            return

        self.sHandler.transferInThread({'rPath'      : inData['rPath'].split('/'),
                                        'path'       : inData['path'],
                                        'size'       : os.path.getsize(inData['path']),
                                        'fileID'     : [],
                                        'index'      : 0, # managed by transferHandler
                                        'chunkIndex' : 0,
                                        'type'       : 'upload',
                                        'handled'    : 0})


    def downloadHandler(self):
        if not self.sHandler.freeSessions:
            self.notifBuf = 'All sessions are currently used.'
            return

        prompts = []
        totalSize = 0
        # Generate list dynamically
        for i in self.sHandler.fileDatabase:
            totalSize += i['size']

            prompts.append({'title'  : "{}  {}".format(
                                '/'.join(i['rPath']),
                                misc.bytesConvert(i['size'])
                            ),
                            'rPath'  : i['rPath'],
                            'fileID' : i['fileID'],
                            'size'   : i['size']})

        inData = self._selectFromList("Enter to download, d to delete, r to rename - {} Total".format(
                                          misc.bytesConvert(totalSize)
                                      ), prompts)

        if inData: # not cancelled
            if inData['action'] == 'delete':
                if self._getInputs("Delete file {}?".format('/'.join(inData['selected']['rPath'])),
                                    {'selected' : "Type 'yes' if you are sure:"})['selected'] != 'yes':
                    return

                tmpData = {'rPath'  : inData['selected']['rPath'],
                           'fileID' : inData['selected']['fileID'],
                           'size'   : inData['selected']['size']}
                self.sHandler.deleteInDatabase(tmpData)
                return

            if inData['action'] == 'rename':
                tmpName = "{}:".format('/'.join(inData['selected']['rPath']))
                name = self._getInputs("Rename file", {'rPath' : tmpName})['rPath']

                if not name:
                    return

                tmpData = {'rPath'  : inData['selected']['rPath'],
                           'fileID' : inData['selected']['fileID'],
                           'size'   : inData['selected']['size']}

                self.sHandler.renameInDatabase(tmpData, name.split('/'))
                return

            # else download
            dPath = self._getInputs("Download file {}".format('/'.join(inData['selected']['rPath'])),
                                    {'dPath' : "Download path, leave empty for default:"})['dPath']

            # check if folder exists
            if dPath and not os.path.isdir(dPath):
                self.notifBuf = "Specified path does not exist."
                return

            self.sHandler.transferInThread({'rPath'   : inData['selected']['rPath'],
                                            'dPath'   : dPath,
                                            'fileID'  : inData['selected']['fileID'],
                                            'IDindex' : 0,
                                            'size'    : inData['selected']['size'],
                                            'type'    : 'download',
                                            'handled' : 0})


    def main(self):
        NAME = "Telegram File Manager"
        optionDict = {'upload' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['upload']), 'function' : self.uploadHandler},
                      'download' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['download']), 'function' : self.downloadHandler},
                      'cancel' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['cancel']), 'function' : self.cancelHandler},
                      'resume' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['resume']), 'function' : self.resumeHandler}}

        try:
            self.resumeHandler()

            while True:
                self.scr.erase()
                tlX, tlY = os.get_terminal_size(0)

                for option, info in optionDict.items():
                    if info['value']:
                        info['function']()
                        info['value'] = False
                        break

                usedSessionStr = "[ {} of {} ]".format(
                    self.sHandler.max_sessions - len(self.sHandler.freeSessions), self.sHandler.max_sessions)

                # program name
                self.scr.addstr(0, max(round((tlX-len(NAME))/2), 0), NAME)
                # Nr of used sessions
                self.scr.addstr(1, max(tlX-len(usedSessionStr), 0), usedSessionStr)

                # transfer info
                i = 2 # on which line to start displaying transfers
                if self.selected:
                    for j in range((self.selected-1)*4+i, (self.selected-1)*4+i+3):
                        self.scr.addch(j, 0, '*')

                for sFile, info in self.sHandler.transferInfo.items():
                    if not info['type']: # empty
                        continue

                    self.scr.addstr(i, 2, "Uploading:" if info['type'] == 'upload' else "Downloading:")
                    self.scr.addstr(i+1, 2, '/'.join(info['rPath']))
                    self.scr.addstr(i+2, 2, "{}% - {}".format(info['progress'], misc.bytesConvert(info['size'])))
                    i+=4

                if self.notifBuf:
                    self.scr.addstr(tlY-1, 0, self.notifBuf, curses.A_STANDOUT)
                    self.notifBuf = ''

                ignoredTransfers = 0
                for i in range(1, self.sHandler.max_sessions+1):
                    if (
                        self.sHandler.resumeData[str(i)] and
                        self.sHandler.resumeData[str(i)]['handled'] == 2
                       ):
                        ignoredTransfers += 1

                ch = self.scr.getch()
                if ch == curses.KEY_UP and self.selected > 1:
                    self.selected -= 1
                elif (
                      ch == curses.KEY_DOWN and
                      (self.selected < self.sHandler.max_sessions -
                          (len(self.sHandler.freeSessions) + ignoredTransfers))
                     ):
                    self.selected += 1

                elif ch == ord('q'):
                    break

                for option, info in optionDict.items():
                    if info['keybind'] == ch:
                        info['value'] = True
                        break

                # Go to the last transfer if the transfer that was selected finished
                if (self.selected > self.sHandler.max_sessions -
                        (len(self.sHandler.freeSessions) + ignoredTransfers)):

                    self.selected = (self.sHandler.max_sessions -
                        (len(self.sHandler.freeSessions) + ignoredTransfers))

        except KeyboardInterrupt: # dont crash the terminal when quitting with Ctrl+C
            pass

        # exit
        curses.endwin()
        self.sHandler.endSessions() # Must call to exit the program


if __name__ == "__main__":
    ui = UserInterface()
    ui.main()
