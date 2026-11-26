"""The play mode: clip cutting, WAV files with a disk cap, the speed effect, the screen, and the whole loop."""
import builtins
import os
import random
import struct
import tempfile
import wave

from common import check, finish, patch_time

patch_time()
from dsp.clipper import Clipper
from dsp.effects import resample_frames
from helpers.clips import ClipStore

FR = 320
Q = -79.0
rnd = random.Random(1)


def frame(i):
    return struct.pack("<%dh" % FR, *([i % 30000] * FR))


def first_sample(f):
    return struct.unpack_from("<h", f, 0)[0]


def quiet(n):
    return [Q + rnd.gauss(0, 0.8) for _ in range(n)]


def feed(c, levels):
    out = []
    for k, lvl in enumerate(levels):
        ev = c.update(lvl, frame(k))
        if ev:
            out.append((k, ev))
    return out


print("-- the clip cutter")
ev = feed(Clipper(), quiet(300))
check(not ev, "a quiet room gives no clips")

ev = feed(Clipper(), quiet(100) + [-50.0] * 50 + quiet(100))
kinds = [e[1][0] for e in ev]
check(kinds == ["start", "clip"], "a one second sound gives one clip: %s" % kinds)
frames = ev[-1][1][1]
check(len(frames) == 12 + 50 + 15, "clip = 12 pre-roll + 50 sound + 15 tail frames (%d)" % len(frames))
check(first_sample(frames[0]) == 100 - 12, "the pre-roll really comes from before the sound (starts at frame %d)" % first_sample(frames[0]))
check(first_sample(frames[-1]) == 100 + 50 + 15 - 1, "the clip ends 300 ms after the last sound")

ev = feed(Clipper(), quiet(100) + [-40.0] + quiet(100))
check(not ev, "a single loud frame (a click) is ignored")
ev = feed(Clipper(), quiet(100) + [-40.0] * 3 + quiet(100))
check([e[1][0] for e in ev] == ["start", "drop"], "a 60 ms click starts and is dropped: %s" % [e[1][0] for e in ev])

ramp = [-79.0 + 17.0 * k / 2000 for k in range(2000)]
check(not feed(Clipper(), quiet(60) + ramp), "a room that slowly gets louder does not trigger")

ev = feed(Clipper(), quiet(100) + [-40.0] * 1500 + quiet(100))
n_clip = sum(1 for e in ev if e[1][0] == "clip")
check(1 <= n_clip <= 2, "a sound that never stops gives %d clip(s), not an endless series" % n_clip)

ev = feed(Clipper(max_s=10), quiet(100) + [-50.0] * 600 + quiet(100))
long_clip = [e[1][1] for e in ev if e[1][0] == "clip"][0]
check(495 <= len(long_clip) <= 505, "a 12 s sound is cut at max_s=10 (%d frames)" % len(long_clip))

print("-- WAV files and the disk cap")
tmp = tempfile.mkdtemp()
store = ClipStore(os.path.join(tmp, "clips"), max_total=300000, min_free=0, free_fn=lambda: 10 ** 9)
clip100 = [frame(k) for k in range(100)]
paths = [store.save(clip100, "_2.0s") for _ in range(5)]
check(all(paths), "five clips of 64 KB are accepted")
names = store.files()
check(len(names) == 4 and names[0].startswith("c0002"), "beyond the 300 KB cap the OLDEST clip is deleted: %s" % names)
check(store.total() <= 300000, "total stays under the cap (%d bytes)" % store.total())
with wave.open(paths[-1], "rb") as w:
    check((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 16000, 100 * FR),
          "the file is a normal WAV: mono, 16 bit, 16 kHz, %d samples" % w.getnframes())
store2 = ClipStore(os.path.join(tmp, "clips"), max_total=300000, min_free=0, free_fn=lambda: 10 ** 9)
check(store2.save(clip100) .endswith("c0006.wav"), "numbering continues after a reboot (c0006)")
check(store2.save([frame(0)] * 1000) is None, "a clip bigger than the whole cap is refused")
before = store2.files()
store3 = ClipStore(os.path.join(tmp, "clips"), max_total=10 ** 7, min_free=50000, free_fn=lambda: 100000)
check(store3.save(clip100) is None and store3.files() == before,
      "too little free flash: nothing saved, and no clip is deleted for it")

print("-- the speed effect")
f10 = [frame(k) for k in range(10)]
check(len(resample_frames(f10, 2.0)) == 5 and len(resample_frames(f10, 0.5)) == 20, "speed 2.0 -> 5 frames, 0.5 -> 20 frames")
check(resample_frames(f10, 1.0) == f10, "speed 1.0 leaves the clip as it is")
check(all(len(f) == FR * 2 for f in resample_frames(f10, 1.37)), "every frame keeps its exact size")

print("-- the screen")
import board
from helpers import config
import ui.playui as pui
cfg = config.load("/nonexistent")
ui = pui.PlayUi(cfg, board.i2c())
check(ui.display is not None, "the play screen starts on the stub panel")
ui.ready(3)
ui.playing(3)
check(ui.display is not None and ui.display.on, "ready / playing screens draw without errors")
ui._shown -= 200000
ui.tick(pui.time.ticks_ms(), 120000)
check(not ui.display.on, "the screen switches off after a quiet while")

print("-- the whole loop on a fake board")
from app import play
from helpers import log

log.enabled = False


class FakeAudio:
    def __init__(self, levels, events):
        self.levels, self.i, self.ev, self.mode, self.pa, self.writes = levels, 0, events, None, False, 0

    def open_rx(self): self.mode = "rx"; self.ev.append("rx")
    def open_tx(self): self.mode = "tx"; self.ev.append("tx")
    def close(self): self.mode = None
    def write_silence(self): pass

    def set_pa(self, on):
        self.pa = on
        self.ev.append("pa1" if on else "pa0")

    def write_payload(self, p, gain=None):
        assert self.mode == "tx" and self.pa, "speaker used while the amplifier is off"
        self.writes += 1
        self.ev.append("w")

    def read_frame(self):
        assert self.mode == "rx", "the microphone was read while it is closed"
        if self.i >= len(self.levels):
            raise KeyboardInterrupt
        lvl = self.levels[self.i]
        self.i += 1
        return frame(self.i), lvl, 50


class FakeUi:
    def __init__(self, events, audio_ref):
        self.ev, self.a = events, audio_ref

    def ready(self, n): self.ev.append("ui:ready:%d:%s" % (n, self.a[0].mode))
    def playing(self, n): self.ev.append("ui:playing:%d:%s" % (n, self.a[0].mode))
    def tick(self, now, idle): pass


def play_session(speed=1.0, save=True):
    levels = ([Q] * 60 + [-50.0] * 60 + [Q] * 120 + [-50.0] * 30 + [Q] * 120)
    events = []
    ref = []
    a = FakeAudio(levels, events)
    ref.append(a)
    c = config.load("/nonexistent")
    c["play"]["speed"] = speed
    c["play"]["save"] = save
    store = ClipStore(os.path.join(tmp, "game%s" % speed), 10 ** 7, 0, free_fn=lambda: 10 ** 9) if save else None
    real = builtins.print
    builtins.print = lambda *x, **k: events.append("print:" + " ".join(map(str, x)))
    try:
        try:
            play.run(c, a, ui=FakeUi(events, ref), store=store)
        except KeyboardInterrupt:
            pass
    finally:
        builtins.print = real
    return a, events, store


a, ev, store = play_session()
check(a.writes == (12 + 60 + 15) + (12 + 30 + 15), "both clips are played back in full (%d frames)" % a.writes)
check(len(store.files()) == 2, "both clips are saved: %s" % store.files())
with wave.open(store.folder + "/" + store.files()[0], "rb") as w:
    check(w.getnframes() == (12 + 60 + 15) * FR, "the first file holds pre-roll + sound + tail (%d samples)" % w.getnframes())
i_ready = [k for k, e in enumerate(ev) if e.startswith("ui:playing")]
check(len(i_ready) == 2 and all(ev[k].endswith(":rx") for k in i_ready), "'listen' is drawn before playback, while only the mic is open")
rec = [k for k, e in enumerate(ev) if "recording" in e]
clip_line = [k for k, e in enumerate(ev) if e.startswith("print:[play] clip ")]
ok = all(not any(e.startswith("ui:") for e in ev[r:c]) for r, c in zip(rec, clip_line))
check(len(rec) == 2 and ok, "NOTHING is drawn while a clip is being recorded")
check(ev.index("tx") < ev.index("pa1") < ev.index("w"), "playback order: speaker opened, amplifier on, then audio")
seq = [e for e in ev if e in ("rx", "tx")]
check(seq == ["rx", "tx", "rx", "tx", "rx"], "microphone and speaker never overlap: %s" % seq)

a, ev, store = play_session(speed=1.4)
check(abs(a.writes - ((12 + 60 + 15) + (12 + 30 + 15)) / 1.4) <= 4, "speed 1.4 plays the clips shorter (%d frames)" % a.writes)

a, ev, store = play_session(save=False)
check(store is None and a.writes > 0 and not os.path.exists("/clips"), "with save off, clips are only played back and no folder is created")
finish()
