# dsp/gate.py -- event-based gate for the baby-monitor mode (pure Python, no hardware access).
#
# Designed from real recordings (silence / snore / voice / mixed), see the chat for the numbers.
#   * floor    : level of the QUIET gaps (silence), a lower-envelope tracker. Not the snore level.
#   * activity : level > floor + act_db (act_db is the user-facing sensitivity, in dB).
#   * events   : runs of activity, merged across gaps shorter than merge_ms.
#   * snore model: events of snoring-like length that recur at a regular rhythm are learned
#                  (median level, peak, length, interval, zero-crossing rate). Once learned, a
#                  "regime" is active and snore-like bursts are NOT alerted. Everything else is.
#   * alert reasons while a snore regime is active:
#         impact: a single frame far above the floor and above the usual snore peak (bang, thump)
#         early : starts too soon after the last snore burst (inside the "dead zone")
#         loud  : peak or running mean clearly above the usual burst level
#         voice : zero-crossing rate at or above zcr_cap (speech is "brighter" than any snore style seen)
#         long  : lasts longer than any snore burst
#         short : much shorter than a snore burst (decided when the event ends)
#         lapse : the rhythm was lost for too long -> the next event alerts, and the rhythm is
#                 re-learned from the next 3 bursts (the profile is remembered for memory_s)
#   * without a regime every event alerts (that is the learning phase after a quiet spell).
#   * snore style changes: when 2 bursts in a row are alerted as "loud" but are otherwise snore-shaped
#     (right length, rhythm, below zcr_cap) they replace the learned profile (self.absorbed counts this).
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
                 zcr_cap=64.0, zcr_min_frames=10, voice_min_ms=120, absorb_events=2, hang_learn_ms=600,
                 short_frac=0.6, short_min_ms=120, short_abs_max=0.5,
                 snore_dur_min=0.5, snore_dur_max=2.5, regularity=0.6,
                 interval_min=1.5, interval_max=7.0, early_frac=0.8,
                 lapse_factor=1.8, lapse_min_s=8.0,
                 learn_events=3, reform_events=2, memory_s=3600,
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
        self.absorb_events = absorb_events
        self.hang_learn_ms = hang_learn_ms    # shorter hang while the snore rhythm is still being learned
        self.short_frac = short_frac          # event shorter than this x a snore burst alerts (None = off)
        self.short_min_ms = short_min_ms
        self.short_abs_max = short_abs_max    # ...and also shorter than this many seconds
        self.snore_dur_min = snore_dur_min
        self.snore_dur_max = snore_dur_max
        self.regularity = regularity
        self.interval_min = interval_min
        self.interval_max = interval_max
        self.early_frac = early_frac
        self.lapse_factor = lapse_factor
        self.lapse_min_s = lapse_min_s
        self.learn_events = learn_events
        self.reform_events = reform_events
        self.memory_s = memory_s
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

        self._cands = []                      # recent snore-like events: (onset, dur_s, mean, peak, zcr)
        self._prof = None                     # cached profile, reset whenever _cands changes
        self._odd = []                        # consecutive loud-but-snore-shaped bursts (style change candidates)
        self.absorbed = 0
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
        """(mean, peak, median interval_s, dur_s, zcr or None, shortest interval_s) of the recent snore bursts."""
        if self._prof is not None:
            return self._prof
        c = self._cands[-8:]
        ivs = [(c[i][0] - c[i - 1][0]) * self.frame_ms / 1000 for i in range(1, len(c))]
        zs = [x[4] for x in c if x[4] is not None]
        self._prof = (_med([x[2] for x in c]), _med([x[3] for x in c]),
                      _med(ivs) if ivs else 3.0, _med([x[1] for x in c]),
                      _med(zs) if zs else None, min(ivs) if ivs else 3.0)
        return self._prof

    def _ev_zcr(self):
        return (self._ev_zs / self._ev_zn) if self._ev_zn else None

    def _zcr_high(self, z):
        return self.zcr_cap is not None and z is not None and z >= self.zcr_cap

    def _voicey(self, min_frames):
        """True if the running event is 'brighter' than any snore: zero crossings at or above zcr_cap."""
        if self.zcr_cap is None or self._ev_zn < min_frames:
            return False
        return self._ev_zcr() >= self.zcr_cap

    def _consistent(self, n):
        c = self._cands[-n:]
        if len(c) < n:
            return False
        ivs = []
        for i in range(1, n):
            iv = (c[i][0] - c[i - 1][0]) * self.frame_ms / 1000
            if iv < self.interval_min or iv > self.interval_max:
                return False
            ivs.append(iv)
        if (max(ivs) - min(ivs)) > self.regularity * _med(ivs):
            return False
        m = _med([x[2] for x in c])
        for x in c:
            if abs(x[2] - m) > 6.0:
                return False
        return True

    def _fresh_profile(self):
        if not self._cands:
            return False
        age = (self.t - self._cands[-1][0]) * self.frame_ms / 1000
        return age < self.memory_s

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
        if dur_ms / 1000 > self.snore_dur_max:
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

        # events not alerted while a snore rhythm is active: look at them again now that they are complete
        if self.regime and not self._ev_alert:
            late = None
            if dur_s * 1000 >= self.voice_min_ms and self._voicey(3):
                late = "voice"
            elif (self.short_frac is not None and dur_s * 1000 >= self.short_min_ms
                  and dur_s < min(self.short_frac * self._profile()[3], self.short_abs_max)):
                late = "short"
            if late:
                self._ev_reason = late
                self._late = (late, int(dur_s * 1000) + self.merge_ms)

        shaped = self.snore_dur_min <= dur_s <= self.snore_dur_max and not self._zcr_high(z)
        if self._ev_reason == "loud" and self.snore_dur_min <= dur_s <= self.snore_dur_max:
            self._last_rhythm_onset = self._ev_start  # a loud burst of snore length keeps the rhythm alive
        elif self._ev_reason == "voice" and self.snore_dur_min <= dur_s <= self.snore_dur_max:
            self._last_rhythm_onset = self._ev_start
        snorelike = shaped and self._ev_reason in (None, "unknown", "lapse")
        if snorelike:
            self._odd = []
            self._cands.append((self._ev_start, dur_s, mean, self._ev_peak, z))
            if len(self._cands) > 12:
                self._cands = self._cands[-12:]
            self._prof = None
            self._last_snore_onset = self._ev_start
            self._last_rhythm_onset = self._ev_start
            need = self.reform_events if self._fresh_profile() and len(self._cands) > self.learn_events else self.learn_events
            if self._consistent(need):
                self.regime = True
        elif self._ev_reason == "loud" and shaped:
            self._odd.append((self._ev_start, dur_s, mean, self._ev_peak, z))
            self._odd = self._odd[-3:]
            self._try_absorb()
        else:
            self._odd = []
        if self._ev_reason in (None,):
            verdict = "ignored (snore burst)" if snorelike else "ignored (fragment)"
        elif self._ev_reason == "unknown":
            verdict = "alerted: unknown (learning)"
        else:
            verdict = "ALERT: " + self._ev_reason
        self.last_event = ((self._ev_start - 1) * fm / 1000, dur_s, self._ev_peak, mean, z, verdict)

    def _try_absorb(self):
        """Two loud bursts in a row that are otherwise snore-shaped: the snore changed, learn the new style."""
        o = self._odd
        if len(o) < self.absorb_events:
            return
        c = o[-self.absorb_events:]
        for i in range(1, len(c)):
            iv = (c[i][0] - c[i - 1][0]) * self.frame_ms / 1000
            if iv < self.interval_min or iv > self.interval_max:
                return
        m = _med([x[2] for x in c])
        for x in c:
            if abs(x[2] - m) > 6.0:
                return
        self._cands = list(c)                 # the new style replaces the old profile
        self._prof = None
        self._last_snore_onset = c[-1][0]
        self._last_rhythm_onset = c[-1][0]
        self._odd = []
        self.absorbed += 1
