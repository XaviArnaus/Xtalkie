# tools/record_raw.py -- record raw audio from the microphone to a file on the board, for analysis on the PC.
#
# Edit LABEL and SECONDS below, then Run it from Thonny (not main.py). Stop the monitor first: if main.py
# is running on this board, press Stop in Thonny, then open and run this file.
# Result: /raw_<LABEL>.raw  (16-bit little-endian mono, 16 kHz).  Copy it to the PC (Thonny: View > Files,
# right-click the file on the board > Download) and convert it with pc/raw2wav.py to listen to it.
#
# Suggested labels:  child_snore  child_voice  child_sleep_night  room_quiet
# Keep SECONDS <= 120 per file (the recording is kept in RAM until the end, then written to flash).

LABEL = "child_snore"
SECONDS = 120
START_DELAY_S = 5          # time to leave the room / get ready

import sys

if "/lib" in sys.path:
    sys.path.remove("/lib")
sys.path.insert(0, "/lib")          # our libraries first

import time

from board.audio import Audio
from helpers import config


def main():
    cfg = config.load()
    a = cfg["audio"]
    audio = Audio(mic_gain=a["mic_gain"], volume=a["volume"], playback_gain=a["playback_gain"])
    audio.start()
    audio.open_rx()
    path = "/raw_%s.raw" % LABEL
    total = SECONDS * 50
    print("Recording '%s' for %d s in %d s ..." % (LABEL, SECONDS, START_DELAY_S))
    chunks = []
    n = 0
    try:
        while n < total + START_DELAY_S * 50 + 25:
            payload, level, zc = audio.read_frame()
            n += 1
            if n <= 25 + START_DELAY_S * 50:
                continue                                # start-up silence and the get-ready delay
            chunks.append(payload)
            if len(chunks) % 250 == 0:
                print("%4d s  level %6.1f dBFS" % (len(chunks) // 50, level))
    finally:
        audio.close()
    print("writing %s ..." % path)
    with open(path, "wb") as f:
        for c in chunks:
            f.write(c)
    print("saved %d frames (%.0f s). Download it with Thonny: View > Files." % (len(chunks), len(chunks) / 50))


main()
