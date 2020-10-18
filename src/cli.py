import urwid
import os
import weakref
import asyncio

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


class MenuButton(urwid.Button):
    def __init__(self, caption, on_press=None, user_data=None):
        super().__init__(caption, on_press, user_data)
        self._w = urwid.AttrMap(urwid.SelectableIcon(caption), None, 'reversed')


class UserInterface(SessionsHandler):
    def __init__(self):
        super().__init__()

        self.notifInfo = {'buffer': '', 'timer': 0, 'endTimer': 6}

        self.loop = asyncio.get_event_loop()

        self.main_widget = self.build_main_widget()
        self.upload_widget = self.build_upload_widget()
        self.download_widget = self.build_download_widget()

        self.mainKeyList = [{'keybind' : self.fileIO.cfg['keybinds']['upload'],
                             'widget' : self.upload_widget,
                             'input' : self.handle_keys_null},

                            {'keybind' : self.fileIO.cfg['keybinds']['download'],
                             'widget' : self.download_widget,
                             'input' : self.handle_keys_download}]

        palette = [('boldtext', 'default,bold', 'default', 'bold'), ('reversed', 'standout', '')]

        self.urwid_loop = urwid.MainLoop(
            widget=self.main_widget,
            palette=palette,
            handle_mouse=False,
            unhandled_input=self.handle_keys_main,
            event_loop=urwid.AsyncioEventLoop(loop=self.loop)
        )
        self.urwid_loop.run()


    def build_main_widget(self):
        def update_info(used_sessions_ref, notif_text_ref, transfer_info_ref):
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
                    local_notif_text.set_text(self.notifInfo['buffer'])
                self.notifInfo['timer'] += 1
                if self.notifInfo['timer'] == self.notifInfo['endTimer']:
                    local_notif_text.set_text('')
                    self.notifInfo['timer'] = 0
                    self.notifInfo['buffer'] = ''

            local_transfer_info.contents = []

            for sFile, info in self.transferInfo.items():
                if not info['type']: # empty
                    continue

                label = "{}\n{}\n{}% - {}".format(
                    "Uploading:" if info['type'] == 'upload' else "Downloading:",
                    '/'.join(info['rPath']),
                    info['progress'], bytesConvert(info['size'])
                )

                button = urwid.Button(
                    label,
                    self.cancel_in_loop,
                    {'sFile': sFile, 'info': info}
                )

                local_transfer_info.contents.append((urwid.AttrMap(button, None, focus_map='reversed'), pack_option))

            # Schedule to update the clock again in one second
            self.loop.call_later(1, update_info, used_sessions_ref, notif_text_ref, transfer_info_ref)

        title = urwid.Text("Telegram File Manager", align='center')
        used_sessions = urwid.Text('', align='right')
        transfer_info = urwid.Pile([])
        useless_button = urwid.Button("Current transfers")
        notif_text = urwid.Text('', align='center')
        custom_notif_text = urwid.AttrMap(notif_text, 'reversed')
        pack_option = transfer_info.options('pack', None)
        div = urwid.Divider()

        pile = urwid.Pile([title, used_sessions, urwid.Columns([useless_button, custom_notif_text], 1), div, transfer_info])

        update_info(weakref.ref(used_sessions), weakref.ref(notif_text), weakref.ref(transfer_info))

        return urwid.Filler(pile, 'top')


    def build_upload_widget(self):
        fpath = urwid.Edit(('boldtext', "File Path:\n"))
        rpath = urwid.Edit(('boldtext', "Relative Path:\n"))

        upload = urwid.Button("Upload", self.upload_in_loop,
            {'path' : weakref.ref(fpath), 'rPath' : weakref.ref(rpath)})
        cancel = urwid.Button("Cancel", self.return_to_main)

        div = urwid.Divider()
        pile = urwid.Pile([fpath, div, rpath, div,
                           urwid.AttrMap(upload, None, focus_map='reversed'),
                           urwid.AttrMap(cancel, None, focus_map='reversed')])

        return urwid.Filler(pile, valign='top')


    def build_download_widget(self):
        body = []
        totalSize = 0

        for i in self.fileDatabase:
            totalSize += i['size']

            button = MenuButton("{}  {}".format(
                                    '/'.join(i['rPath']),
                                    bytesConvert(i['size'])
                                ))
            body.append(urwid.AttrMap(button, None, focus_map='reversed'))

        body.insert(0, urwid.Divider())
        body.insert(0, urwid.Text(
            "Enter to download, d to delete, r to rename - {} Total".format(
                bytesConvert(totalSize)
            )
        ))

        listBox = urwid.ListBox(urwid.SimpleFocusListWalker(body))
        return urwid.Padding(listBox, left=2, right=2)


    def handle_keys_main(self, key):
        if key == 'esc':
            self.endSessions()
            raise urwid.ExitMainLoop

        for i in self.mainKeyList:
            if key == i['keybind']:
                urwid.Button._command_map.restore_defaults()
                self.urwid_loop.widget = i['widget']
                self.urwid_loop.unhandled_input = i['input']
                break # don't check for other keys


    def handle_keys_download(self, key):
        if key == 'q':
            self.return_to_main()


    def handle_keys_null(self, key): pass


    def return_to_main(self, key = None):
        # Kinda bad solution, we can't have a button in main widget
        # that uses a different mapping
        urwid.Button._command_map[self.fileIO.cfg['keybinds']['cancel']] = 'activate'
        del urwid.Button._command_map['enter']
        del urwid.Button._command_map[' ']

        self.urwid_loop.widget = self.main_widget
        self.urwid_loop.unhandled_input = self.handle_keys_main


    def upload_in_loop(self, key, data):
        path = data['path']().edit_text
        rPath = data['rPath']().edit_text

        self.loop.create_task(self.upload({
             'rPath'      : rPath.split('/'),
             'path'       : path,
             'size'       : os.path.getsize(path),
             'fileID'     : [],
             'index'      : 0, # managed by transferHandler
             'chunkIndex' : 0,
             'handled'    : 0}))

        self.return_to_main()


    def cancel_in_loop(self, key, data):
        if data['info']['size'] <= self.chunkSize: # no chunks
            self.notifInfo['buffer'] = "Can't cancel single chunk transfers"
            return

        try:
            self.cancelTransfer(data['sFile'])
            self.notifInfo['buffer'] = "Transfer {} cancelled".format('/'.join(data['info']['rPath']))
        except ValueError:
            self.notifInfo['buffer'] = "Transfer already cancelled"


if __name__ == "__main__":
    ui = UserInterface()
