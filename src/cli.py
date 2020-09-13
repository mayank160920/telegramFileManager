import urwid
import os
import weakref
import asyncio

import misc
from backend.sessionsHandler import SessionsHandler

class UserInterface():
    def __init__(self):
        self.cfg = misc.loadConfig()
        self.progress_info = "1"

        try:
            realChannelID = int(self.cfg['telegram']['channel_id'])
        except ValueError:
            realChannelID = self.cfg['telegram']['channel_id']

        #super().__init__(
        #    realChannelID, self.cfg['telegram']['api_id'],
        #    self.cfg['telegram']['api_hash'], self.cfg['paths']['data_path'],
        #    self.cfg['paths']['tmp_path'], int(self.cfg['telegram']['max_sessions'])
        #)

        self.loop = asyncio.get_event_loop()


    def build_main_widgets(self):
        def update_info(used_sessions_ref, progress_ref):
            local_progress = progress_ref()
            local_used_sessions = used_sessions_ref()

            if not local_progress or not local_used_sessions:
                # widget is dead, the main loop must've been destroyed
                return

            local_progress.set_text(self.progress_info)
            local_used_sessions.set_text("[ {} of {} ]".format(
                1, 4))

            # Schedule to update the clock again in one second
            self.loop.call_later(5, update_info, used_sessions_ref, progress_ref)

        title = urwid.Text("Telegram File Manager", align='center')
        used_sessions = urwid.Text('', align='right')
        progress = urwid.Text('')
        div = urwid.Divider()

        pile = urwid.Pile([title, used_sessions, div, progress])

        update_info(weakref.ref(used_sessions), weakref.ref(progress))

        return urwid.Filler(pile, 'top')


    def unhandled_keys(self, key):
        #optionDict = {'upload' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['upload']), 'function' : self.uploadHandler},
        #              'download' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['download']), 'function' : self.downloadHandler},
        #              'cancel' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['cancel']), 'function' : self.cancelHandler},
        #              'resume' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['resume']), 'function' : self.resumeHandlerUI}}

        if key == 'esc':
            #self.endSessions() # Must call to exit the program
            raise urwid.ExitMainLoop

    def main(self):
        main_widget = self.build_main_widgets()

        self.urwid_loop = urwid.MainLoop(
            main_widget,
            event_loop=urwid.AsyncioEventLoop(loop=self.loop),
            unhandled_input=self.unhandled_keys
        )
        self.urwid_loop.run()


if __name__ == "__main__":
    ui = UserInterface()
    ui.main()
