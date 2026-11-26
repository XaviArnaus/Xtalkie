# app/play.py -- the play mode: she speaks, the device plays it back, and every clip is kept as a WAV file.
#
# One board, no network. The microphone is read continuously; a plain level trigger (dsp/clipper.py) cuts the
# stream into clips. When a clip is complete: save it (capped, see helpers/clips.py), show "LISTEN", play it
# back through the speaker, show "SPEAK", reopen the microphone. The microphone is closed during playback,
# so there is no feedback squeal, and nothing is drawn while a clip is being recorded.
import time

from dsp.clipper import Clipper
from dsp.effects import resample_frames
from helpers import log, watchdog

SKIP = 25                  # frames ignored after the microphone opens (digital silence)
STATUS_MS = 10000


def _play(audio, frames):
    audio.open_tx()
    audio.write_silence()
    audio.set_pa(True)
    for f in frames:
        watchdog.feed()
        audio.write_payload(f, None)
    for _ in range(3):
        audio.write_silence()
    audio.set_pa(False)


def run(cfg, audio, ui=None, store=None):
    pc = cfg["play"]
    if ui is None:
        import board
        from ui.playui import PlayUi
        ui = PlayUi(cfg, board.i2c())
    if store is None and pc["save"]:
        from helpers.clips import ClipStore
        store = ClipStore(pc["dir"], pc["max_total_kb"] * 1000, pc["min_free_kb"] * 1000)
    clipper = Clipper(frame_ms=20, trig_db=pc["trig_db"], end_db=pc["end_db"], hang_ms=pc["hang_ms"],
                      pre_ms=pc["pre_ms"], tail_ms=pc["tail_ms"], min_ms=pc["min_ms"], max_s=pc["max_s"])
    idle_off_ms = pc["idle_off_s"] * 1000
    speed = pc["speed"]
    n_clips = store.count() if store else 0
    warned = False

    audio.open_rx()
    ui.ready(n_clips)
    print("[play] listening%s" % (", saving clips to %s" % pc["dir"] if store else ", NOT saving"))
    log.write("play", "start,clips=%d" % n_clips)
    skip = SKIP
    last_status = time.ticks_ms()
    try:
        while True:
            payload, lvl, zc = audio.read_frame()
            watchdog.feed()
            if skip:
                skip -= 1
                continue
            now = time.ticks_ms()
            ev = clipper.update(lvl, payload)
            if ev is None:
                ui.tick(now, idle_off_ms)
                if time.ticks_diff(now, last_status) >= STATUS_MS:
                    last_status = now
                    print("[play] %6.1f dB  floor %6.1f" % (lvl, clipper.floor))
                continue
            kind, data = ev
            if kind == "start":
                print("[play] recording ...")
                continue
            if kind == "drop":
                print("[play] ignored a very short sound")
                continue
            frames = data
            secs = len(frames) * 0.02
            path = None
            if store is not None:
                path = store.save(frames, "_%.1fs" % secs)
                if path is None and not warned:
                    warned = True
                    print("[play] clip NOT saved: storage limit reached or too little free space")
                elif path is not None:
                    n_clips = store.count()
            print("[play] clip %.1f s -> %s" % (secs, path or "not saved"))
            log.write("play", "clip,%.1f s,%s" % (secs, path or "not saved"))
            out = frames if speed == 1 else resample_frames(frames, speed)
            ui.playing(n_clips)
            _play(audio, out)
            ui.ready(n_clips)
            audio.open_rx()
            skip = SKIP
            clipper.reset()
            last_status = time.ticks_ms()
    finally:
        audio.close()
