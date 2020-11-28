'''
Extends transferHandler by managing the database and adding support for multiple sessions
'''

from operator import itemgetter
import asyncio

from backend.transferHandler import TransferHandler
from backend.fileIO import FileIO

class SessionsHandler:
    def __init__(self, local_library: bool = True):
        self.fileIO = FileIO()

        self.tHandler = {}
        self.freeSessions = []
        self.transferInfo = {}
        self.fileDatabase = self.fileIO.loadDatabase()
        self.resumeData = self.fileIO.loadResumeData()

        for i in range(1, int(self.fileIO.cfg['telegram']['max_sessions'])+1):
            # set session as free only if there is no resume info for it
            if not self.resumeData[str(i)]:
                self.freeSessions.append(str(i))

            self.transferInfo[str(i)] = {}
            self.transferInfo[str(i)]['rPath'] = ''
            self.transferInfo[str(i)]['progress'] = 0
            self.transferInfo[str(i)]['size'] = 0
            self.transferInfo[str(i)]['type'] = None

            # initialize all sessions that will be used
            self.tHandler[str(i)] = TransferHandler(
                self.fileIO.cfg, str(i), self._saveProgress,
                self._saveResumeData, local_library)

        self.chunkSize = self.tHandler['1'].chunk_size


    async def initSessions(self):
        for i in range(1, int(self.fileIO.cfg['telegram']['max_sessions'])+1):
            await self.tHandler[str(i)].initSession()


    def _useSession(self, sFile: str = None):
        # Gets the first available session or the given one
        if sFile:
            # don't remove session because it was already removed in resumeHandler
            return sFile

        if not self.freeSessions:
            raise IndexError("No free sessions.")

        # get available session
        retSession = self.freeSessions[0]
        self.freeSessions.pop(0)
        return retSession


    def _freeSession(self, sFile: str):
        if not int(sFile) in range(1, int(self.fileIO.cfg['telegram']['max_sessions'])+1):
            raise IndexError("sFile should be between 1 and {}.".format(int(self.fileIO.cfg['telegram']['max_sessions'])))
        if sFile in self.freeSessions:
            raise ValueError("Can't free a session that is already free.")

        self.freeSessions.append(sFile)


    def _saveProgress(self, current, total, current_chunk, total_chunks, sFile):
        prg = int(((current/total/total_chunks)+(current_chunk/total_chunks))*100)
        self.transferInfo[sFile]['progress'] = prg


    def _saveResumeData(self, fileData: list, sFile: str):
        self.resumeData[sFile] = fileData
        self.fileIO.saveResumeData(fileData, sFile)


    async def resumeHandler(self, sFile: str, selected: int = 0):
        if not int(sFile) in range(1, int(self.fileIO.cfg['telegram']['max_sessions'])+1):
            raise IndexError("sFile should be between 1 and {}.".format(int(self.fileIO.cfg['telegram']['max_sessions'])))

        if selected == 1: # Finish the transfer
            if self.resumeData[sFile]['type'] == 'upload':
                await self.upload(self.resumeData[sFile], sFile)
            elif self.resumeData[sFile]['type'] == 'download':
                await self.download(self.resumeData[sFile], sFile)

        elif selected == 2: # Ignore for now
            # as the session is removed both after the end of a cancelled transfer
            # and at the beginning of the program this doesn't need to do anything
            pass

        elif selected == 3: # delete the resume file
            if self.resumeData[sFile]['type'] == 'upload':
                await self.cleanTg(self.resumeData[sFile]['fileID'])

            self._freeSession(sFile)

            self.resumeData[sFile] = {} # not possible to resume later
            self.fileIO.delResumeData(sFile)


    async def cleanTg(self, IDList: list = None):
        sFile = self._useSession()
        mode = 2

        if not IDList:
            mode = 1
            for i in self.fileDatabase:
                for j in i['fileID']:
                    IDlist.append(j)

        await self.tHandler[sFile].deleteUseless(IDList, mode)
        self._freeSession(sFile)


    async def deleteInDatabase(self, fileData: dict):
        self.fileDatabase.remove(fileData)
        await self.cleanTg(fileData['fileID'])
        self.fileIO.updateDatabase(self.fileDatabase)


    def renameInDatabase(self, fileData: dict, newName: list):
        self.fileDatabase[self.fileDatabase.index(fileData)]['rPath'] = newName
        self.fileIO.updateDatabase(self.fileDatabase)


    async def upload(self, fileData: dict, sFile: str = None):
        sFile = self._useSession(sFile) # Use a free session

        self.transferInfo[sFile]['rPath'] = fileData['rPath']
        self.transferInfo[sFile]['progress'] = 0
        self.transferInfo[sFile]['size'] = fileData['size']
        self.transferInfo[sFile]['type'] = 'upload'

        if not 'index' in fileData: # not resuming
            fileData['index'] = self.fileIO.loadIndexData(sFile)
            fileData['chunkIndex'] = 0
            fileData['fileID'] = []

        finalData = await self.tHandler[sFile].uploadFiles(fileData)

        self.transferInfo[sFile]['type'] = None # not transferring anything

        if finalData: # Finished uploading
            if len(finalData['fileData']['fileID']) > 1: # not single chunk
                self.fileIO.delResumeData(sFile)
                self.resumeData[sFile] = {}

            self.fileIO.saveIndexData(sFile, finalData['index'])

            # This could be slow, a faster alternative could be bisect.insort,
            # howewer, I couldn't find a way to sort by an item in dictionary
            self.fileDatabase.append(finalData['fileData'])
            self.fileDatabase.sort(key=itemgetter('rPath'))

            self.fileIO.updateDatabase(self.fileDatabase)
            self._freeSession(sFile)

        else: # cancelled
            await self.resumeHandler(sFile, 2)


    async def download(self, fileData: dict, sFile: str = None):
        sFile = self._useSession(sFile) # Use a free session

        self.transferInfo[sFile]['rPath'] = fileData['rPath']
        self.transferInfo[sFile]['progress'] = 0
        self.transferInfo[sFile]['size'] = fileData['size']
        self.transferInfo[sFile]['type'] = 'download'

        if not 'IDindex' in fileData:
            fileData['IDindex'] = 0

        finalData = await self.tHandler[sFile].downloadFiles(fileData)

        self.transferInfo[sFile]['type'] = None

        if finalData and len(fileData['fileID']) > 1: # finished downloading
            self.fileIO.delResumeData(sFile)
            self.resumeData[sFile] = {}
            self._freeSession(sFile)
        elif not finalData: # cancelled
            await self.resumeHandler(sFile, 2)

        return finalData


    async def cancelTransfer(self, sFile: str):
        if not int(sFile) in range(1, int(self.fileIO.cfg['telegram']['max_sessions'])+1):
            raise IndexError("sFile should be between 1 and {}.".format(int(self.fileIO.cfg['telegram']['max_sessions'])))

        await self.tHandler[sFile].stop(1)
