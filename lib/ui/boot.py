# ui/boot.py -- the start-up screen, and the one place that opens the panel.
#
# main.py opens the panel ONCE (open_screen) and hands it to the HUD or the play screen, so there is no double
# initialisation. The start-up screen shows the name, version, role and four steps; each step is also printed
# with its time. On the child unit after an automatic restart nothing is drawn (should_show), but the steps are
# still printed. A drawing error switches the start-up screen off and never stops the start.
import time

STEPS = ("CONFIG", "AUDIO", "NETWORK", "READY")


def open_screen(cfg, i2c):
    """(display, gfx), or (None, None) when the screen is disabled in the config or does not start."""
    u = cfg["ui"]
    if not u["enabled"]:
        return None, None
    try:
        import board
        from board.display import Display
        from ui.gfx import Gfx
        d = Display(i2c, manual=u.get("manual_refresh", False))
        d.init()
        g = Gfx(d.panel, board.LCD_W, board.LCD_H)
        print("[ui] screen ready")
        return d, g
    except Exception as e:
        print("[ui] screen disabled:", e)
        return None, None


def should_show(mode, role, manual):
    """Light the start-up screen? "always" / "never" force it. "auto": the parent and test units always show it;
    the child unit (master) only when a person started it, so a 3 a.m. restart never lights the room."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    return role != "master" or bool(manual)


class Boot:
    def __init__(self, display, gfx, role, version, show, brightness=60):
        self.display = display
        self.gfx = gfx
        self.role = role
        self.version = version
        self.shown = bool(show) and display is not None
        self.brightness = brightness
        self.steps = [[n, None] for n in STEPS]
        self.hint = None                          # a line at the bottom, e.g. how to reach the role chooser
        self.t0 = self.last = time.ticks_ms()

    def step(self, name, status="OK"):
        """A step is done: status "OK" (green), "-" (not used here, gray), or text such as "SEARCHING" (amber)."""
        now = time.ticks_ms()
        print("[boot] +%4d ms  %-8s %-9s (%d ms since the last step)" % (
            time.ticks_diff(now, self.t0), name, status, time.ticks_diff(now, self.last)))
        self.last = now
        for s in self.steps:
            if s[0] == name:
                s[1] = status
        self._draw()

    def redraw(self):
        """Draw the start-up screen again (after the chooser has used the panel)."""
        self._draw()

    def _draw(self):
        if not self.shown:
            return
        try:
            from ui import screens as S
            S.draw_boot(self.gfx, self.version, self.role, [tuple(s) for s in self.steps], self.hint)
            self.display.show(self.brightness)
        except Exception as e:
            print("[boot] screen error, start-up screen off:", e)
            self.shown = False
            try:
                self.display.hide()
            except Exception:
                pass
