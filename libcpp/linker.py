from pathlib import Path
import ctypes


class Linker:
    def __init__(self, lib_path: str | Path):
        self.lib = ctypes.CDLL(lib_path)

    def __call__(self, argtypes, restype, name):
        self.lib.__getattr__(name).argtypes = argtypes
        self.lib.__getattribute__(name).restype = restype

        def wrapped(*args):
            return self.lib.__getattribute__(name)(*args)

        return wrapped


if __name__ == '__main__':
    pass
