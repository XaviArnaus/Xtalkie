# dsp/clipper.py -- cut a microphone stream into clips with a plain level trigger (hardware-free).
#
# Not the snore-aware Gate: for the play mode every voice sound should be kept, soft or loud, so the rule is
# simply "clearly above the room floor". The floor follows the room quickly downwards and slowly upwards.
# A clip holds: a little pre-roll (so no first syllable is cut), the sound, and a short tail.
#   update(level_db, frame) -> None
#                              ("start", None)    a clip begins
#                              ("clip", [frames]) a clip is complete
#                              ("drop", None)     a sound too short to be a voice (a click) was ignored


class Clipper:
    def __init__(self, frame_ms=20, trig_db=12.0, end_db=6.0, on_frames=2, hang_ms=800, pre_ms=240,
                 tail_ms=300, min_ms=300, max_s=8.0):
        self.fm = frame_ms
        self.trig = trig_db
        self.end = end_db
        self.on_frames = on_frames
        self.hang = max(1, hang_ms // frame_ms)
        self.pre = max(0, pre_ms // frame_ms)
        self.tail = min(self.hang, max(0, tail_ms // frame_ms))
        self.min_loud = max(1, min_ms // frame_ms)
        self.max_frames = max(10, int(max_s * 1000) // frame_ms)
        self.floor = None
        self.reset()

    def reset(self):
        """Forget the running state but keep the floor (used when the microphone is reopened after playback)."""
        self.recording = False
        self._ring = []
        self._clip = []
        self._above = 0
        self._quiet = 0
        self._loud = 0
        self._avg = -90.0

    def update(self, level, frame):
        if level < -90.0:
            level = -90.0                       # digital silence must not drag the floor down
        if self.floor is None:
            self.floor = level
        if not self.recording:
            return self._idle(level, frame)
        return self._record(level, frame)

    def _idle(self, level, frame):
        thr = self.floor + self.trig
        ring = self._ring
        ring.append(frame)
        if len(ring) > self.pre + self.on_frames:
            del ring[0]
        if level > thr:
            self._above += 1
            if self._above >= self.on_frames:
                self.recording = True
                self._clip = list(ring)
                self._ring = []
                self._quiet = 0
                self._loud = self._above
                self._avg = level
                return ("start", None)
            return None
        self._above = 0
        if level < self.floor:
            self.floor += (level - self.floor) * 0.2
        else:
            self.floor += (level - self.floor) * 0.003
        return None

    def _record(self, level, frame):
        clip = self._clip
        clip.append(frame)
        self._avg += (level - self._avg) * 0.1
        if level > self.floor + self.end:
            self._quiet = 0
            self._loud += 1
        else:
            self._quiet += 1
        cut = len(clip) >= self.max_frames
        if self._quiet < self.hang and not cut:
            return None
        if self._quiet > self.tail:
            del clip[len(clip) - (self._quiet - self.tail):]
        loud = self._loud
        if cut:
            # a sound that never stops (TV, fan, a game that runs away): do not start again at once
            self.floor = max(self.floor, self._avg - self.trig + 3.0)
        self.reset()
        if loud < self.min_loud:
            return ("drop", None)
        return ("clip", clip)
