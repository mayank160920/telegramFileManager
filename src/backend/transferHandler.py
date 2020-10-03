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

from pyrogram import Client
import asyncio
from shutil import copyfile
from os import path
import sys
from backend.asyncFiles import AsyncFiles


class TransferHandler:
    def __init__(self,
                 config: dict,
                 s_file: str,
                 progress_fun: callable, # Pointer to progress function
                 data_fun: callable, # Called for multi chunk transfers
                 local_library: bool = True): # Where to search for library

        self.asyncFiles = AsyncFiles(
            "{}transferHandler_extern.{}".format('' if local_library else '../',
            'dll' if sys.platform == 'win32' else 'so'))

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

        self.mul_chunk_size = 2000*1024
        self.chunk_size = self.mul_chunk_size * 1024

        self.telegram = Client(path.join(self.data_path, "a{}".format(s_file)),
                               config['telegram']['api_id'], config['telegram']['api_hash'])
        # Connect to telegram servers when starting
        # So that if we are missing any sessions it will prompt for login
        # Before starting the UI
        self.telegram.start()


    async def uploadFiles(self, fileData: dict):
        tot_chunks = (fileData['size'] // self.chunk_size) + 1 # used by progress fun
        self.now_transmitting = 1 if fileData['size'] <= self.chunk_size else 2

        while True: # not end of file
            if self.now_transmitting == 2:
                copied_file_path = path.join(self.tmp_path, "tfilemgr",
                    "{}_{}".format(self.s_file, fileData['index']))

                fileData['chunkIndex'] = await self.asyncFiles.splitFile(
                    fileData['chunkIndex'],
                    fileData['path'].encode('ascii'),
                    copied_file_path.encode('ascii'),
                    self.mul_chunk_size, 1024
                )

            msg_obj = await self.telegram.send_document(
                    self.telegram_channel_id,
                    copied_file_path if self.now_transmitting == 2 else \
                        fileData['path'],
                    file_name = None if self.now_transmitting == 2 else \
                        "{}_{}".format(self.s_file, fileData['index']),
                    progress=self.progress_fun,
                    progress_args=(len(fileData['fileID']), tot_chunks,
                                   self.s_file)
            )

            if self.now_transmitting == 2:
                await self.asyncFiles.remove(copied_file_path)
                # delete the chunk

            if self.should_stop == 2: # force stop
                if self.now_transmitting == 1:
                    self.should_stop = 0
                    return
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


    async def downloadFiles(self, fileData: dict):
        self.now_transmitting = 1 if fileData['size'] <= self.chunk_size else 2

        final_file_path = path.join(fileData['dPath'], fileData['rPath'][-1]) if fileData['dPath'] else \
                          path.join(self.data_path, "downloads", fileData['rPath'][-1])
        tmp_file_path = path.join(self.tmp_path, "tfilemgr",
                                  "{}_chunk".format(fileData['rPath'][-1]))

        while fileData['IDindex'] < len(fileData['fileID']):
            await self.telegram.get_messages(self.telegram_channel_id,
                                             fileData['fileID'][fileData['IDindex']]
                                             ).download(
                    file_name=final_file_path if self.now_transmitting == 1 else tmp_file_path,
                    progress=self.progress_fun,
                    progress_args=(fileData['IDindex'], len(fileData['fileID']),
                                   self.s_file)
            )

            if self.should_stop == 2: # force stop
                break

            fileData['IDindex']+=1

            if self.now_transmitting == 2:
                await self.asyncFiles.concatFiles(
                    tmp_file_path,
                    copied_file_path,
                    1024
                )
                await self.asyncFiles.remove(tmp_file_path)

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
