"""Helpers for the threaded child/parent simulations: fake audio hardware, real UDP on localhost."""
import builtins
import struct
import threading
import time

FR = 320


class ChildAudio:
    """Scripted microphone, paced in real time. The frame index is stored in the samples."""

    def __init__(self, events, stop_s):
        self.events, self.stop_s, self.i, self.t0 = events, stop_s, 0, None

    def open_rx(self): pass
    def close(self): pass
    def open_tx(self): pass
    def set_pa(self, on): pass
    def write_silence(self): pass
    def write_payload(self, p, gain=None): pass

    def read_frame(self):
        if self.t0 is None:
            self.t0 = time.monotonic()
        wait = self.t0 + (self.i + 1) * 0.02 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        t = self.i * 0.02
        if t > self.stop_s:
            raise KeyboardInterrupt
        lvl, z = -79.0, 110
        for a, b, l, zz in self.events:
            if a <= t < b:
                lvl, z = l, zz
        idx = self.i % 30000
        self.i += 1
        return struct.pack("<%dh" % FR, *([idx] * FR)), lvl, z


class ParentAudio:
    level = 4

    def __init__(self):
        self.frames, self.beeps, self.t0 = 0, [], time.monotonic()

    def set_level(self, n): self.level = n
    def open_tx(self): pass
    def close(self): pass
    def set_pa(self, on): pass
    def write_silence(self): time.sleep(0.02)

    def write_payload(self, p, gain=None):
        time.sleep(0.02)
        self.frames += 1

    def beep(self, **k):
        self.beeps.append(round(time.monotonic() - self.t0, 1))


class Capture:
    """Collects print() output of all threads with a timestamp."""

    def __init__(self):
        self.lines, self.lock, self.t0, self._real = [], threading.Lock(), time.monotonic(), builtins.print

    def __enter__(self):
        builtins.print = lambda *a, **k: self._add(" ".join(str(x) for x in a))
        return self

    def __exit__(self, *e):
        builtins.print = self._real

    def _add(self, s):
        with self.lock:
            self.lines.append("%6.2f %s" % (time.monotonic() - self.t0, s))

    def has(self, text):
        return any(text in l for l in self.lines)

    def count(self, text):
        return sum(1 for l in self.lines if text in l)


def run_pair(child_mod, parent_mod, mcfg, scfg, maudio, saudio, mhud, shud, mnet, snet, parent_seconds, extra=()):
    """Run the child (until its audio stops) and the parent (for parent_seconds) as two threads."""
    deadline = time.monotonic() + parent_seconds
    orig = snet.recv

    def recv():
        if time.monotonic() > deadline:
            raise KeyboardInterrupt
        return orig()

    snet.recv = recv

    def rm():
        try: child_mod.run(mcfg, maudio, mnet, mhud)
        except KeyboardInterrupt: pass

    def rs():
        try: parent_mod.run(scfg, saudio, snet, shud)
        except KeyboardInterrupt: pass

    ts, tm = threading.Thread(target=rs), threading.Thread(target=rm)
    others = [threading.Thread(target=f) for f in extra]
    for t in others + [ts]:
        t.start()
    time.sleep(0.2)
    tm.start()
    tm.join()
    ts.join()
    for t in others:
        t.join()
