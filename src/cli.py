import urwid
import os
import weakref
import asyncio

import misc
from backend.sessionsHandler import SessionsHandler

class UserInterface(SessionsHandler):
    def __init__(self):
        self.cfg = misc.loadConfig()

        try:
            realChannelID = int(self.cfg['telegram']['channel_id'])
        except ValueError:
            realChannelID = self.cfg['telegram']['channel_id']

        super().__init__(
            realChannelID, self.cfg['telegram']['api_id'],
            self.cfg['telegram']['api_hash'], self.cfg['paths']['data_path'],
            self.cfg['paths']['tmp_path'], int(self.cfg['telegram']['max_sessions'])
        )

        self.loop = asyncio.get_event_loop()

        main_widget = build_widgets()

        urwid_loop = urwid.MainLoop(
            main_widget,
            event_loop=urwid.AsyncioEventLoop(loop=self.loop),
            unhandled_input=urwid_unhandled,
        )
        urwid_loop.run()


    def build_widgets(self):
        def update_progress(widget_ref):
            widget = widget_ref()
            if not widget:
                # widget is dead; the main loop must've been destroyed
                return

            widget.set_text(progress_info)

            # Schedule to update the clock again in one second
            loop.call_later(1, update_progress, widget_ref)

        progress = urwid.Text('')
        update_progress(weakref.ref(progress))

        return urwid.Filler(progress, 'top')


    def unhandled(key):
        optionDict = {'upload' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['upload']), 'function' : self.uploadHandler},
                      'download' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['download']), 'function' : self.downloadHandler},
                      'cancel' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['cancel']), 'function' : self.cancelHandler},
                      'resume' : {'value' : False, 'keybind' : ord(self.cfg['keybinds']['resume']), 'function' : self.resumeHandlerUI}}

        if key == 'esc':
            self.endSessions() # Must call to exit the program
            raise urwid.ExitMainLoop


if __name__ == "__main__":
    ui = UserInterface()
