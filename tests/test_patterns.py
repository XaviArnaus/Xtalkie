"""Adaptive snore learning: variable bursts, several patterns, deviations that alert, patterns saved and reloaded."""
import json
import os
import random
import shutil
import struct
import tempfile

from common import check, finish, patch_time

patch_time()
from dsp.gate import Gate
from helpers import patterns

ACT, IMPACT = 12.0, 42.0                        # microphone level 3


def quiet(n, r, base=-75.0):
    return [(base + r.gauss(0, 1.2), int(r.gauss(115, 15))) for _ in range(n)]


def snore(n, peak, zcr, r):
    """A burst of n frames: a flat-ish top at `peak` with noise (like the real ones: only a few dB above the threshold)."""
    return [(peak + r.gauss(0, 1.6), int(r.gauss(zcr, 5))) for _ in range(n)]


def feed(g, frames, t0=0):
    opens = []
    for i, (lvl, z) in enumerate(frames):
        if g.update(lvl, z) == "open":
            opens.append((t0 + i, g.reason))
    return opens


def new_gate():
    g = Gate(act_db=ACT, impact_db=IMPACT)
    g.stamper = lambda: "2026-11-27 00:00:00"
    return g


def night(r, bursts, gap_s=(6.0, 9.0), dur_frames=(8, 40), peak=-59.0):
    """The real thing: bursts of 0.16-0.8 s, 6-9 s apart, peak ~-59 dB over a -75 dB floor."""
    frames = quiet(150, r)
    starts = []
    for _ in range(bursts):
        starts.append(len(frames))
        frames += snore(r.randint(*dur_frames), peak + r.uniform(-2, 2), 45, r)
        frames += quiet(int(r.uniform(*gap_s) * 50), r)
    return frames, starts


for seed in (1, 2, 3):
    r = random.Random(seed)
    print("seed", seed)

    # 1. the real pattern: short variable bursts, 7-8 s apart: learned, then quiet
    frames, starts = night(r, 30)
    g = new_gate()
    opens = feed(g, frames)
    check(g.learned == 1 and g.regime, "variable 0.2-0.8 s bursts every ~7.5 s become ONE pattern (%d learned)" % g.learned)
    first_regime = next((s for s in starts if True), 0)
    check(len(opens) <= 8, "...with few alerts in 30 bursts (%d, mostly while learning)" % len(opens))
    late_alerts = [o for o in opens if o[0] >= starts[10]]
    check(len(late_alerts) <= 2, "after burst 10 the snoring is quiet (%d alerts in 20 bursts)" % len(late_alerts))
    p = g.patterns[0]
    check(p["dmin"] < 0.35 and p["dmax"] > 0.6 and -62 < p["pmin"] and p["pmax"] < -52 and 5 < p["iv"] < 11, "the pattern covers the variation: %.2f-%.2f s, %.1f..%.1f dB, every %.1f s" % (p["dmin"], p["dmax"], p["pmin"], p["pmax"], p["iv"]))

    # 2. deviations alert: a louder cough, a long burst, a bright (voice) burst
    base = night(r, 14)[0]
    g = new_gate()
    feed(g, base)
    assert g.regime
    for name, burst_frames in (("a louder burst", snore(20, -48.0, 45, r)),
                               ("a much longer burst", snore(150, -59.0, 45, r)),
                               ("a bright (voice-like) burst", snore(20, -55.0, 85, r))):
        gg = new_gate()
        feed(gg, base)
        n0 = len(base)
        opens = feed(gg, burst_frames + quiet(200, r), n0)
        check(len(opens) >= 1 and gg.regime in (True, False), "%s alerts" % name)
    # a burst of another length but the usual level: unmatched, alerts (odd), and a single one does not become a pattern
    gg = new_gate()
    feed(gg, base)
    opens = feed(gg, snore(60, -59.0, 45, r) + quiet(400, r), len(base))
    check(any(rsn in ("odd", "long") for _, rsn in opens) and gg.learned == 1, "a different burst that does not repeat alerts and is not learned")

    # 3. the snoring gets louder and longer: alerts at first, then a second pattern is learned and it is quiet again
    louder = []
    for _ in range(14):
        louder += snore(r.randint(40, 60), -50.0 + r.uniform(-1.5, 1.5), 45, r) + quiet(int(r.uniform(6, 9) * 50), r)
    gg = new_gate()
    feed(gg, base)
    opens = feed(gg, louder, len(base))
    check(gg.learned == 2 and len(gg.patterns) == 2, "louder, longer snoring is learned as a second pattern (%d patterns)" % len(gg.patterns))
    check(2 <= len(opens) <= 6, "...after a few alerts (%d), not for every burst of 14" % len(opens))
    check(max(p["peak"] for p in gg.patterns) - min(p["peak"] for p in gg.patterns) > 4, "both patterns are kept")
    # and the old kind of snoring is still recognised afterwards
    opens = feed(gg, night(r, 6)[0][150:], len(base) + len(louder))
    check(len([o for o in opens]) <= 1, "the first pattern still matches afterwards (%d alerts)" % len(opens))

    # 4. saved and reloaded: after a restart the same snoring is known after a few bursts
    saved = json.loads(json.dumps(g.export()))
    g2 = new_gate()
    n = g2.load(saved)
    check(n == 1 and not g2.regime, "a loaded pattern is there, the regime waits for it to match again")
    opens = feed(g2, night(r, 10)[0])
    check(g2.regime and g2.learned == 0 and len(opens) <= 3, "after a restart the snoring is quiet after 2 bursts (%d alerts, nothing new learned)" % len(opens))

    # 5. a quiet room and a thump
    g = new_gate()
    check(not feed(g, quiet(3000, r)), "a quiet room gives no alert")
    g = new_gate()
    feed(g, base)
    pos = len(base)
    opens = feed(g, quiet(100, r) + [(-30.0, 100)] + quiet(50, r), pos)
    check(any(rsn == "impact" for _, rsn in opens), "a thump alerts at once")

# the bank is limited and drops the pattern seen longest ago
g = new_gate()
r = random.Random(7)
feed(g, quiet(100, r))
for k in range(10):
    feed(g, [(-59.0 + k * 0.0, 45)] * 0)   # nothing
    peak = -62.0 + (k % 2) * 0
g.max_patterns = 2
r = random.Random(8)
for peak, nfr in ((-60.0, 12), (-50.0, 40), (-40.0, 25)):
    for _ in range(5):
        feed(g, snore(nfr, peak, 45, r) + quiet(int(7.5 * 50), r))
check(len(g.patterns) <= 2 and g.learned >= 3, "at most max_patterns are kept (%d kept, %d learned)" % (len(g.patterns), g.learned))

# the file
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "p.json")
check(patterns.load(path) == [], "no file: no patterns")
items = [{"dur": 0.4, "peak": -59.0, "mean": -61.0, "zcr": 45.0, "iv": 7.5, "n": 12, "first": "a", "last": "b"}]
check(patterns.save(items, path) and patterns.load(path) == items, "saved and loaded back")
check(not os.path.exists(path + ".tmp"), "no temporary file is left")
os.remove(path)
open(path + ".tmp", "w").write(json.dumps({"patterns": items}))
check(patterns.load(path) == items, "a temporary file left by a power cut is used")
open(path, "w").write("{not json")
os.remove(path + ".tmp")
check(patterns.load(path) == [], "a broken file is ignored")
check(patterns.save(items, os.path.join(tmp, "nodir", "x.json")) is False, "an unwritable place gives False, no exception")
g3 = new_gate()
check(g3.load([{"dur": "x"}, {"dur": 1, "peak": -50, "mean": -52, "zcr": None, "iv": 5}, None]) == 1, "load skips bad entries")

# the child loop: learns, saves, and a second run reloads
from app import child
from helpers import config, log
from net.link import LoopbackNet

log.enabled = False


class Audio:
    def __init__(self, frames): self.f, self.i, self.mode = frames, 0, None
    def open_rx(self): self.mode = "rx"
    def open_tx(self): self.mode = "tx"
    def close(self): self.mode = None
    def set_pa(self, on): pass
    def write_silence(self): pass
    def write_payload(self, p, g=None): pass

    def read_frame(self):
        if self.i >= len(self.f):
            raise KeyboardInterrupt
        lvl, z = self.f[self.i]
        self.i += 1
        return struct.pack("<320h", *([self.i % 3000] * 320)), lvl, z


class Net:                                           # a child with a parent that hears everything (no loopback)
    peer = None
    def ensure(self): pass
    def recv(self): return None
    def send(self, data, to): return True


def run_child(frames, persist):
    cfg = config.load("/nonexistent")
    cfg["learning"].update({"persist": persist, "path": os.path.join(tmp, "child.json"), "save_every_s": 5})
    cfg["gate"]["act_db"] = ACT
    try:
        child.run(cfg, Audio(frames), Net(), None)
    except KeyboardInterrupt:
        pass


r = random.Random(11)
frames = night(r, 14)[0]
run_child(frames, True)
saved = patterns.load(os.path.join(tmp, "child.json"))
check(len(saved) == 1 and saved[0]["n"] >= 3 and saved[0].get("first"), "the child saved what it learned: %s" % (saved and {k: saved[0][k] for k in ("dur", "peak", "iv", "n")}))
shutil.rmtree(os.path.join(tmp, "child.json"), ignore_errors=True)
os.remove(os.path.join(tmp, "child.json"))
run_child(frames, False)
check(not os.path.exists(os.path.join(tmp, "child.json")), "with persist off nothing is written")

shutil.rmtree(tmp, ignore_errors=True)
finish()
