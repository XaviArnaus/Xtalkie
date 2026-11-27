# dsp/gate.py -- event-based gate for the baby-monitor mode (pure Python, no hardware access).
#
# Designed from real recordings (silence / snore / voice / mixed), see the chat for the numbers.
#   * floor    : level of the QUIET gaps (silence), a lower-envelope tracker. Not the snore level.
#   * activity : level > floor + act_db (act_db is the user-facing sensitivity, in dB).
#   * events   : runs of activity, merged across gaps shorter than merge_ms.
#   * snore PATTERNS: a bank of learned burst shapes (length, peak, level, brightness, rhythm). Bursts differ
#                  from one another (a snore can be 0.2 s or 0.8 s, louder or softer), so a pattern is a RANGE of
#                  length and peak that GROWS with every burst it matches: an event "matches" when its length is
#                  within max(0.3 s, 40 %) of that range, its peak within 6 dB of it and its brightness (zero
#                  crossings) within 30 of the pattern's. A matching event is NOT alerted while the rhythm holds
#                  (the "regime"). Several patterns can be learned during a night.
#   * learning   : events that match nothing are candidates. 3 that look alike and come at a regular rhythm
#                  (1..20 s apart) become a new pattern: this is how the unit re-learns when the snoring gets
#                  louder or longer, and why a deviation that does NOT repeat stays an alert.
#   * alert reasons while a snore regime is active:
#         impact: a single frame far above the floor and above the loudest learned snore peak (bang, thump)
#         early : starts too soon after the last snore burst (inside the "dead zone")
#         loud  : peak or running mean clearly above the loudest learned burst
#         voice : zero-crossing rate at or above zcr_cap (speech is "brighter" than any snore style seen)
#         long  : lasts clearly longer than the longest learned burst
#         odd   : (decided when the event ends) matches no learned pattern
#         lapse : the rhythm was lost for too long -> the next event alerts; the patterns are kept and the
#                 regime comes back after reform_events matching bursts
#   * without a regime every event alerts (that is the learning phase after a quiet spell).
#   * the bank can be saved and reloaded: export() / load() (see helpers/patterns.py); `stamper` (optional callable
#     returning a time text) stamps the first/last time a pattern was seen; `learned` counts new patterns and
#     `pat_dirty` says the bank changed since the last save.
#
# Feed one frame to update(level_db, zcr): level in dBFS, zcr = zero crossings in that frame
# (zcr may be omitted, the "voice" cue is then simply off). It returns "open", "close" or None.
# After an "open", self.reason says why and self.onset_ms_ago how far back the event started
# (for pre-roll). When an event ends, self.ended is True for that frame and self.last_event holds
# (start_s, dur_s, peak_db, mean_db, zcr, verdict).

EVENT_OPEN = "open"
EVENT_CLOSE = "close"


def _med(lst):
    s = sorted(lst)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


class Gate:
    def __init__(self, frame_ms=20, act_db=10.0, merge_ms=200, min_ms=80,
                 sustain_ms=100, hang_ms=1000,
                 peak_excess_db=7.0, mean_excess_db=6.0, mean_check_ms=300,
                 impact_db=38.0, impact_excess_db=10.0,
                 zcr_cap=64.0, zcr_min_frames=10, voice_min_ms=120, hang_learn_ms=600,
                 short_min_ms=120, regularity=0.6,
                 interval_min=1.0, interval_max=20.0, early_frac=0.8,
                 lapse_factor=1.8, lapse_min_s=8.0,
                 learn_events=3, reform_events=2,
                 dur_tol=0.4, dur_tol_min=0.3, level_tol=6.0, zcr_tol=30.0, max_patterns=8,
                 long_factor=1.5, long_extra_s=0.3,
                 floor_fall=0.02, floor_rise=0.002, floor_init_frames=50):
        self.frame_ms = frame_ms
        self.act_db = act_db                  # sensitivity: how far above the quiet floor counts as activity
        self.merge_ms = merge_ms
        self.min_ms = min_ms
        self.sustain_ms = sustain_ms
        self.hang_ms = hang_ms
        self.peak_excess_db = peak_excess_db
        self.mean_excess_db = mean_excess_db
        self.mean_check_ms = mean_check_ms
        self.impact_db = impact_db            # one frame this far above the floor alerts at once
        self.impact_excess_db = impact_excess_db
        self.zcr_cap = zcr_cap                # events with at least this many zero crossings per frame are speech-like (None = off)
        self.zcr_min_frames = zcr_min_frames
        self.voice_min_ms = voice_min_ms
        self.hang_learn_ms = hang_learn_ms    # shorter hang while the snore rhythm is still being learned
        self.short_min_ms = short_min_ms      # an unmatched event must last this long to alert as "odd"
        self.regularity = regularity
        self.interval_min = interval_min
        self.interval_max = interval_max
        self.early_frac = early_frac
        self.lapse_factor = lapse_factor
        self.lapse_min_s = lapse_min_s
        self.learn_events = learn_events
        self.reform_events = reform_events
        self.dur_tol = dur_tol                # a burst matches a pattern within max(dur_tol_min s, dur_tol x length)
        self.dur_tol_min = dur_tol_min
        self.level_tol = level_tol            # ... within this many dB of the pattern's peak
        self.zcr_tol = zcr_tol                # ... and (if both are known) this many zero crossings per frame
        self.max_patterns = max_patterns
        self.long_factor = long_factor        # "long": longer than the longest pattern x this + long_extra_s
        self.long_extra_s = long_extra_s
        self.floor_fall = floor_fall
        self.floor_rise = floor_rise
        self.floor_init_frames = floor_init_frames

        self.floor_db = None
        self._init_buf = []
        self.t = 0                            # frame counter
        self.gate_open = False
        self._hang_left = 0
        self.reason = None
        self.onset_ms_ago = 0
        self.ended = False
        self.last_event = None

        self._in_event = False
        self._ev_start = 0
        self._ev_last = 0
        self._ev_sum = 0.0
        self._ev_n = 0
        self._ev_peak = -99.0
        self._ev_zs = 0.0                     # zcr sum over the strong frames of the event
        self._ev_zn = 0
        self._ev_alert = False
        self._ev_reason = None
        self._late = None

        self.patterns = []                    # learned: dicts dur, peak, mean, zcr, iv, n (+ first/last, last_t)
        self._cands = []                      # recent events that matched nothing: (onset, dur_s, mean, peak, zcr)
        self._ivs = []                        # recent intervals (s) between snore bursts
        self._reform = 0                      # matching bursts in a row since the regime was lost
        self.learned = 0                      # new patterns learned since start
        self.pat_dirty = False
        self.stamper = None
        self.regime = False
        self._last_snore_onset = None
        self._last_rhythm_onset = None

    # ---- helpers -------------------------------------------------------
    @property
    def threshold_db(self):
        return (self.floor_db if self.floor_db is not None else -80.0) + self.act_db

    @property
    def state_name(self):
        if self.floor_db is None:
            return "INIT"
        if self.gate_open:
            return "OPEN"
        if self._in_event:
            return "EVENT"
        return "SNORE" if self.regime else "QUIET"

    def _profile(self):
        """(mean, peak, median interval_s, dur_s, zcr or None, shortest interval_s) over the learned patterns:
        the LOUDEST / LONGEST values, so only what exceeds every learned burst counts as louder or longer."""
        P = self.patterns
        zs = [p["zcr"] for p in P if p["zcr"] is not None]
        ivs = self._ivs or [p["iv"] for p in P]
        return (max(p["mean"] for p in P), max(p["peak"] for p in P), _med(ivs) if ivs else 3.0,
                max(p["dmax"] for p in P), _med(zs) if zs else None, min(ivs) if ivs else 3.0)

    def _ev_zcr(self):
        return (self._ev_zs / self._ev_zn) if self._ev_zn else None

    def _zcr_high(self, z):
        return self.zcr_cap is not None and z is not None and z >= self.zcr_cap

    def _voicey(self, min_frames):
        """True if the running event is 'brighter' than any snore: zero crossings at or above zcr_cap."""
        if self.zcr_cap is None or self._ev_zn < min_frames:
            return False
        return self._ev_zcr() >= self.zcr_cap

    @staticmethod
    def _gap(x, lo, hi):
        """0 inside [lo, hi], else the distance to the nearest end."""
        return lo - x if x < lo else (x - hi if x > hi else 0.0)

    def _pdist(self, dur_s, peak, z, p):
        """How far a burst is from a pattern's ranges (<= 3 and every part <= 1 means it matches), or None."""
        td = max(self.dur_tol_min, self.dur_tol * min(dur_s, p["dmax"]))
        sd = self._gap(dur_s, p["dmin"], p["dmax"]) / td
        sp = self._gap(peak, p["pmin"], p["pmax"]) / self.level_tol
        sz = 0.0 if (z is None or p["zcr"] is None) else abs(z - p["zcr"]) / self.zcr_tol
        if sd > 1.0 or sp > 1.0 or sz > 1.0:
            return None
        return sd + sp + sz

    def _close(self, d1, pk1, z1, d2, pk2, z2):
        """How far apart two bursts are (0 = identical, <= 1 = similar), or None when they are not similar."""
        td = max(self.dur_tol_min, self.dur_tol * max(d1, d2))
        sd = abs(d1 - d2) / td
        sp = abs(pk1 - pk2) / self.level_tol
        sz = 0.0
        if z1 is not None and z2 is not None:
            sz = abs(z1 - z2) / self.zcr_tol
        if sd > 1.0 or sp > 1.0 or sz > 1.0:
            return None
        return sd + sp + sz

    def _match(self, dur_s, peak, z):
        """The learned pattern this burst belongs to, or None."""
        best, best_d = None, None
        for p in self.patterns:
            d = self._pdist(dur_s, peak, z, p)
            if d is not None and (best_d is None or d < best_d):
                best, best_d = p, d
        return best

    def _consistent(self, c):
        """Candidates c (similar to each other): a regular rhythm of similar level."""
        ivs = []
        for i in range(1, len(c)):
            iv = (c[i][0] - c[i - 1][0]) * self.frame_ms / 1000
            if iv < self.interval_min or iv > self.interval_max:
                return False
            ivs.append(iv)
        if (max(ivs) - min(ivs)) > self.regularity * _med(ivs):
            return False
        m = _med([x[2] for x in c])
        for x in c:
            if abs(x[2] - m) > self.level_tol:
                return False
        return True

    def _stamp(self):
        try:
            return self.stamper() if self.stamper else None
        except Exception:
            return None

    def _learn_match(self, p, start, dur_s, mean, peak, z):
        """A burst that belongs to a learned pattern: refine the pattern, keep the rhythm, maybe restore the regime."""
        k = 0.2
        p["dur"] += (dur_s - p["dur"]) * k
        p["peak"] += (peak - p["peak"]) * k
        p["mean"] += (mean - p["mean"]) * k
        if z is not None:
            p["zcr"] = z if p["zcr"] is None else p["zcr"] + (z - p["zcr"]) * k
        p["dmin"] = min(p["dmin"], dur_s)
        p["dmax"] = max(p["dmax"], dur_s)
        p["pmin"] = min(p["pmin"], peak)
        p["pmax"] = max(p["pmax"], peak)
        p["n"] += 1
        p["last_t"] = self.t
        if self._last_snore_onset is not None:
            iv = (start - self._last_snore_onset) * self.frame_ms / 1000
            if self.interval_min <= iv <= self.interval_max * 1.5:
                self._ivs = (self._ivs + [iv])[-8:]
                p["iv"] += (iv - p["iv"]) * k
        st = self._stamp()
        if st:
            p["last"] = st
        self._last_snore_onset = start
        self._last_rhythm_onset = start
        self._reform += 1
        if not self.regime and self._reform >= self.reform_events:
            self.regime = True
        if p["n"] % 10 == 0 or dur_s > p["dmax"] - 1e-9 or peak > p["pmax"] - 1e-9:
            self.pat_dirty = True

    def _add_cand(self, start, dur_s, mean, peak, z):
        """An event that matched nothing. Three alike at a regular rhythm become a new pattern."""
        horizon = self.interval_max * 4 * 1000 // self.frame_ms
        self._cands = [c for c in self._cands if self.t - c[0] <= horizon]
        self._cands.append((start, dur_s, mean, peak, z))
        self._cands = self._cands[-12:]
        last = self._cands[-1]
        alike = [c for c in self._cands if self._close(c[1], c[3], c[4], last[1], last[3], last[4]) is not None]
        if len(alike) < self.learn_events:
            return
        sel = alike[-self.learn_events:]
        if not self._consistent(sel):
            return
        zs = [c[4] for c in sel if c[4] is not None]
        ivs = [(sel[i][0] - sel[i - 1][0]) * self.frame_ms / 1000 for i in range(1, len(sel))]
        span = [c for c in self._cands if sel[0][0] <= c[0] <= sel[-1][0]]      # the events between them count for the rhythm
        gaps = [(span[i][0] - span[i - 1][0]) * self.frame_ms / 1000 for i in range(1, len(span))]
        gaps = [x for x in gaps if x >= self.interval_min]
        if gaps:
            ivs = gaps
        st = self._stamp()
        if len(self.patterns) >= self.max_patterns:                    # forget the pattern seen longest ago
            self.patterns.remove(min(self.patterns, key=lambda q: q["last_t"]))
        self.patterns.append({"dur": _med([c[1] for c in sel]), "peak": _med([c[3] for c in sel]),
                              "dmin": min(c[1] for c in sel), "dmax": max(c[1] for c in sel),
                              "pmin": min(c[3] for c in sel), "pmax": max(c[3] for c in sel),
                              "mean": _med([c[2] for c in sel]), "zcr": _med(zs) if zs else None,
                              "iv": _med(ivs), "n": len(sel), "first": st, "last": st, "last_t": self.t})
        self._cands = [c for c in self._cands if c not in sel]
        self._ivs = ivs
        self._last_snore_onset = sel[-1][0]
        self._last_rhythm_onset = sel[-1][0]
        self._reform = self.reform_events
        self.regime = True
        self.learned += 1
        self.pat_dirty = True

    def export(self):
        """The learned patterns as plain data (numbers and texts), to save as JSON."""
        out = []
        for p in self.patterns:
            q = {k: v for k, v in p.items() if k != "last_t"}
            for k in ("dur", "peak", "mean", "zcr", "iv", "dmin", "dmax", "pmin", "pmax"):
                if q.get(k) is not None:
                    q[k] = round(q[k], 2)
            out.append(q)
        return out

    def load(self, items):
        """Start with saved patterns (bad entries are skipped). The regime stays off until they match again."""
        loaded = []
        for q in items or []:
            try:
                p = {"dur": float(q["dur"]), "peak": float(q["peak"]), "mean": float(q["mean"]),
                     "dmin": float(q.get("dmin", q["dur"])), "dmax": float(q.get("dmax", q["dur"])),
                     "pmin": float(q.get("pmin", q["peak"])), "pmax": float(q.get("pmax", q["peak"])),
                     "zcr": None if q.get("zcr") is None else float(q["zcr"]), "iv": float(q["iv"]),
                     "n": int(q.get("n", 1)), "first": q.get("first"), "last": q.get("last"), "last_t": self.t}
            except Exception:
                continue
            loaded.append(p)
        self.patterns = loaded[-self.max_patterns:]
        self._ivs = []
        self.regime = False
        self._reform = 0
        return len(self.patterns)

    def _impact(self, level_db):
        lim = self.floor_db + self.impact_db
        if self.regime:
            lim = max(lim, self._profile()[1] + self.impact_excess_db)
        return level_db > lim

    # ---- alert decision ----------------------------------------------------
    def _alert_reason(self, dur_ms):
        """Return a reason string if this running event should alert, else None."""
        if not self.regime:
            return "unknown"
        mean_p, peak_p, iv_p, dur_p, z_p, iv_min = self._profile()
        since_rhythm = (self._ev_start - self._last_rhythm_onset) * self.frame_ms / 1000
        if since_rhythm > max(self.lapse_factor * iv_p, self.lapse_min_s):
            self.regime = False               # rhythm lost
            self._reform = 0
            return "lapse"
        since = (self._ev_start - self._last_snore_onset) * self.frame_ms / 1000
        if since < self.early_frac * iv_min:
            return "early"
        if self._ev_peak > peak_p + self.peak_excess_db:
            return "loud"
        if dur_ms >= self.mean_check_ms and (self._ev_sum / self._ev_n) > mean_p + self.mean_excess_db:
            return "loud"
        if self._voicey(self.zcr_min_frames):
            return "voice"
        if dur_ms / 1000 > dur_p * self.long_factor + self.long_extra_s:
            return "long"
        return None

    # ---- main --------------------------------------------------------------
    def _hang_for(self, reason):
        return self.hang_learn_ms if reason == "unknown" else self.hang_ms

    def _open(self, reason, onset_ms):
        self.gate_open = True
        self.reason = reason
        self.onset_ms_ago = onset_ms
        self._hang_left = self._hang_for(reason)

    def update(self, level_db, zcr=None):
        fm = self.frame_ms
        self.t += 1
        ev = None
        self.ended = False
        self._late = None

        if self.floor_db is None:
            self._init_buf.append(level_db)
            if len(self._init_buf) >= self.floor_init_frames:
                self.floor_db = _med(self._init_buf)
                self._init_buf = []
            return None

        thr = self.floor_db + self.act_db
        active = level_db > thr
        strong = level_db > thr + 5

        if not self._in_event:
            if active:
                self._in_event = True
                self._ev_start = self.t
                self._ev_last = self.t
                self._ev_sum = level_db
                self._ev_n = 1
                self._ev_peak = level_db
                self._ev_zs = 0.0
                self._ev_zn = 0
                if zcr is not None and strong:
                    self._ev_zs = float(zcr)
                    self._ev_zn = 1
                self._ev_alert = False
                self._ev_reason = None
            else:
                # quiet frame: floor follows the bottom of the level distribution
                if level_db < self.floor_db:
                    self.floor_db += (level_db - self.floor_db) * self.floor_fall
                else:
                    self.floor_db += (level_db - self.floor_db) * self.floor_rise
        else:
            if active:
                self._ev_last = self.t
                self._ev_sum += level_db
                self._ev_n += 1
                if level_db > self._ev_peak:
                    self._ev_peak = level_db
                if zcr is not None and strong:
                    self._ev_zs += zcr
                    self._ev_zn += 1
            elif (self.t - self._ev_last) * fm > self.merge_ms:
                self._end_event()

        if self._late and not self.gate_open:            # recognised only when the event ended
            self._open(self._late[0], self._late[1])
            return EVENT_OPEN

        if self._in_event:
            dur_ms = (self._ev_last - self._ev_start + 1) * fm
            if not self._ev_alert and self._impact(level_db):
                self._ev_alert = True
                self._ev_reason = "impact"
                if not self.gate_open:
                    self._open("impact", (self.t - self._ev_start) * fm)
                    ev = EVENT_OPEN
            if not self._ev_alert and dur_ms >= self.sustain_ms:
                r = self._alert_reason(dur_ms)
                if r:
                    self._ev_alert = True
                    self._ev_reason = r
                    if not self.gate_open:
                        self._open(r, (self.t - self._ev_start) * fm)
                        ev = EVENT_OPEN
            self._hang_left = self._hang_for(self._ev_reason)
        elif self.gate_open:
            self._hang_left -= fm
            if self._hang_left <= 0:
                self.gate_open = False
                self.reason = None
                ev = EVENT_CLOSE
        return ev

    def _end_event(self):
        fm = self.frame_ms
        self._in_event = False
        self.ended = True
        dur_s = (self._ev_last - self._ev_start + 1) * fm / 1000
        mean = self._ev_sum / self._ev_n
        z = self._ev_zcr()
        if dur_s * 1000 < self.min_ms and self._ev_reason != "impact":
            self.last_event = ((self._ev_start - 1) * fm / 1000, dur_s, self._ev_peak, mean, z, "noise (too short)")
            return

        shaped = not self._zcr_high(z)
        pat = self._match(dur_s, self._ev_peak, z) if shaped else None

        # events not alerted while a snore rhythm is active: look at them again now that they are complete
        if self.regime and not self._ev_alert:
            late = None
            if dur_s * 1000 >= self.voice_min_ms and self._voicey(3):
                late = "voice"
            elif dur_s * 1000 >= self.short_min_ms and pat is None:
                late = "odd"
            if late:
                self._ev_reason = late
                self._late = (late, int(dur_s * 1000) + self.merge_ms)

        reason = self._ev_reason
        if shaped and reason in ("loud", "odd", "long"):
            self._last_rhythm_onset = self._ev_start      # still breathing: a deviating burst keeps the rhythm alive
        elif reason == "voice" and dur_s <= 2.5:
            self._last_rhythm_onset = self._ev_start
        snorelike = shaped and reason in (None, "unknown", "lapse")
        if (snorelike or (shaped and reason == "early")) and pat is not None:      # an "early" burst still teaches the rhythm
            self._learn_match(pat, self._ev_start, dur_s, mean, self._ev_peak, z)
        elif shaped and reason in (None, "unknown", "lapse", "loud", "odd", "long"):
            self._reform = 0
            self._add_cand(self._ev_start, dur_s, mean, self._ev_peak, z)
        else:
            self._reform = 0
        if reason in (None,):
            verdict = "ignored (snore burst)" if (snorelike and pat is not None) else "ignored (fragment)"
        elif reason == "unknown":
            verdict = "alerted: unknown (learning)"
        else:
            verdict = "ALERT: " + reason
        self.last_event = ((self._ev_start - 1) * fm / 1000, dur_s, self._ev_peak, mean, z, verdict)
