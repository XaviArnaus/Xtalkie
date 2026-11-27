"""Night clips: event clips and 20 s windows, the budget, the eviction, one job at a time, never breaking the monitor."""
import json
import os
import shutil
import struct
import tempfile
import time

from common import check, patch_time
import common

patch_time()
clock_ms = [1000000]
time.ticks_ms = lambda: clock_ms[0]
time.ticks_us = lambda: clock_ms[0] * 1000
from helpers import nightclips
from helpers.nightclips import NightClips

tmp = tempfile.mkdtemp()
FR = bytes(range(256)) * 2 + bytes(128)             # 640 bytes


def frames(nc, n):
    for _ in range(n):
        clock_ms[0] += 20
        nc.feed(FR)


def drain(nc, limit=3000):
    k = 0
    while nc.job is not None and k < limit:
        frames(nc, 1)
        k += 1
    return k


def make(**kw):
    d = os.path.join(tmp, "n%d" % len(os.listdir(tmp)))
    kw.setdefault("free_fn", lambda: 10 ** 9)
    return NightClips(folder=d, **kw), d


# an alerted event: a short clip, 0.5 s before + the event, written a chunk per frame, with an index line
nc, d = make(window_every_s=1200)
frames(nc, 200)
nc.event(0.4, -59.0, -63.0, 30, "ALERT: loud", True)                      # first event: opens a window, not an event clip
check(nc.job["kind"] == "w" and len(nc.job["frames"]) == 150, "the first event of an episode starts a 20 s window (3 s already heard)")
steps = drain(nc)
names = sorted(os.listdir(d))
check(any("_w_" in n for n in names) and "index.csv" in names, "the window is saved, with an index.csv")
w = [n for n in names if "_w_" in n][0]
data = open(os.path.join(d, w), "rb").read()
check(len(data) == 44 + 1000 * 640 and data[:4] == b"RIFF" and struct.unpack("<I", data[40:44])[0] == 1000 * 640,
      "the window is a valid 20 s WAV (%d bytes)" % len(data))
check(steps >= 1000 // 3 - 5, "it takes the writing %d frames: one small chunk per frame, never all at once" % steps)

nc.event(0.4, -59.0, -63.0, 30, "ALERT: loud", True)
check(nc.job["kind"] == "e", "the next alerted event within 20 min is a short event clip")
check(len(nc.job["frames"]) == int(0.4 * 50) + 25, "it has 0.5 s before the event and the event (%d frames)" % len(nc.job["frames"]))
drain(nc)
check(sum(1 for n in os.listdir(d) if "_e_" in n) == 1, "the event clip is saved")
nc.event(0.4, -60.0, -64.0, 30, "ignored (snore)", False)
check(nc.job is None, "an ignored snore does not make an event clip (inside the window interval)")
clock_ms[0] += 1300 * 1000
nc.event(0.4, -60.0, -64.0, 30, "ignored (snore)", False)
check(nc.job is not None and nc.job["kind"] == "w", "after 20 minutes an ignored snore starts the next window")
drain(nc)
lines = open(os.path.join(d, "index.csv")).read().splitlines()
check(len(lines) == 3 and lines[0].split(",")[3] == "w" and lines[1].split(",")[3] == "e", "index.csv has a line per file: %s" % lines[1])
nc.event(0.3, -50.0, -60.0, 10, "noise (impact)", False, worthy=False)
check(nc.job is None, "noise starts nothing")

# one job at a time
nc2, d2 = make()
frames(nc2, 100)
nc2.event(0.4, -59, -63, 30, "ALERT: loud", True)
nc2.event(0.4, -59, -63, 30, "ALERT: loud", True)
check(nc2.skipped == 1, "an event during a running job is only counted")
check("clipskip=1" in nc2.minute() and nc2.skipped == 0, "the minute line reports it and resets")

# the budget: the oldest EVENT clip of the busiest hour goes first, windows stay
nc3, d3 = make(budget=3 * 100000, window_every_s=10 ** 9)
nc3.files = {}
def put(name, size=100000):
    open(os.path.join(d3, name), "wb").write(bytes(size))
    nc3.files[name] = size
put("20261127_010000_w.wav"); put("20261127_020000_e.wav"); put("20261127_020500_e.wav")
check(nc3._victim() == "20261127_020000_e.wav", "busiest hour (02), oldest event clip is the victim")
put("20261127_020700_w.wav", 1)
nc3.files["20261127_020700_w.wav"] = 1
frames(nc3, 160)
nc3.last_window = clock_ms[0]
nc3.event(0.4, -59, -63, 30, "ALERT: loud", True)
drain(nc3)
check("20261127_020000_e.wav" not in os.listdir(d3) and nc3.saved == 1, "a full budget deletes the victim and still saves the new clip")
check(nc3.used() <= 300000 + 1, "the clips stay within the budget (%d bytes)" % nc3.used())

# the free space is respected, and nothing is deleted when nothing can make room
nc4, d4 = make(min_free=4000000, free_fn=lambda: 4000100)
frames(nc4, 100)
nc4.event(0.4, -59, -63, 30, "ALERT: loud", True)
drain(nc4)
check(nc4.saved == 0 and nc4.skipped == 1 and not [n for n in os.listdir(d4) if n.endswith(".wav")],
      "with no room above min_free the clip is skipped, not written")

# never breaks the monitor: errors switch it off after 3
nc5, d5 = make()
frames(nc5, 100)
shutil.rmtree(d5)
open(d5, "w").write("a file where the folder should be")
for _ in range(4):
    clock_ms[0] += 11000
    nc5.event(0.4, -59, -63, 30, "ALERT: loud", True)
    try:
        drain(nc5)
    except Exception:
        check(False, "feed must never raise")
check(nc5.errors >= 3 and not nc5.on, "after 3 write errors the recorder switches itself off")
frames(nc5, 5)                                     # still harmless
check(True, "feeding a switched-off recorder does nothing")

# the file of a not set clock
nc6, d6 = make()
frames(nc6, 100)
_lt = time.localtime
time.localtime = lambda *a: (2000, 1, 1, 0, 0, 5, 5, 1)
nc6.event(0.4, -59, -63, 30, "ALERT: loud", True)
drain(nc6)
time.localtime = _lt
check(any(n.startswith("t") and "_w_" in n for n in os.listdir(d6)), "without a valid clock the file is named by uptime")

# the child loop with night clips on (loopback, one board): the event is recorded, the stream is unaffected
import struct
from app import child
from helpers import config, log
from net.link import LoopbackNet

log.enabled = False


class Audio:
    def __init__(self): self.i, self.played, self.mode = 0, [], None
    def open_rx(self): self.mode = "rx"
    def open_tx(self): self.mode = "tx"
    def close(self): self.mode = None
    def set_pa(self, on): pass
    def write_silence(self): self.played.append(None)
    def write_payload(self, p, g=None): self.played.append(1)

    def read_frame(self):
        t = self.i * 0.02
        if t > 12:
            raise KeyboardInterrupt
        lvl, z = (-55.0, 45) if 3.0 <= t < 4.0 else (-79.0, 110)
        self.i += 1
        return struct.pack("<320h", *([self.i] * 320)), lvl, z


def run_child(enabled):
    cfg = config.load("/nonexistent")
    cfg["nightclips"].update({"enabled": enabled, "folder": os.path.join(tmp, "child%d" % enabled), "window_s": 2})
    a = Audio()
    try:
        child.run(cfg, a, LoopbackNet(), None)
    except KeyboardInterrupt:
        pass
    return a, cfg["nightclips"]["folder"]


a_on, f_on = run_child(True)
a_off, f_off = run_child(False)
clips = [n for n in os.listdir(f_on) if n.endswith(".wav")] if os.path.isdir(f_on) else []
check(len(clips) >= 1 and os.path.exists(os.path.join(f_on, "index.csv")), "the child loop records the event: %s" % clips)
check(not os.path.exists(f_off), "with night clips off nothing is created")
check(len([x for x in a_on.played if x is not None]) == len([x for x in a_off.played if x is not None]),
      "the played-back stream is the same with and without the recorder")

# the flash file system is slow with many files: nothing is stat'ed at start, names carry the size, few files, spaced clips
nc7, d7 = make(max_files=4, min_gap_s=10, budget=10 ** 9)
frames(nc7, 200)
nc7.event(0.4, -59, -63, 30, "ALERT: loud", True)
drain(nc7)
wname = [n for n in os.listdir(d7) if n.endswith(".wav")][0]
check(wname.endswith("_w_1000.wav") and nc7.files[wname] == 1000 * 640 + 44, "the length is in the file name (%s) and gives the size" % wname)
_stat = os.stat
os.stat = lambda *a, **k: (_ for _ in ()).throw(AssertionError("os.stat used"))
try:
    nc8 = NightClips(folder=d7, free_fn=lambda: 10 ** 9)
    check(wname in nc8.files and nc8.files[wname] == 1000 * 640 + 44, "start-up reads the folder once and never stats the files")
finally:
    os.stat = _stat
for i in range(3):
    clock_ms[0] += 11000
    nc7.event(0.4, -59, -63, 30, "ALERT: loud", True)
    drain(nc7)
nc7.skipped = 0
nc7.event(0.4, -59, -63, 30, "ALERT: loud", True)
check(nc7.job is None and nc7.skipped == 1, "a second event clip within 10 s is skipped (one clip per min_gap_s)")
for i in range(4):
    clock_ms[0] += 11000
    nc7.event(0.4, -59, -63, 30, "ALERT: loud", True)
    drain(nc7)
check(len([n for n in os.listdir(d7) if n.endswith(".wav")]) <= 4, "never more than max_files files (%d)" % len([n for n in os.listdir(d7) if n.endswith(".wav")]))

# too slow for the monitor: it gives up for the run after 3 slow flash operations
nc9, d9 = make()
frames(nc9, 100)
nc9.event(0.4, -59, -63, 30, "ALERT: loud", True)
_us = time.ticks_us
tick = [0]
def slow_us():
    tick[0] += 600000                                  # every call "takes" 600 ms
    return tick[0]
time.ticks_us = slow_us
try:
    drain(nc9, 1500)
finally:
    time.ticks_us = _us
check(not nc9.on and nc9.job is None, "after 3 flash operations over 400 ms the recorder switches itself off")
check(not [n for n in os.listdir(d9) if n.endswith(".wav")], "...and removes the half-written clip")

# not started in a crash loop
from helpers import bootinfo
bootinfo._crashes = 2
cfg = config.load("/nonexistent")
cfg["nightclips"].update({"enabled": True, "folder": os.path.join(tmp, "loopguard")})
try:
    child.run(cfg, Audio(), LoopbackNet(), None)
except KeyboardInterrupt:
    pass
bootinfo._crashes = 0
check(not os.path.exists(os.path.join(tmp, "loopguard")), "after 2 crashes in a row the child does not start the recorder")

# the menu: the parent sends CMD_CLIPS, the child switches (and remembers), the heartbeat reports it back
from net import proto
hb = proto.pack_hb(1, False, -80.0, 50, False, 3, "0.10.2 abc1234", 2, 1)
body = proto.parse(hb)[3]
check(proto.parse_hb_clips(body) == 1 and proto.parse_hb_restart(body) == 2 and proto.parse_hb_version(body) == "0.10.2 abc1234"
      and proto.parse_hb(body)[4] == 3, "the heartbeat carries the clips state without disturbing the other fields")
old_hb = proto.parse(proto.pack_hb(1, False, -80.0, 50, False, 3, "0.9", 2))[3]
check(proto.parse_hb_clips(old_hb) is None, "a heartbeat of an older child has no clips field (None)")
check(proto.parse(proto.pack_cmd(1, proto.CMD_CLIPS, 1))[3] == bytes([proto.CMD_CLIPS, 1]), "CMD_CLIPS is a normal command")

import helpers.config as hc
hc.STATE = os.path.join(tmp, "state.json")


class CmdNet:
    """A parent that sends the given commands one after the other and records the heartbeats it gets."""
    def __init__(self, cmds):
        self.cmds, self.hbs, self.peer_set = list(cmds), [], False
    def ensure(self): pass
    def recv(self):
        if self.n // 50 != self.hello_at:                 # a HELLO every second keeps the link up
            self.hello_at = self.n // 50
            return proto.pack(proto.T_HELLO, 1, bytes([255, 0])), ("1.2.3.4", 5)
        if self.cmds and self.n > self.cmds[0][0]:
            return proto.pack_cmd(1, proto.CMD_CLIPS, self.cmds.pop(0)[1]), ("1.2.3.4", 5)
        return None
    n = 0
    hello_at = -1
    def send(self, data, to):
        info = proto.parse(data)
        if info and info[0] == proto.T_HB:
            self.hbs.append(proto.parse_hb_clips(info[3]))
        return True


def run_with_cmds(enabled, cmds, frames_n=1800):
    cfg = config.load("/nonexistent")
    cfg["nightclips"].update({"enabled": enabled, "folder": os.path.join(tmp, "menu")})
    cfg["child"]["hb_ms"] = 200
    net = CmdNet(cmds)

    class A:
        i = 0
        def open_rx(self): pass
        def close(self): pass
        def read_frame(self):
            if self.i >= frames_n:
                raise KeyboardInterrupt
            self.i += 1
            net.n = self.i
            clock_ms[0] += 20
            return bytes(640), -79.0, 100
    a = A()
    try:
        child.run(cfg, a, net, None)
    except KeyboardInterrupt:
        pass
    return net


net = run_with_cmds(False, [(300, 1), (900, 0)])
seen = [x for x in net.hbs if x is not None]
check(seen[0] == 0 and 1 in seen and seen[-1] == 0, "deployed off: the menu switches it on, then off again (heartbeat reports 0, 1, 0)")
check(json.load(open(hc.STATE)).get("clips") == 0, "the choice is remembered in state.json")
net = run_with_cmds(False, [(300, 1)])
check(json.load(open(hc.STATE)).get("clips") == 1, "switched on from the menu is remembered")
net = run_with_cmds(False, [])
seen = [x for x in net.hbs if x is not None]
check(seen and seen[0] == 1, "after a restart the remembered choice is used (on) although the deployed setting is off")
net = run_with_cmds(True, [])
seen = [x for x in net.hbs if x is not None]
check(seen and seen[0] == 1, "a deploy that says on starts on")
hc_state = json.load(open(hc.STATE))
hc_state["clips"] = 0
hc_state["clips_cfg"] = 1                          # chosen while the deployed setting was on
json.dump(hc_state, open(hc.STATE, "w"))
net = run_with_cmds(True, [])
check([x for x in net.hbs if x is not None][0] == 0, "the remembered OFF is used while the deployed setting is the same")
hc_state["clips"] = 1                              # "on" chosen while the deployed setting was on ...
json.dump(hc_state, open(hc.STATE, "w"))
net = run_with_cmds(False, [])                     # ... and now a deploy without --clips
check([x for x in net.hbs if x is not None][0] == 0, "a deploy with another --clips setting wins over an old menu choice")

# the menu item itself
from ui import hud as _hud
check("CLIPS" in _hud.MENU_ITEMS, "the parent menu has a CLIPS item")

shutil.rmtree(tmp, ignore_errors=True)
common.finish()
