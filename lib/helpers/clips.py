# helpers/clips.py -- WAV clips on the board's flash, with a hard cap so the play mode can never fill the disk.
#
# Files: /clips/c0001_2.4s.wav, c0002_0.9s.wav, ...  (16-bit mono 16 kHz, playable on any computer).
# When the cap is reached the OLDEST clips are deleted. If the flash is short for any other reason (other files),
# nothing is written and nothing is deleted: the clips are the data, they are never sacrificed for that.
import os
import struct

RATE = 16000


def wav_header(n_bytes, rate=RATE):
    return struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + n_bytes, b"WAVE", b"fmt ", 16, 1, 1,
                       rate, rate * 2, 2, 16, b"data", n_bytes)


def _statvfs_free():
    st = os.statvfs("/")
    return st[0] * st[3]


class ClipStore:
    def __init__(self, folder="/clips", max_total=6000000, min_free=2500000, free_fn=None):
        self.folder = folder
        self.max_total = max_total
        self.min_free = min_free
        self._free = free_fn or _statvfs_free
        try:
            os.mkdir(folder)
        except OSError:
            pass                                    # exists already
        self._next = 1
        for name in self.files():
            n = self._number(name)
            if n >= self._next:
                self._next = n + 1

    @staticmethod
    def _number(name):
        i = 1
        while i < len(name) and name[i].isdigit():
            i += 1
        try:
            return int(name[1:i])
        except ValueError:
            return 0

    def files(self):
        try:
            names = [n for n in os.listdir(self.folder) if n.startswith("c") and n.endswith(".wav")]
        except OSError:
            return []
        names.sort(key=self._number)
        return names

    def _size(self, name):
        return os.stat(self.folder + "/" + name)[6]

    def count(self):
        return len(self.files())

    def total(self):
        return sum(self._size(n) for n in self.files())

    def save(self, frames, tag=""):
        """Write one clip. Returns its path, or None if it does not fit under the limits."""
        n_bytes = sum(len(f) for f in frames)
        size = n_bytes + 44
        if size > self.max_total:
            return None
        names = self.files()
        total = sum(self._size(n) for n in names)
        while names and total + size > self.max_total:
            victim = names.pop(0)
            total -= self._size(victim)
            os.remove(self.folder + "/" + victim)
        if self._free() - size < self.min_free:
            return None
        path = "%s/c%04d%s.wav" % (self.folder, self._next, tag)
        with open(path, "wb") as f:
            f.write(wav_header(n_bytes))
            for fr in frames:
                f.write(fr)
        self._next += 1
        return path
