'''
The files uploaded to telegram will have this naming convention:
[s_file]_[index]  example: 1_3128

The maximum filename length for a file is 64 ASCII chars (for telegram)
2 chars will be allocated for the session file part

This means that we have 10^62 filenames possible with only digits
(for each session file)

Don't upload files that are in the same directory as data_path

The path of the uploaded file should only have ASCII characters,
because the string is transmitted to a C function

Due to how files are downloaded, downloading 2 files with the same name
(not path) at the same time will cause problems.

Also when a file with same name as one of previous files has been downloaded
then the original file will be replaced. (If the original has not been moved)
'''

from ctypes import *
from pyrogram import Client
import threading
import asyncio
from shutil import copyfile
from os import remove, path
import sys

class TransferHandler:
    def __init__(self,
                 config: dict,
                 s_file: str,
                 progress_fun: callable, # Pointer to progress function
                 data_fun: callable, # Called for multi chunk transfers
                 local_library: bool = True): # Where to search for library

        libPath = "{}transferHandler_extern.{}".format('' if local_library else '../', 'dll' if sys.platform == 'win32' else 'so')
        self.extern = CDLL(libPath)
        self.extern.splitFile.restype = c_size_t
        self.extern.splitFile.argtypes = [c_size_t, c_char_p, c_char_p,
                                          c_size_t, c_size_t]

        self.extern.concatFiles.restype = c_char
        self.extern.concatFiles.argtypes = [c_char_p, c_char_p, c_size_t]

        try:
            self.telegram_channel_id = int(config['telegram']['channel_id'])
        except ValueError:
            self.telegram_channel_id = config['telegram']['channel_id']

        self.data_path = config['paths']['data_path']
        self.tmp_path = config['paths']['tmp_path']
        self.s_file = s_file # we need this for the naming when uploading
        self.progress_fun = progress_fun
        self.data_fun = data_fun
        self.now_transmitting = 0 # no, single chunk, multi chunk (0-2)
        self.should_stop = 0

        self.chunk_size = 2000*1024*1024
        self.mul_chunk_size = 2000*1024

        self.telegram = Client(path.join(self.data_path, "a{}".format(s_file)),
                               config['telegram']['api_id'], config['telegram']['api_hash'])
        # Connect to telegram servers when starting
        # So that if we are missing any sessions it will prompt for login
        # Before starting the UI
        self.telegram.start()

    async def extern_concatFiles(self,
                                 filePath: str,
                                 outFileName: str):

        threadJob = threading.Thread(target=self.extern.concatFiles,
                                     args=(filePath.encode('ascii'),
                                           outFileName.encode('ascii'),
                                           1024,))
        threadJob.start()

        while True:
            await asyncio.sleep(1)
            if not threadJob.isAlive():
                break



    def uploadFiles(self, fileData: dict):
        if fileData['size'] <= self.chunk_size: # don't split file
            # Single chunk upload doesn't call data_fun
            copied_file_path = path.join(self.tmp_path, "tfilemgr",
                "{}_{}".format(self.s_file, fileData['index']))

            copyfile(fileData['path'], copied_file_path)

            self.now_transmitting = 1

            msg_obj = self.telegram.send_document(
                    self.telegram_channel_id, copied_file_path,
                    progress=self.progress_fun,
                    progress_args=(0, 1, self.s_file) # 0 out of 1 chunks
                )

            self.now_transmitting = 0

            # Canceling with 1 makes no sense for single chunk transmission
            if self.should_stop == 2:
                self.should_stop = 0
                return

            remove(copied_file_path) # finished uploading, delete file

            # return file information
            return {'fileData' : {'rPath'  : fileData['rPath'],
                                  'fileID' : [msg_obj.message_id],
                                  'size'   : fileData['size']},
                    'index'    : fileData['index']+1}

        # else file should be split
        tot_chunks = (fileData['size'] // self.chunk_size) + 1 # used by progress fun

        self.now_transmitting = 2
        while True: # not end of file
            copied_file_path = path.join(self.tmp_path, "tfilemgr",
                "{}_{}".format(self.s_file, fileData['index']))

            fileData['chunkIndex'] = self.extern.splitFile(
                fileData['chunkIndex'],
                fileData['path'].encode('ascii'),
                copied_file_path.encode('ascii'),
                self.mul_chunk_size, 1024
            )

            msg_obj = self.telegram.send_document(
                    self.telegram_channel_id,
                    copied_file_path,
                    progress=self.progress_fun,
                    progress_args=(len(fileData['fileID']), tot_chunks,
                                   self.s_file)
            )

            remove(copied_file_path) # delete the chunk

            if self.should_stop == 2: # force stop
                break

            fileData['fileID'].append(msg_obj.message_id)
            fileData['index'] += 1

            if not fileData['chunkIndex']: # reached EOF
                break

            self.data_fun(fileData, self.s_file)

            if self.should_stop == 1:
                break

        self.now_transmitting = 0
        self.should_stop = 0 # Set this to 0 no matter what

        if not fileData['chunkIndex']: # finished uploading
            return {'fileData' : {'rPath'  : fileData['rPath'],
                                  'fileID' : fileData['fileID'],
                                  'size'   : fileData['size']},
                    'index'    : fileData['index']}
            # return file information


    def downloadFiles(self, fileData: dict):
        if fileData['dPath']:
            copied_file_path = path.join(fileData['dPath'],
                                         fileData['rPath'][-1])
        else:
            copied_file_path = path.join(self.data_path, "downloads",
                                         fileData['rPath'][-1])

        if len(fileData['fileID']) == 1: # no chunks
            # Single chunk download doesn't call data_fun
            self.now_transmitting = 1

            self.telegram.get_messages(self.telegram_channel_id,
                                       fileData['fileID'][0]).download(
                file_name=copied_file_path,
                progress=self.progress_fun,
                progress_args=(0, 1, self.s_file) # 0 out of 1 chunks
            )

            self.now_transmitting = 0

            if self.should_stop == 2:
                self.should_stop = 0
                return 0

            return 1

        # else has chunks
        tmp_file_path = path.join(self.tmp_path, "tfilemgr",
                                  "{}_chunk".format(fileData['rPath'][-1]))

        self.now_transmitting = 2
        while fileData['IDindex'] < len(fileData['fileID']):
            self.telegram.get_messages(self.telegram_channel_id,
                                       fileData['fileID'][fileData['IDindex']]
                                       ).download(
                    file_name=tmp_file_path,
                    progress=self.progress_fun,
                    progress_args=(fileData['IDindex'], len(fileData['fileID']),
                                   self.s_file)
            )

            if self.should_stop == 2:
                break

            fileData['IDindex']+=1

            self.extern.concatFiles(
                tmp_file_path.encode('ascii'),
                copied_file_path.encode('ascii'),
                1024
            )

            remove(tmp_file_path)

            if fileData['IDindex'] == len(fileData['fileID']):
                # finished or canceled with 1 but it was last chunk
                self.should_stop = 0 # download finished
                break

            # stores only ids of files that haven't yet been downloaded
            self.data_fun(fileData, self.s_file)

            if self.should_stop == 1:
                # issued normal cancel
                break

        self.now_transmitting = 0

        if self.should_stop:
            self.should_stop = 0 # don't confuse future transfers
            return 0

        return 1


    def deleteUseless(self, IDList: list, mode: int = 1):
        # mode is 1 for enerything except IDList,
        #         2 for only IDList
        deletedList = []

        if mode == 1:
            for tFile in self.telegram.iter_history(self.telegram_channel_id):
                if (tFile.media) and (not tFile.message_id in IDList):
                    deletedList.append(tFile.message_id)

            if deletedList:
                self.telegram.delete_messages(self.telegram_channel_id,
                                              deletedList)

        elif mode == 2:
            self.telegram.delete_messages(self.telegram_channel_id, IDList)

        return deletedList

    def stop(self, stop_type: int):
        #Values of stop_type:
        #1 - Wait until the current chunk transfer ended and appended
        #2 - Cancel transfer, will still wait for appending to finish
        if not stop_type in [1, 2]:
            raise IndexError("stop_type should be 1 or 2.")
        if self.now_transmitting == 1 and stop_type == 1:
            raise IndexError("stop_type can't be 1 when transmitting single chunk files.")

        self.should_stop = stop_type
        if stop_type == 2: #force stop
            self.telegram.stop_transmission()


    def endSession(self):
        self.telegram.stop()
