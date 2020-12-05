import configparser
import pickle
import os

class FileIO:
    def __init__(self):
        self.cfg = configparser.ConfigParser()

        if os.path.isfile(os.path.expanduser("~/.config/tgFileManager.ini")):
            self.cfg.read(os.path.expanduser("~/.config/tgFileManager.ini"))
        else:
            print("Config file not found, user input required for first time configuration.")
            self.cfg['telegram'] = {}
            self.cfg['telegram']['api_id'] = ''
            self.cfg['telegram']['api_hash'] = ''
            self.cfg['telegram']['channel_id'] = 'me'
            self.cfg['telegram']['max_sessions'] = '4'
            self.cfg['paths'] = {}
            self.cfg['paths']['data_path'] = os.path.expanduser("~/tgFileManager")
            self.cfg['paths']['tmp_path'] = os.path.expanduser("~/.tmp/tgFileManager")
            self.cfg['paths']['download_full_path'] = False
            self.cfg['keybinds'] = {}
            self.cfg['keybinds']['upload'] = 'u'
            self.cfg['keybinds']['download'] = 'd'
            self.cfg['keybinds']['resume'] = 'r'
            self.cfg['keybinds']['cancel'] = 'c'
            self.cfg['telegram']['api_id'] = input("api_id: ")
            self.cfg['telegram']['api_hash'] = input("api_hash: ")
            with open(os.path.expanduser("~/.config/tgFileManager.ini"), 'w') as f:
                self.cfg.write(f)

        for i in [os.path.join(self.cfg['paths']['data_path'], "downloads"),
                  os.path.join(self.cfg['paths']['tmp_path'], "tfilemgr")]:
            if not os.path.isdir(i):
                os.makedirs(i)


    def updateDatabase(self, fileDatabase: list):
        # This should be called after finishing an upload
        with open(os.path.join(self.cfg['paths']['data_path'], "fileData"), 'wb') as f:
            pickle.dump(fileDatabase, f)


    def loadDatabase(self) -> list:
        fileDatabase = []

        if os.path.isfile(os.path.join(self.cfg['paths']['data_path'], "fileData")):
            with open(os.path.join(self.cfg['paths']['data_path'], "fileData"), 'rb') as f:
                fileDatabase = pickle.load(f)

        return fileDatabase


    def saveResumeData(self, fileData: dict, sFile: str):
        with open(os.path.join(self.cfg['paths']['data_path'], "resume_{}".format(sFile)), 'wb') as f:
            pickle.dump(fileData, f)


    def loadResumeData(self) -> dict:
        resumeData = {}

        for i in range(1, int(self.cfg['telegram']['max_sessions'])+1):
            fileData = {}
            if os.path.isfile(os.path.join(self.cfg['paths']['data_path'], "resume_{}".format(i))):
                with open(os.path.join(self.cfg['paths']['data_path'], "resume_{}".format(i)), 'rb') as f:
                    fileData = pickle.load(f)

            resumeData[str(i)] = fileData

        return resumeData


    def delResumeData(self, sFile: str):
        os.remove(os.path.join(self.cfg['paths']['data_path'], "resume_{}".format(sFile)))


    def loadIndexData(self, sFile: str) -> int:
        indexData = 1

        if os.path.isfile(os.path.join(self.cfg['paths']['data_path'], "index_{}".format(sFile))):
            with open(os.path.join(self.cfg['paths']['data_path'], "index_{}".format(sFile)), 'rb') as f:
                indexData = pickle.load(f)

        return indexData


    def saveIndexData(self, sFile: str, index: int):
        with open(os.path.join(self.cfg['paths']['data_path'], "index_{}".format(sFile)), 'wb') as f:
            pickle.dump(index, f)
