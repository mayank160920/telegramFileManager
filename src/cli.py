import urwid
import os
import weakref
import asyncio

from .backend.sessionsHandler import SessionsHandler

class UserInterface(SessionsHandler):
    def __init__(self):
        super().__init__()

        self.progress_info = "1"

        try:
            realChannelID = int(self.cfg['telegram']['channel_id'])
        except ValueError:
            realChannelID = self.cfg['telegram']['channel_id']

        self.loop = asyncio.get_event_loop()

        self.main_widget = self.build_main_widgets()

        urwid_loop = urwid.MainLoop(
            self.main_widget,
            event_loop=urwid.AsyncioEventLoop(loop=self.loop),
            unhandled_input=self.unhandled_keys
        )
        urwid_loop.run()


    def build_main_widgets(self):
        def update_info(used_sessions_ref, transfer_info_ref):
            local_used_sessions = used_sessions_ref()
            local_transfer_info = transfer_info_ref()

            if not local_used_sessions or not local_transfer_info:
                # widget is dead, the main loop must've been destroyed
                return

            local_used_sessions.set_text("[ {} of {} ]".format(1, 4))

            local_transfer_info.contents = [(urwid.Text("fewfwe"), local_transfer_info.options('pack', None)),
                (urwid.Text("faawe"), local_transfer_info.options('pack', None))]

            # Schedule to update the clock again in one second
            self.loop.call_later(5, update_info, used_sessions_ref, transfer_info_ref)

        title = urwid.Text("Telegram File Manager", align='center')
        used_sessions = urwid.Text('', align='right')
        transfer_info = urwid.Pile([])
        div = urwid.Divider()

        pile = urwid.Pile([title, used_sessions, div, transfer_info])

        update_info(weakref.ref(used_sessions), weakref.ref(transfer_info))

        return urwid.Filler(pile, 'top')


    def unhandled_keys(self, key):
        #optionList = [{'keybind' : self.cfg['keybinds']['upload'], 'function' : self.uploadHandler},
        #              {'keybind' : self.cfg['keybinds']['download'], 'function' : self.downloadHandler},
        #              {'keybind' : self.cfg['keybinds']['cancel'], 'function' : self.cancelHandler},
        #              {'keybind' : self.cfg['keybinds']['resume'], 'function' : self.resumeHandlerUI}]

        if key == 'esc':
            #self.endSessions() # Must call to exit the program
            raise urwid.ExitMainLoop


if __name__ == "__main__":
    ui = UserInterface()
