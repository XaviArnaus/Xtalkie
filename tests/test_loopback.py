"""One board, no network: the gate opens, the pre-roll is included and the stream is played back."""
import struct

from common import check, finish, patch_time

patch_time()
from app import child
from helpers import config, log
from net.link import LoopbackNet

log.enabled = False


class Audio:
    def __init__(self): self.i, self.played, self.mode, self.pa = 0, [], None, []
    def open_rx(self): self.mode = "rx"
    def open_tx(self): self.mode = "tx"
    def close(self): self.mode = None
    def set_pa(self, on): self.pa.append(on)
    def write_silence(self): self.played.append(None)
    def write_payload(self, p, g=None): self.played.append(struct.unpack_from("<h", p, 0)[0])

    def read_frame(self):
        assert self.mode == "rx"
        t = self.i * 0.02
        if t > 12:
            raise KeyboardInterrupt
        lvl, z = (-55.0, 45) if 3.0 <= t < 4.0 else (-79.0, 110)
        idx = self.i
        self.i += 1
        return struct.pack("<320h", *([idx] * 320)), lvl, z


cfg, a = config.load("/nonexistent"), Audio()
try:
    child.run(cfg, a, LoopbackNet(), None)
except KeyboardInterrupt:
    pass
frames = [x for x in a.played if x is not None]
check(len(frames) == 100, "100 frames played back (%d)" % len(frames))
check(frames[0] == 140, "playback starts 10 frames before the sound (pre-roll): first frame %d, sound began at 150" % frames[0])
check(a.pa == [True, False], "speaker amplifier on during playback only %s" % a.pa)
finish()
