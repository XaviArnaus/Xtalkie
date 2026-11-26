# ui/menu.py -- pieces of the menu shared by every role (the parent unit's HUD and the play mode).
#
#   Button        the BOOT button: tap = "short", hold >= 1.2 s = "long" (reported on release)
#   volume_actions  the VOLUME item
#   RoleSwitch    pick a role -> confirm -> write config.json -> restart. Pure logic: the caller draws and acts.
#   restart       the restart itself (marks "a person did this", then machine.reset())
import time

from helpers import config

LONG_MS = 1200


class Button:
    def __init__(self):
        import board
        from machine import Pin
        self.pin = Pin(board.BOOT, Pin.IN, Pin.PULL_UP)
        self._t = None

    def read(self, now):
        down = self.pin.value() == 0
        if down and self._t is None:
            self._t = now
        elif not down and self._t is not None:
            held = time.ticks_diff(now, self._t)
            self._t = None
            if held >= LONG_MS:
                return "long"
            if held >= 40:
                return "short"
        return None


    def held_for(self, window_ms, hold_ms):
        """Wait up to window_ms for the button to be held down for hold_ms (a press that began inside the window is
        followed to the end). True = it was held long enough. Blocking; used once at start-up."""
        t0 = time.ticks_ms()
        down_since = None
        while True:
            now = time.ticks_ms()
            if self.pin.value() == 0:
                if down_since is None:
                    down_since = now
                if time.ticks_diff(now, down_since) >= hold_ms:
                    return True
            else:
                down_since = None
                if time.ticks_diff(now, t0) >= window_ms:
                    return False
            time.sleep_ms(20)

    def wait_release(self, limit_ms=10000):
        """Wait until the button is up again (so the end of a long hold is not read as a press)."""
        t0 = time.ticks_ms()
        while self.pin.value() == 0 and time.ticks_diff(time.ticks_ms(), t0) < limit_ms:
            time.sleep_ms(20)
        self._t = None


def volume_actions(audio):
    """Menu actions that read and step the volume level (1..5) and remember it across reboots."""
    def step():
        n = audio.level % 5 + 1
        audio.set_level(n)
        config.state_save("volume_level", n)
        audio.beep(n=1)                      # a beep at the new level
        return n

    return {"get_level": lambda: audio.level, "volume_step": step}


class RoleSwitch:
    """state: "pick" (MASTER / SLAVE / PLAY / BACK) -> "confirm" -> "done" (restart now) or "failed".
    tap() and hold() return "redraw", "cancel" (leave the role menu) or "reset" (config.json written: restart)."""

    def __init__(self, current, save=None):
        self.current = current
        self.save = save or config.save_role
        self.state = "pick"
        self.idx = config.SWITCHABLE.index(current) if current in config.SWITCHABLE else 0
        self.target = None
        self.error = ""

    def labels(self):
        return [r.upper() for r in config.SWITCHABLE] + ["BACK"]

    def tap(self):
        if self.state == "pick":
            self.idx = (self.idx + 1) % (len(config.SWITCHABLE) + 1)
            return "redraw"
        if self.state == "confirm":              # tap = NO: back to the list
            self.state = "pick"
            self.target = None
            return "redraw"
        return "cancel"

    def hold(self):
        if self.state == "pick":
            if self.idx >= len(config.SWITCHABLE) or config.SWITCHABLE[self.idx] == self.current:
                return "cancel"                  # BACK, or the role it already has
            self.target = config.SWITCHABLE[self.idx]
            self.state = "confirm"
            return "redraw"
        if self.state == "confirm":              # hold = YES
            ok, msg = self.save(self.target)
            if ok:
                self.state = "done"
                return "reset"
            self.state = "failed"
            self.error = msg
            return "redraw"
        return "cancel"


def restart():
    """A person asked for this restart: mark it (the start-up screen shows), then reset. Never returns on a board."""
    try:
        from helpers import bootinfo
        bootinfo.mark_manual()
    except Exception:
        pass
    time.sleep_ms(600)                           # let the "restarting" screen be seen
    import machine
    machine.reset()
