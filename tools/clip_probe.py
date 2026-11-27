# tools/clip_probe.py -- can the child unit write audio clips to flash while it listens? Run it by hand, never at boot:
#
#     bin/xtalkie clip-probe [port]        (or: python -m mpremote connect <port> run tools/clip_probe.py)
#
# It takes about 40 s and writes (then deletes) about 500 KB. It measures:
#   1. the free memory: can a 6 s and a 20 s clip be kept in RAM?
#   2. the flash: how long does one write take, in the worst case, for 640-byte appends (one frame) and for 2 KB / 4 KB
#      chunks (so how big a chunk may be without making the microphone lose audio)?
#   3. the real thing: the microphone runs (as in the child unit) while clips are written in three ways, and the longest
#      gap between two microphone frames is reported. A frame comes every 20 ms; the microphone buffer holds about
#      150 ms, so a gap above ~120 ms means lost audio.
# Copy the whole output (lines starting with XT-). Stops the program of the board; a --night unit restarts by itself
# about 15 s after the probe ends, which is normal.
import sys

if "/lib" in sys.path:
    sys.path.remove("/lib")
sys.path.insert(0, "/lib")          # our libraries first
import gc
import os
import time

import board

FILE = "/_clip_probe.bin"
FRAME_BYTES = 640                   # 320 samples of 16 bit: one 20 ms frame at 16 kHz
FRAMES_PER_S = 50


def pct(values, p):
    """The p-th percentile (0..100) of a list, without sorting it in place."""
    if not values:
        return 0
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p / 100.0))]


def stats(us_list):
    return "n=%d  mean %.1f ms  p95 %.1f ms  max %.1f ms" % (
        len(us_list), sum(us_list) / max(1, len(us_list)) / 1000.0, pct(us_list, 95) / 1000.0, max(us_list or [0]) / 1000.0)


def free_flash():
    st = os.statvfs("/")
    return st[0] * st[3]


def memory():
    gc.collect()
    print("XT-MEM heap free %d KB, in use %d KB" % (gc.mem_free() // 1024, gc.mem_alloc() // 1024))
    for seconds in (6, 20):
        n = seconds * FRAMES_PER_S
        try:
            frames = [bytes(FRAME_BYTES) for _ in range(n)]
            gc.collect()
            print("XT-MEM %2d s clip in RAM (%d frames, %d KB): OK, heap free afterwards %d KB" % (
                seconds, n, n * FRAME_BYTES // 1024, gc.mem_free() // 1024))
            del frames
        except MemoryError:
            print("XT-MEM %2d s clip in RAM: NOT ENOUGH MEMORY" % seconds)
        gc.collect()


def flash():
    print("XT-FLASH free %d KB" % (free_flash() // 1024))
    block = bytes(FRAME_BYTES)
    times = []
    t0 = time.ticks_us()
    f = open(FILE, "wb")
    print("XT-FLASH open (create): %.1f ms" % (time.ticks_diff(time.ticks_us(), t0) / 1000.0))
    for _ in range(300):
        t = time.ticks_us()
        f.write(block)
        times.append(time.ticks_diff(time.ticks_us(), t))
    t = time.ticks_us()
    f.close()
    close_ms = time.ticks_diff(time.ticks_us(), t) / 1000.0
    print("XT-FLASH 640 B appends x300:  %s   close %.1f ms" % (stats(times), close_ms))
    os.remove(FILE)
    for size in (2048, 4096):
        chunk = bytes(size)
        times = []
        f = open(FILE, "wb")
        for _ in range(40):
            t = time.ticks_us()
            f.write(chunk)
            times.append(time.ticks_diff(time.ticks_us(), t))
        f.close()
        os.remove(FILE)
        print("XT-FLASH %d B chunks x40:   %s" % (size, stats(times)))


def listen(audio, frames, writer=None):
    """Read `frames` microphone frames; writer(i, payload) may write to flash on each frame. Returns the gaps in ms
    between consecutive frames (normally about 20)."""
    gaps = []
    last = time.ticks_ms()
    for i in range(frames):
        payload, _lvl, _zc = audio.read_frame()
        now = time.ticks_ms()
        gaps.append(time.ticks_diff(now, last))
        last = now
        if writer:
            writer(i, payload)
    return gaps[5:]                                  # the first frames after opening are not representative


def gap_line(name, gaps):
    return "XT-LIVE %-34s frames %d  max gap %3d ms  gaps >60 ms: %d  >120 ms: %d" % (
        name, len(gaps), max(gaps), sum(1 for g in gaps if g > 60), sum(1 for g in gaps if g > 120))


def live():
    from board.audio import Audio
    audio = Audio()
    audio.start()
    audio.open_rx()
    for _ in range(30):
        audio.read_frame()                           # let the microphone settle
    print(gap_line("no writing (the baseline)", listen(audio, 250)))

    f = open(FILE, "wb")
    print(gap_line("A: append every frame (640 B)", listen(audio, 250, lambda i, p: f.write(p))))
    f.close()
    os.remove(FILE)

    for size in (2048, 4096):
        buf = []
        state = {"f": None, "pos": 0}

        def writer(i, payload, size=size, buf=buf, state=state):
            buf.append(payload)
            if i == 100:                              # the "event" ended: flush what was captured, a chunk per frame
                state["f"] = open(FILE, "wb")
                state["data"] = b"".join(buf)
            if state["f"] is not None and state["pos"] < len(state["data"]):
                state["f"].write(state["data"][state["pos"]:state["pos"] + size])
                state["pos"] += size

        gaps = listen(audio, 250, writer)
        if state["f"] is not None:
            state["f"].close()
            os.remove(FILE)
        print(gap_line("B: RAM, then %d B per frame" % size, gaps))
    audio.close()


def main():
    memory()
    flash()
    try:
        live()
    except Exception as e:
        print("XT-LIVE could not run:", e)
    try:
        os.remove(FILE)
    except OSError:
        pass
    print("XT-DONE")


if __name__ == "__main__":      # also true for `mpremote run`; false when a test imports the functions
    main()
