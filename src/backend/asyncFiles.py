from ctypes import CDLL, c_size_t, c_char_p, c_char
import asyncio
from functools import partial, wraps
from os import remove


# https://github.com/Tinche/aiofiles/blob/master/aiofiles/os.py
def wrap(func):
    @wraps(func)
    async def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)

    return run

class AsyncFiles:
    def __init__(self, libPath: str):
        extern = CDLL(libPath)

        extern.splitFile.restype = c_size_t
        extern.splitFile.argtypes = [c_size_t, c_char_p, c_char_p,
                                     c_size_t, c_size_t]

        extern.concatFiles.restype = c_char
        extern.concatFiles.argtypes = [c_char_p, c_char_p, c_size_t]

        self.splitFile = wrap(extern.splitFile)
        self.concatFiles = wrap(extern.concatFiles)
        self.remove = wrap(remove)
