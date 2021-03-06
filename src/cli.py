import urwid
import os
import weakref
import asyncio
import sys

from backend.sessionsHandler import SessionsHandler


def bytesConvert(rawBytes: int) -> str:
    if   rawBytes >= 16**10:
        return "{} TiB".format(round(rawBytes/16**10, 2))
    elif rawBytes >= 8**10:
        return "{} GiB".format(round(rawBytes/8**10, 2))
    elif rawBytes >= 4**10:
        return "{} MiB".format(round(rawBytes/4**10, 2))
    elif rawBytes >= 2**10:
        return "{} KiB".format(round(rawBytes/2**10, 2))
    else:
        return "{} Bytes".format(rawBytes)


class CustomButton(urwid.Button):
    signals = ['click', 'cancel', 'delete', 'rename']

    def __init__(self, caption, actionDict = None, info = None):
        super().__init__(caption)

        self._w = urwid.AttrMap(urwid.SelectableIcon(caption), None, 'reversed')
        self.actionDict = actionDict

        if info:
            self.info = info

    def keypress(self, size, key):
        if key in self.actionDict:
            self._emit(self.actionDict[key])
        else:
            return key


class CustomColumns(urwid.Columns):
    def __init__(self, widget_list, dividechars = 0, info = None):
        super().__init__(widget_list, dividechars)
        if info:
            self.info = info


class UserInterface(SessionsHandler):
    def __init__(self):
        super().__init__(False if (len(sys.argv) > 1 and sys.argv[1] == '1') else True)

        self.notifInfo = {'buffer': '', 'timer': 0, 'endTimer': 6}

        self.loop = asyncio.get_event_loop()

        self.loop.create_task(self.initSessions())

        self.main_widget = self.build_main_widget()

        self.mainKeyList = [{'keybind' : self.fileIO.cfg['keybinds']['upload'],
                             'widget' : self.build_upload_widget,
                             'input' : self.handle_keys_null},

                            {'keybind' : self.fileIO.cfg['keybinds']['download'],
                             'widget' : self.build_download_widget,
                             'input' : self.handle_keys_download},

                            {'keybind' : self.fileIO.cfg['keybinds']['resume'],
                             'widget' : self.build_resume_widget,
                             'input' : self.handle_keys_null}]

        palette = [('boldtext', 'default,bold', 'default', 'bold'), ('reversed', 'standout', '')]

        self.urwid_loop = urwid.MainLoop(
            widget=self.main_widget,
            palette=palette,
            handle_mouse=False,
            unhandled_input=self.handle_keys_main,
            event_loop=urwid.AsyncioEventLoop(loop=self.loop)
        )


    def notification(self, inStr: str):
        self.notifInfo['buffer'] = inStr
        self.notifInfo['timer'] = 0


    def change_widget(self, widget, unhandled_input, user_args: dict = None, key = None):
        """
        This function creates the given widget giving it the args it received,
        then it sets urwid_loop's widget and unhandled_input to the ones received

        This function is mainly used by urwid.Button signal callback as it can have only one callback function
        """

        # Conditionally set argument
        fun_kwargs = user_args if user_args else {}

        self.urwid_loop.widget = widget(**fun_kwargs)
        self.urwid_loop.unhandled_input = unhandled_input


    def build_main_widget(self):
        def update_info(used_sessions_ref, notif_text_ref,
                        transfer_info_ref):
            local_used_sessions = used_sessions_ref()
            local_notif_text = notif_text_ref()
            local_transfer_info = transfer_info_ref()

            if not local_used_sessions or not local_notif_text or not local_transfer_info:
                # widget is dead, the main loop must've been destroyed
                return

            local_used_sessions.set_text("[ {} of {} ]".format(int(self.fileIO.cfg['telegram']['max_sessions']) - len(self.freeSessions),
                                                               int(self.fileIO.cfg['telegram']['max_sessions'])))

            if self.notifInfo['buffer']:
                if not self.notifInfo['timer']: # new notification
                    local_notif_text.set_text(('reversed', self.notifInfo['buffer']))
                self.notifInfo['timer'] += 1
                if self.notifInfo['timer'] == self.notifInfo['endTimer']:
                    local_notif_text.set_text('')
                    self.notifInfo['timer'] = 0
                    self.notifInfo['buffer'] = ''

            # Delete finished transfers
            # There is a chance that the transfer doesn't get deleted when it should
            # if we add another transfer that uses the same session file
            # inbetween the runs of this loop
            # In that case, the label of this button would just get updated along
            # with the progress update of the other transfers

            local_transfer_info.contents[:] = [x for x in local_transfer_info.contents
                if self.transferInfo[x[0].info['sFile']]['type']]

            # Update progress, doesn't work
            #for i, widget in enumerate(local_transfer_info.contents):
            #    currentTransfer = self.transferInfo[widget[0].info['sFile']]

            #    label = "{}\n{}\n{}% - {}".format(
            #        "Uploading:" if currentTransfer['type'] == 'upload' else "Downloading:",
            #        '/'.join(currentTransfer['rPath']),
            #        currentTransfer['progress'], bytesConvert(currentTransfer['size'])
            #    )

            #    local_transfer_info[i].set_label(label) # the label gets updated but doesn't get shown on screen

            # Add new transfers
            for sFile, info in self.transferInfo.items():
                # If the transfer does not exist in local_transfer_info add it
                if info['type'] and sFile not in [x[0].info['sFile']
                                                  for x in local_transfer_info.contents]:
                    label = "{}\n{}\n{}".format(
                        "Uploading:" if info['type'] == 'upload' else "Downloading:",
                        '/'.join(info['rPath']),
                        bytesConvert(info['size'])
                    )

                    button = CustomButton(label,
                        {self.fileIO.cfg['keybinds']['cancel']: 'cancel'},
                        {'sFile': sFile})

                    urwid.connect_signal(button, 'cancel', self.cancel_in_loop,
                        user_args=[sFile, info['size'], info['rPath']]
                    )

                    local_transfer_info.contents.append((button, pack_option))

            # Schedule to update the clock again in one second
            self.loop.call_later(1, update_info, used_sessions_ref,
                                 notif_text_ref, transfer_info_ref)

        title = urwid.Text("Telegram File Manager", align='center')
        used_sessions = urwid.Text('', align='right')
        transfer_info = urwid.Pile([])
        useless_button = urwid.Button("Current transfers")
        notif_text = urwid.Text('', align='center')
        pack_option = transfer_info.options('pack', None)
        div = urwid.Divider()

        pile = urwid.Pile([title, used_sessions, urwid.Columns([useless_button, ('weight', 3, notif_text)], 1), div, transfer_info])

        update_info(weakref.ref(used_sessions), weakref.ref(notif_text), weakref.ref(transfer_info))

        return urwid.Filler(pile, 'top')


    def build_upload_widget(self):
        fpath = urwid.Edit(('boldtext', "File Path:\n"))
        rpath = urwid.Edit(('boldtext', "Relative Path:\n"))

        upload = urwid.Button("Upload")
        urwid.connect_signal(upload, 'click', self.upload_in_loop,
            weak_args=[fpath, rpath])

        cancel = urwid.Button("Cancel", self.return_to_main)

        div = urwid.Divider()
        pile = urwid.Pile([fpath, div, rpath, div,
                           urwid.AttrMap(upload, None, focus_map='reversed'),
                           urwid.AttrMap(cancel, None, focus_map='reversed')])

        return urwid.Filler(pile, 'top')


    def build_download_widget(self):
        totalSize = 0

        dpath = urwid.Edit(('boldtext', "Download path: "),
            os.path.join(self.fileIO.cfg['paths']['data_path'], 'downloads'))

        body = [dpath, urwid.Divider()]

        for i in self.fileDatabase:
            totalSize += i['size']

            button = CustomButton("{}  {}".format(
                                    '/'.join(i['rPath']),
                                    bytesConvert(i['size'])),
                                  {'enter' : 'click',
                                   'd'     : 'delete',
                                   'r'     : 'rename'})

            urwid.connect_signal(button, 'click', self.download_in_loop,
                weak_args=[dpath],
                user_args=[i['rPath'], i['fileID'], i['size']]
            )

            fileData_tmp = {'fileData': {'rPath': i['rPath'], 'fileID': i['fileID'], 'size': i['size']}}

            urwid.connect_signal(button, 'rename', self.change_widget,
                user_args=[self.build_rename_widget, self.handle_keys_null,
                           fileData_tmp]
            )

            urwid.connect_signal(button, 'delete', self.change_widget,
                user_args=[self.build_delete_widget, self.handle_keys_null,
                           fileData_tmp]
            )

            body.append(button)

        body.insert(0, urwid.Text(
            ('reversed', "Enter to download, d to delete, r to rename - {} Total".format(
                bytesConvert(totalSize)
            ))
        ))

        listBox = urwid.ListBox(urwid.SimpleFocusListWalker(body))
        return urwid.Padding(listBox, left=2, right=2)


    def build_resume_widget(self):
        """
        Widget that shows unfinished transfers and prompts the user
        to either resume, ignore or delete each of the transfers.

        When one of these actions is selected for a transfer, that
        transfer gets removed from the widget so that the user can't
        select multiple actions for a transfer.
        """

        title = urwid.Button(('boldtext', "Cancelled transfers:"))
        div = urwid.Divider()

        pile = urwid.Pile([title, div])
        pack_option = pile.options('pack', None)

        for sFile, info in self.resumeData.items():
            if info and not self.transferInfo[sFile]['type']:
                # has resume data that wasn't handled
                transfer_name = urwid.Text("Session {}, '{}' - {}:".format(sFile,
                    '/'.join(info['rPath']), bytesConvert(info['size'])))

                resume = urwid.Button("Resume")
                urwid.connect_signal(resume, 'click', self.resume_in_loop,
                                     weak_args=[pile],
                                     user_args=[sFile, 1]
                )

                ignore = urwid.Button("Ignore")
                urwid.connect_signal(ignore, 'click', self.resume_in_loop,
                                     weak_args=[pile],
                                     user_args=[sFile, 2]
                )

                delete = urwid.Button("Delete")
                urwid.connect_signal(delete, 'click', self.resume_in_loop,
                                     weak_args=[pile],
                                     user_args=[sFile, 3]
                )

                option_pile = urwid.Pile([urwid.AttrMap(resume, None, focus_map='reversed'),
                                          urwid.AttrMap(ignore, None, focus_map='reversed'),
                                          urwid.AttrMap(delete, None, focus_map='reversed')])

                transfer_columns = CustomColumns([('weight', 4, transfer_name),
                                                  ('weight', 1, option_pile)], 1,
                                                 {'sFile': sFile})

                pile.contents.append((transfer_columns, pack_option))
                pile.contents.append((div, pack_option))

        if len(pile.contents) == 2:
            self.notification("No resume information")
            # the function that called this function always expects it to
            # return a widget, that's why we can't use return_to_main
            self.urwid_loop.unhandled_input = self.handle_keys_main
            return self.main_widget

        pile.contents.append((urwid.Button("Done", self.return_to_main), pack_option))

        return urwid.Filler(pile, 'top')


    def build_rename_widget(self, fileData):
        newName = urwid.Edit(('boldtext', "Rename {}:\n".format(
            '/'.join(fileData['rPath']))))

        rename = urwid.Button("Rename")
        urwid.connect_signal(rename, 'click', self.rename_in_loop, weak_args=[newName], user_args=[fileData])

        cancel = urwid.Button("Cancel", self.return_to_main)

        div = urwid.Divider()
        pile = urwid.Pile([newName, div,
                           urwid.AttrMap(rename, None, focus_map='reversed'),
                           urwid.AttrMap(cancel, None, focus_map='reversed')])

        return urwid.Filler(pile, 'top')


    def build_delete_widget(self, fileData):
        confirm_text = urwid.Text(('boldtext', "Are you sure you want to delete {}?".format(
            '/'.join(fileData['rPath']))))

        delete = urwid.Button("Delete")
        urwid.connect_signal(delete, 'click', self.delete_in_loop, user_args=[fileData])

        cancel = urwid.Button("Cancel", self.return_to_main)

        div = urwid.Divider()
        pile = urwid.Pile([confirm_text, div,
                           urwid.AttrMap(cancel, None, focus_map='reversed'),
                           urwid.AttrMap(cancel, None, focus_map='reversed'),
                           urwid.AttrMap(delete, None, focus_map='reversed'),
                           urwid.AttrMap(cancel, None, focus_map='reversed')])

        return urwid.Filler(pile, 'top')


    def handle_keys_main(self, key):
        if key == 'esc':
            raise urwid.ExitMainLoop

        for i in self.mainKeyList:
            if key == i['keybind']:
                self.urwid_loop.unhandled_input = i['input']
                self.urwid_loop.widget = i['widget']() # build widget everytime
                break # don't check for other keys


    def handle_keys_download(self, key):
        if key == 'q':
            self.return_to_main()


    def handle_keys_null(self, key): pass


    def return_to_main(self, key = None):
        self.urwid_loop.widget = self.main_widget
        self.urwid_loop.unhandled_input = self.handle_keys_main


    def upload_in_loop(self, path, rPath, key):
        path_str = path.edit_text
        rPath_str = rPath.edit_text

        if not self.freeSessions:
            self.notification("All sessions are currently used")
        elif not path_str or not rPath_str:
            self.notification("Please enter all info")
        elif not os.path.isfile(path_str):
            self.notification("There is no file with this path")
        else:
            self.loop.create_task(self.upload({
                'rPath'   : rPath_str.split('/'),
                'path'    : path_str,
                'size'    : os.path.getsize(path_str),
                'type'    : 'upload'
            }))

        self.return_to_main()


    def download_in_loop(self, dPath, rPath, fileID, size, key):
        if not self.freeSessions:
            self.notification("All sessions are currently used")
        else:
            self.loop.create_task(self.download({
                'rPath'   : rPath,
                'dPath'   : dPath.edit_text,
                'fileID'  : fileID,
                'size'    : size,
                'type'    : 'download'
            }))

        self.return_to_main()


    def resume_in_loop(self, pile_widget, sFile, selected, key):
        self.loop.create_task(self.resumeHandler(sFile, selected))

        # Remove current transfer from pile_widget but don't delete other widgets
        pile_widget.contents[:] = [x for x in pile_widget.contents
            if type(x[0]) != CustomColumns or x[0].info['sFile'] != sFile]
        pile_widget.focus_position = 0


    def rename_in_loop(self, rename_widget, fileData, key):
        self.renameInDatabase(fileData, rename_widget.edit_text.split('/'))
        self.return_to_main()


    def delete_in_loop(self, fileData, key):
        self.loop.create_task(self.deleteInDatabase(fileData))
        self.return_to_main()


    def cancel_in_loop(self, sFile, size, rPath, key):
        if size <= self.chunkSize: # no chunks
            self.notification("Can't cancel single chunk transfers")
        elif self.tHandler[sFile].should_stop:
            self.notification("Transfer already cancelled")
        else:
            asyncio.create_task(self.cancelTransfer(sFile))
            self.notification("Transfer {} cancelled".format('/'.join(rPath)))


if __name__ == "__main__":
    ui = UserInterface()
    ui.urwid_loop.run()
