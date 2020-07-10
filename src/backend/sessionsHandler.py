'''
Extends transferHandler by managing the database and implementing multithreading
'''

from .transferHandler import TransferHandler
from .fileIO import FileIO
import threading
from operator import itemgetter

class SessionsHandler:
    def __init__(self, telegram_channel_id, api_id, api_hash,
                 data_path, tmp_path, max_sessions):

        self.api_id = api_id
        self.api_hash = api_hash
        self.data_path = data_path
        self.max_sessions = max_sessions
        self.fileIO = FileIO(data_path, tmp_path, max_sessions)
        self.tHandler = {}
        self.freeSessions = []
        self.transferInfo = {}
        self.fileDatabase = self.fileIO.loadDatabase()
        self.resumeData = self.fileIO.loadResumeData()

        for i in range(1, max_sessions+1):
            self.freeSessions.append(str(i)) # all sessions are free by default
            self.transferInfo[str(i)] = {}
            self.transferInfo[str(i)]['rPath'] = ''
            self.transferInfo[str(i)]['progress'] = 0
            self.transferInfo[str(i)]['size'] = 0
            self.transferInfo[str(i)]['type'] = 0

            self.tHandler[str(i)] = TransferHandler(
                    telegram_channel_id, api_id, api_hash, data_path, tmp_path,
                    str(i), self.__saveProgress, self.__saveResumeData
            ) # initialize all sessions that will be used


    def __useSession(self, sFile=''): # Gets the first available session or the given one
        if not self.freeSessions:
            raise IndexError("No free sessions.")

        if sFile: # don't remove session because it was already removed in resumeHandler
            return sFile

        # get available session
        retSession = self.freeSessions[0]
        self.freeSessions.pop(0)
        return retSession


    def __freeSession(self, sFile=''):
        if not int(sFile) in range(1, self.max_sessions+1):
            raise IndexError("sFile should be between 1 and {}.".format(self.max_sessions))
        if sFile in self.freeSessions:
            raise ValueError("Can't free a session that is already free.")

        self.freeSessions.append(sFile)


    def __saveProgress(self, current, total, current_chunk, total_chunks, sFile):
        prg = int(((current/total/total_chunks)+(current_chunk/total_chunks))*100)
        self.transferInfo[sFile]['progress'] = prg


    def __saveResumeData(self, fileData, sFile):
        self.resumeData[sFile] = fileData
        self.fileIO.saveResumeData(fileData, sFile)


    def resumeHandler(self, sFile='', selected=0):
        if not int(sFile) in range(1, self.max_sessions+1):
            raise IndexError("sFile should be between 1 and {}.".format(self.max_sessions))

        if selected == 1: # Finish the transfer
            if self.resumeData[sFile]['handled'] != 2:
                self.freeSessions.remove(sFile) # if it was handled at startup as ignore
                                                # the session was already removed

            self.resumeData[sFile]['handled'] = 1
            self.transferInThread(self.resumeData[sFile], sFile)

        elif selected == 2: # Ignore for now
            self.resumeData[sFile]['handled'] = 2
            self.freeSessions.remove(sFile)	# prevent using this session for transfer

        elif selected == 3: # delete the resume file
            rmIDs = self.resumeData[sFile]['fileID']
            self.resumeData[sFile] = {} # not possible to resume later
            self.fileIO.delResumeData(sFile)
            self.cleanTg(rmIDs)


    def cleanTg(self, IDList=[]):
        sFile = self.__useSession()
        mode = 2

        if not IDList:
            mode = 1
            for i in self.fileDatabase:
                for j in i['fileID']:
                    IDlist.append(j)

        self.tHandler[sFile].deleteUseless(IDList, mode)
        self.__freeSession(sFile)


    def deleteInDatabase(self, fileData={}):
        if (not fileData) or not (type(fileData) is dict):
            raise TypeError("Bad or empty value given.")

        self.fileDatabase.remove(fileData)
        self.cleanTg(fileData['fileID'])
        self.fileIO.updateDatabase(self.fileDatabase)


    def renameInDatabase(self, fileData={}, newName=[]):
        if (
                (not fileData) or not (type(fileData) is dict) or
                (not newName) or not (type(newName) is list)
           ):
            raise TypeError("Bad or empty value given.")

        self.fileDatabase[self.fileDatabase.index(fileData)]['rPath'] = newName
        self.fileIO.updateDatabase(self.fileDatabase)


    def _upload(self, fileData, sFile):
        sFile = self.__useSession(sFile) # Use a free session
        if self.resumeData[sFile] and self.resumeData[sFile]['handled'] in [0, 2]:
            raise ValueError("Resume sessions not handled, refusing to transfer.")

        self.transferInfo[sFile]['rPath'] = fileData['rPath']
        self.transferInfo[sFile]['progress'] = 0
        self.transferInfo[sFile]['size'] = fileData['size']
        self.transferInfo[sFile]['type'] = 1

        if not fileData['index']: # not resuming
            fileData['index'] = self.fileIO.loadIndexData(sFile)

        finalData = self.tHandler[sFile].uploadFiles(fileData)

        if finalData: # Finished uploading
            if len(finalData['fileData']['fileID']) > 1: # not single chunk
                self.fileIO.delResumeData(sFile)

            self.fileIO.saveIndexData(sFile, finalData['index'])

            # This could be slow, a faster alternative is bisect.insort,
            # howewer, I couldn't find a way to sort by an item in dictionary
            self.fileDatabase.append(finalData['fileData'])
            self.fileDatabase.sort(key=itemgetter('rPath'))

            self.fileIO.updateDatabase(self.fileDatabase)

        else:
            self.resumeData[sFile]['handled'] = 0

        self.transferInfo[sFile]['type'] = 0 # not transferring anything
        self.__freeSession(sFile)


    def _download(self, fileData, sFile):
        sFile = self.__useSession(sFile) # Use a free session
        if self.resumeData[sFile] and self.resumeData[sFile]['handled'] in [0, 2]:
            raise ValueError("Resume sessions not handled, refusing to transfer.")

        self.transferInfo[sFile]['rPath'] = fileData['rPath']
        self.transferInfo[sFile]['progress'] = 0
        self.transferInfo[sFile]['size'] = fileData['size']
        self.transferInfo[sFile]['type'] = 2

        finalData = self.tHandler[sFile].downloadFiles(fileData)

        if finalData: # finished downloading
            if len(fileData['fileID']) > 1:
                self.fileIO.delResumeData(sFile)

        else:
            self.resumeData[sFile]['handled'] = 0

        self.transferInfo[sFile]['type'] = 0
        self.__freeSession(sFile)

        return finalData


    def transferInThread(self, fileData={}, sFile=''):
        if (not fileData) or not (type(fileData) is dict):
            raise TypeError("Bad or empty value given.")

        if fileData['type'] == 1:
            threadTarget = self._upload
        elif fileData['type'] == 2:
            threadTarget = self._download

        transferJob = threading.Thread(target=threadTarget, args=(fileData,sFile,), daemon=True)
        transferJob.start()


    def cancelTransfer(self, sFile=''):
        if not int(sFile) in range(1, self.max_sessions+1):
            raise IndexError("sFile should be between 1 and {}.".format(self.max_sessions))

        if self.tHandler[sFile].should_stop:
            raise ValueError("Transfer already cancelled.")

        self.resumeData[sFile]['handled'] = 0

        self.tHandler[sFile].stop(1)


    def endSessions(self):
        for i in range(1, self.max_sessions+1):
            self.tHandler[str(i)].endSession()
