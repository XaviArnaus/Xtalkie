# ui/playui.py -- the screen of the play mode. Failure-isolated like the monitor's HUD: if the screen breaks,
# the game goes on without it.
#
# IMPORTANT: draw only while the microphone is NOT being read (before playback, after playback). A draw takes
# about 150 ms and the microphone buffer holds about the same: drawing during a recording would punch a hole in it.
import time


class PlayUi:
    def __init__(self, cfg, i2c, shared=None):
        """shared = (display, gfx) already opened by main.py; without it the panel is opened here."""
        self.brightness = cfg["ui"]["brightness"]
        self._shown = time.ticks_ms()
        if shared is not None:
            self.display, self.gfx = shared
        else:
            from ui.boot import open_screen
            self.display, self.gfx = open_screen(cfg, i2c)

    def _present(self, state, clips):
        if self.display is None:
            return
        try:
            from ui import screens as S
            S.draw_play(self.gfx, state, clips)
            self.display.show(self.brightness)
            self._shown = time.ticks_ms()
        except Exception as e:
            print("[ui] error, screen disabled:", e)
            try:
                self.display.hide()
            except Exception:
                pass
            self.display = None

    def ready(self, clips):
        self._present("ready", clips)

    def playing(self, clips):
        self._present("playing", clips)

    def tick(self, now, idle_off_ms):
        """Switch the screen off after a quiet while (an AMOLED that stays lit would burn in)."""
        if self.display is not None and idle_off_ms and self.display.on:
            if time.ticks_diff(now, self._shown) > idle_off_ms:
                self.display.hide()
