# dsp/effects.py -- a speed change for playback (hardware-free): speed 1.4 = higher and faster ("chipmunk"),
# 0.75 = lower and slower. Nearest-neighbour resampling: crude, and good enough for a toy.
import struct

SPEEDS = (0.75, 1.0, 1.4)           # the menu steps through these: deep, as spoken, chipmunk


def next_speed(v):
    """The speed after v in SPEEDS (the nearest one first, if v is not one of them)."""
    i = min(range(len(SPEEDS)), key=lambda k: abs(SPEEDS[k] - v))
    return SPEEDS[(i + 1) % len(SPEEDS)]


FRAME = 320                         # samples per frame, as in board.FRAMES
_FMT = "<%dh" % FRAME


def resample_frames(frames, speed, frame_len=FRAME):
    """frames: list of bytes, 16-bit little-endian mono. Returns a new list of equally long frames."""
    if speed <= 0 or abs(speed - 1.0) < 0.01:
        return list(frames)
    fmt = "<%dh" % frame_len
    vals = []
    for f in frames:
        vals.extend(struct.unpack(fmt, f))
    n_out = int(len(vals) / speed)
    out = [vals[int(i * speed)] for i in range(n_out)]
    rest = (-len(out)) % frame_len
    if rest:
        out.extend([0] * rest)
    return [struct.pack(fmt, *out[i:i + frame_len]) for i in range(0, len(out), frame_len)]
