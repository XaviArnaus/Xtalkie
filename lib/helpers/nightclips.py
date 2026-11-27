# helpers/nightclips.py -- audio clips of the night, kept on the child unit's flash for ANALYSIS (off by default).
#
# Two kinds of file in /night (16 kHz 16-bit mono WAV, named by local date and time of the end of the event):
#   YYYYMMDD_HHMMSS_e.wav  an alerted event: up to 0.5 s before it, the event itself (at most 6 s)
#   YYYYMMDD_HHMMSS_w.wav  a 20 s window: the last 3 s plus the next 17 s, to see the RHYTHM of the snoring
#                          (at most one per window_every_s, so the first event of an episode starts one)
# /night/index.csv has one line per file: datetime,uptime_s,file,kind,seconds,peak_db,mean_db,zcr,verdict.
# Copy them with `bin/xtalkie clips`.
#
# The microphone must never lose audio, and the flash is slow (about 40 KB/s, one write may take 100+ ms), so:
# frames are collected in RAM, then written one small chunk (CHUNK_FRAMES frames) per microphone frame, one job at a
# time (an event that arrives while a job is running is only counted). Measured on the board: chunks of 2 KB keep the
# longest gap between mic frames at ~100 ms; the mic buffer holds ~150 ms.
# Space: at most `budget` bytes of clips and `min_free` bytes of flash always left free. When full, the oldest
# EVENT clip of the busiest hour goes first (windows are rarer and worth more), so the whole night stays covered.
# Never raises: after 3 errors the recorder switches itself off and the monitor goes on.
import os
import time

from helpers import clock
from helpers.clips import wav_header

FRAME_BYTES = 640            # 320 samples of 16 bit = 20 ms
FRAMES_PER_S = 50
PRE_FRAMES = 150             # 3 s of history
EVENT_PRE = 25               # 0.5 s before an event
EVENT_MAX = 300              # 6 s
CHUNK_FRAMES = 3             # 1920 B per flash write
MAX_ERRORS = 3


def _free():
    st = os.statvfs("/")
    return st[0] * st[3]


class NightClips:
    def __init__(self, folder="/night", budget=9000000, min_free=4000000, window_s=20, window_every_s=1200,
                 free_fn=None):
        self.folder = folder
        self.budget = budget
        self.min_free = min_free
        self.window_frames = int(window_s * FRAMES_PER_S)
        self.window_every_ms = int(window_every_s * 1000)
        self._free = free_fn or _free
        self.on = True
        self.errors = 0
        self.saved = 0
        self.skipped = 0
        self.worst_ms = 0
        self.last_window = None
        self.job = None
        self._ring = [None] * PRE_FRAMES
        self._w = 0
        self._n = 0
        self.files = {}                       # name -> size
        try:
            os.mkdir(folder)
        except OSError:
            pass
        try:
            for name in os.listdir(folder):
                if name.endswith(".wav"):
                    self.files[name] = os.stat(folder + "/" + name)[6]
        except OSError:
            pass

    # ---- what the child loop calls ----
    def feed(self, payload):
        """Every microphone frame (640 bytes). Does at most one small flash operation."""
        if not self.on:
            return
        try:
            self._ring[self._w] = payload
            self._w = (self._w + 1) % PRE_FRAMES
            if self._n < PRE_FRAMES:
                self._n += 1
            j = self.job
            if j is None:
                return
            if j["phase"] == 0:                           # collecting the rest of a window
                j["frames"].append(payload)
                if len(j["frames"]) >= j["target"]:
                    j["phase"] = 1
            else:
                self._flush_step(j)
        except Exception as e:
            self._fail(e)

    def event(self, d_s, peak, mean, zcr, verdict, alerted, worthy=True):
        """An event just ended. alerted: it raised (or would raise) an alert. worthy: it may start a window."""
        if not self.on:
            return
        try:
            if self.job is not None:
                self.skipped += 1
                return
            now = time.ticks_ms()
            window = worthy and (self.last_window is None or time.ticks_diff(now, self.last_window) >= self.window_every_ms)
            if window:
                kind = "w"
                frames = self._snapshot(PRE_FRAMES)
                target = self.window_frames
                self.last_window = now
            elif alerted:
                kind = "e"
                frames = self._snapshot(min(EVENT_MAX, int(d_s * FRAMES_PER_S) + EVENT_PRE))
                target = len(frames)
            else:
                return
            if not frames:
                return
            self.job = {"phase": 1 if len(frames) >= target else 0, "frames": frames, "target": target, "kind": kind,
                        "stamp": clock.stamp(), "up": now // 1000, "d": d_s, "peak": peak, "mean": mean, "zcr": zcr,
                        "verdict": verdict, "f": None, "pos": 0, "path": None, "name": None}
        except Exception as e:
            self._fail(e)

    def minute(self):
        """Text for the per-minute log line; resets the per-minute numbers."""
        s = ",clips=%d,clipskip=%d,clipw=%d" % (len(self.files), self.skipped, self.worst_ms)
        self.skipped = 0
        self.worst_ms = 0
        return s

    def used(self):
        return sum(self.files.values())

    # ---- inside ----
    def _snapshot(self, k):
        k = min(k, self._n)
        return [self._ring[(self._w - i) % PRE_FRAMES] for i in range(k, 0, -1)]

    def _name(self, j):
        t = time.localtime()
        if t[0] >= clock.MIN_YEAR:
            return "%04d%02d%02d_%02d%02d%02d_%s.wav" % (t[0], t[1], t[2], t[3], t[4], t[5], j["kind"])
        return "t%06d_%s.wav" % (j["up"], j["kind"])        # the clock was never set: uptime instead

    def _victim(self):
        """The file to delete first: the oldest event clip of the busiest hour (else its oldest file)."""
        names = sorted(self.files)
        if not names:
            return None
        counts = {}
        for n in names:
            counts[n[:11]] = counts.get(n[:11], 0) + 1
        busiest = max(counts, key=lambda h: counts[h])
        hour = [n for n in names if n[:11] == busiest]
        events = [n for n in hour if n.endswith("_e.wav")]
        return (events or hour)[0]

    def _remove(self, name):
        try:
            os.remove(self.folder + "/" + name)
        except OSError:
            pass
        self.files.pop(name, None)

    def _flush_step(self, j):
        t0 = time.ticks_us()
        if j["f"] is None:
            n_bytes = len(j["frames"]) * FRAME_BYTES
            size = n_bytes + 44
            if self.used() + size > self.budget or self._free() - size < self.min_free:
                victim = self._victim()
                if victim is None:
                    self.skipped += 1                  # does not fit and nothing to make room: give up on this clip
                    self.job = None
                    return
                self._remove(victim)                   # one deletion per frame, then look again
            else:
                j["name"] = self._name(j)
                j["path"] = self.folder + "/" + j["name"]
                j["f"] = open(j["path"], "wb")
                j["f"].write(wav_header(n_bytes))
        else:
            frames = j["frames"]
            chunk = frames[j["pos"]:j["pos"] + CHUNK_FRAMES]
            j["f"].write(b"".join(chunk))
            j["pos"] += len(chunk)
            if j["pos"] >= len(frames):
                j["f"].close()
                j["f"] = None
                self.files[j["name"]] = len(frames) * FRAME_BYTES + 44
                self._index(j)
                self.saved += 1
                self.job = None
        ms = time.ticks_diff(time.ticks_us(), t0) // 1000
        if ms > self.worst_ms:
            self.worst_ms = ms

    def _index(self, j):
        try:
            with open(self.folder + "/index.csv", "a") as f:
                f.write("%s,%d,%s,%s,%.1f,%.1f,%.1f,%s,%s\n" % (
                    j["stamp"], j["up"], j["name"], j["kind"], len(j["frames"]) / FRAMES_PER_S,
                    j["peak"], j["mean"], "-" if j["zcr"] is None else j["zcr"], str(j["verdict"]).replace(",", ";")))
        except Exception:
            pass

    def _fail(self, e):
        j = self.job
        self.job = None
        if j is not None and j.get("f") is not None:
            try:
                j["f"].close()
            except Exception:
                pass
            self._remove(j["name"] or "")
            try:
                os.remove(j["path"])
            except Exception:
                pass
        self.errors += 1
        try:
            from helpers import log
            log.write("child", "nightclips error %s" % (e,))
        except Exception:
            pass
        if self.errors >= MAX_ERRORS:
            self.on = False
