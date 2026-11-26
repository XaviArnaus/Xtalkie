# ui/playui.py -- the screen and button of the play mode. Failure-isolated like the monitor's HUD: if the screen
# breaks, the game goes on without it.
#
# IMPORTANT: draw only while the microphone is NOT being read (before playback, after playback). A draw takes
# about 150 ms and the microphone buffer holds about the same: drawing during a recording would punch a hole in it.
# So the button is only noticed while recording, never acted on: a long press sets `menu_wanted`, and app/play.py
# opens the menu (run_menu, with the microphone closed) as soon as no clip is being recorded.
import time

from ui import menu


class PlayUi:
    def __init__(self, cfg, i2c, shared=None):
        """shared = (display, gfx) already opened by main.py; without it the panel is opened here."""
        self.brightness = cfg["ui"]["brightness"]
        self._shown = time.ticks_ms()
        self._last = ("ready", 0)
        self.recording = False                    # set by app/play.py before every tick()
        self.menu_wanted = False
        if shared is not None:
            self.display, self.gfx = shared
        else:
            from ui.boot import open_screen
            self.display, self.gfx = open_screen(cfg, i2c)
        try:
            self.btn = menu.Button()
        except Exception as e:
            print("[ui] button not available:", e)
            self.btn = None

    def _show(self, draw):
        """draw(gfx) then show it; any error switches the screen off for good."""
        if self.display is None:
            return False
        try:
            draw(self.gfx)
            self.display.show(self.brightness)
            self._shown = time.ticks_ms()
            return True
        except Exception as e:
            print("[ui] error, screen disabled:", e)
            try:
                self.display.hide()
            except Exception:
                pass
            self.display = None
            return False

    def _present(self, state, clips):
        from ui import screens as S
        self._last = (state, clips)
        self._show(lambda g: S.draw_play(g, state, clips))

    def ready(self, clips):
        self._present("ready", clips)

    def playing(self, clips):
        self._present("playing", clips)

    def tick(self, now, idle_off_ms):
        """Button, and the screen off after a quiet while (an AMOLED that stays lit would burn in)."""
        ev = self.btn.read(now) if self.btn is not None else None
        if ev and not self.recording and self.display is not None:
            if ev == "long":
                self.menu_wanted = True
            elif not self.display.on:             # a tap wakes the screen
                self._present(*self._last)
        if self.display is not None and idle_off_ms and self.display.on:
            if time.ticks_diff(now, self._shown) > idle_off_ms:
                self.display.hide()

    def run_menu(self, audio, speed_get, speed_step, feed):
        """The play menu (VOLUME, SPEED, ROLE, EXIT), blocking. The caller has closed the microphone. Tap = next,
        hold = select. Leaves after 20 s of nothing. A role switch writes config.json and restarts the board."""
        from ui import screens as S
        self.menu_wanted = False
        if self.btn is None or self.display is None:
            return
        items = ("VOLUME", "SPEED", "ROLE", "EXIT")
        vol = menu.volume_actions(audio)
        idx, sw = 0, None
        until = time.ticks_add(time.ticks_ms(), 20000)

        def redraw(now):
            if sw is None:
                labels = ["VOLUME %d" % audio.level, "SPEED %s" % speed_get(), "ROLE", "EXIT"]
                self._show(lambda g: S.draw_menu(g, labels, idx))
            elif sw.state == "pick":
                labels, i = sw.labels(), sw.idx
                self._show(lambda g: S.draw_menu(g, labels, i, "ROLE"))
            elif sw.state == "confirm":
                target = sw.target
                self._show(lambda g: S.draw_confirm(g, target))
            elif sw.state == "done":
                self._show(lambda g: S.draw_message(g, "RESTARTING", "", S.GREEN))
            else:
                err = sw.error
                self._show(lambda g: S.draw_message(g, "NOT SAVED", err, S.AMBER))
            return time.ticks_add(now, 4000 if (sw is not None and sw.state == "failed") else 20000)

        until = redraw(time.ticks_ms())
        while self.display is not None:
            feed()
            now = time.ticks_ms()
            ev = self.btn.read(now)
            if ev:
                if sw is None:
                    if ev == "short":
                        idx = (idx + 1) % len(items)
                    elif items[idx] == "VOLUME":
                        vol["volume_step"]()
                    elif items[idx] == "SPEED":
                        speed_step()
                    elif items[idx] == "ROLE":
                        sw = menu.RoleSwitch("play")
                    else:
                        return
                else:
                    res = sw.tap() if ev == "short" else sw.hold()
                    if res == "cancel":
                        sw = None
                    elif res == "reset":
                        from helpers import log
                        log.write("ui", "role switch play -> %s" % sw.target)
                        print("[ui] role play -> %s: restarting" % sw.target)
                        redraw(now)
                        menu.restart()
                        return
                until = redraw(now)
            elif time.ticks_diff(now, until) >= 0:
                if sw is not None and sw.state == "failed":
                    sw = None
                    until = redraw(now)
                else:
                    return
            time.sleep_ms(20)
