# ui/hud.py -- the "HUD": battery, one button (BOOT), and what the screen shows. Never lets the screen
# break the monitor: any display error switches the screen off for good, the audio keeps running.
#
# Screen policy (the panel is dark unless one of these is active):
#   STATUS    BOOT tap: link icon + battery of this unit and of the other one, for status_s seconds
#   ALARM     (parent unit) voice / alert audio is playing: full-screen flashing bell, until dismissed
#   LINKLOST  (parent unit) no signal from the child unit: flashing cross; BOOT acknowledges: the beeps stop until the link changes
#   MENU      BOOT long press (parent unit): TEST LIVE / TEST ALARM / EXIT; tap = next, hold = select
#   TEST      live test: the child unit streams its microphone for test_s seconds, level bar + packet count
import time

import board
import version
from drivers.axp2101 import AXP2101
from ui import menu

OFF, STATUS, ALARM, LINKLOST, MENU, TEST, PREVIEW, BOOT, ROLE, NOTE = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
MUTE_TAPS = 3                                     # this many quick BOOT taps on the parent unit switch its sound off / on
NOTE_MS = 3000
MENU_ITEMS = ("TEST LIVE", "TEST ALARM", "VOLUME", "MIC", "ROLE", "EXIT")
LONG_MS = menu.LONG_MS
BATT_REFRESH_MS = 30000
volume_actions = menu.volume_actions          # moved to ui/menu.py (shared with the play mode); kept importable from here


class Hud:
    def __init__(self, cfg, role, i2c, shared=None):
        """shared = (display, gfx) already opened by main.py (either may be None: screen off). Without it the
        HUD opens the panel itself."""
        u = cfg["ui"]
        self.u = u
        self.role = role
        self.is_parent = role != "child"            # loopback behaves like the parent unit
        self.bat = AXP2101(i2c)
        self._binfo = None
        self._btime = 0
        self.display = None
        self.gfx = None
        self.last_draw_ms = 0
        self.state = OFF
        self._until = 0
        self._phase = 0
        self._phase_t = 0
        self.link_ok = False
        self.peer = (None, False)                    # battery of the other unit
        self.version = version.full()
        self.peer_version = None                     # software version of the other unit, once known
        self.peer_restart = None                     # the child unit's restart code (parent unit only): n > 0 = it restarted by itself
        self.boot_note = None                        # how THIS unit started (shown on the child unit's status screen)
        self.alert_active = False
        self._dismissed = False
        self._hold_until = 0
        self.sound_off = False                       # parent unit: voice and beeps switched off by 3 quick taps (remembered)
        self._tap_n = 0
        self._tap_t = 0
        self._note = None                            # (title, detail, colour) of the NOTE screen
        if self.is_parent:
            try:
                from helpers import config as _cfg
                self.sound_off = bool(_cfg.state_load().get("sound_off", False))
            except Exception:
                pass
        self.acked = False                           # a person pressed BOOT while the link is down: no more beeps until the link changes
        self.idx = 0
        self.switch = None                           # the role switch in progress (ui/menu.py RoleSwitch)
        self.test = None
        self.actions = {}
        self._press_t = None
        self._test_draw_t = 0
        from machine import Pin
        self.btn = Pin(board.BOOT, Pin.IN, Pin.PULL_UP)
        if shared is not None:
            self.display, self.gfx = shared
        else:
            from ui.boot import open_screen
            self.display, self.gfx = open_screen(cfg, i2c)

    # ------------------------------------------------------------ helpers
    def hold_boot(self, ms):
        """The start-up screen is on the panel (drawn by ui/boot.py): leave it there for ms, then show the status
        screen (parent unit) or go dark (child unit). A button press or an alarm ends it earlier. Does nothing
        when nothing was drawn (child unit after an automatic restart)."""
        if self.display is None or not self.display.on:
            return
        self.state = BOOT
        self._until = time.ticks_add(time.ticks_ms(), ms)

    def set_actions(self, **kw):
        self.actions.update(kw)

    def _fail(self, e):
        print("[ui] error, screen disabled:", e)
        try:
            self.display.hide()
        except Exception:
            pass
        self.display = None

    def battery_info(self, now=None):
        """(percent or None, charging) of this unit, refreshed at most every 30 s."""
        try:
            now = time.ticks_ms() if now is None else now
            if self._binfo is None or time.ticks_diff(now, self._btime) > BATT_REFRESH_MS:
                self._binfo = self.bat.read()
                self._btime = now
            return self._binfo[0], self._binfo[1]
        except Exception:
            return None, False

    def muted(self, now):
        """No beeps for the no-link alarm: it was acknowledged (until the link changes) or the sound is switched off."""
        return self.acked or self.sound_off

    def sound_muted(self):
        """The parent unit's sound (voice and beeps) is switched off by the person (3 quick taps)."""
        return self.sound_off

    def alert_dismissed(self):
        """A person pressed BOOT on the bell screen of the alert that is still playing: stop its voice."""
        return self.alert_active and self._dismissed

    def _toggle_sound(self, now):
        self.sound_off = not self.sound_off
        try:
            from helpers import config as _cfg
            _cfg.state_save("sound_off", self.sound_off)
        except Exception:
            pass
        if self.sound_off:
            self._note = ("SOUND OFF", "3 TAPS: SOUND ON", self._amber())
        else:
            self._note = ("SOUND ON", "", self._green())
        print("[ui] sound %s" % ("OFF (muted by hand)" if self.sound_off else "ON"))
        self._go(NOTE, now, NOTE_MS)
        if not self.sound_off:
            fn = self.actions.get("unmute_beep")
            if fn:
                fn()                                 # one beep: the speaker works again

    @staticmethod
    def _amber():
        from ui import screens as S
        return S.AMBER

    @staticmethod
    def _green():
        from ui import screens as S
        return S.GREEN

    def silence_requested(self):
        """Called by the parent's beep loop between tones: BOOT held down while the link is down = acknowledge now,
        so a press made during the (blocking) beeps is not lost. True = stop beeping."""
        try:
            if self.is_parent and not self.link_ok and self.btn.value() == 0:
                self.acked = True
                return True
        except Exception:
            pass
        return False

    def _expired(self, now, t):
        return time.ticks_diff(now, t) >= 0

    # ------------------------------------------------------------ events from the roles
    def on_link(self, up):
        try:
            if up == self.link_ok:
                return
            was = self.link_ok
            self.link_ok = up
            now = time.ticks_ms()
            self.acked = False                       # every change of the link starts a new alarm cycle
            if up:
                if self.state in (LINKLOST, OFF) and self.is_parent:
                    self._go(STATUS, now, self.u["status_s"] * 1000)
            elif self.is_parent and was:
                self._go(LINKLOST, now, None)
        except Exception as e:
            self._fail(e)

    def on_peer_status(self, pct, charging):
        self.peer = (pct, charging)

    def _redraw_status_if_shown(self):
        try:
            if self.state == STATUS and self.display is not None:
                self._draw(time.ticks_ms())
        except Exception as e:
            self._fail(e)

    def on_peer_version(self, v):
        """Software version of the other unit (None = it does not report one, i.e. older code)."""
        changed = v != self.peer_version
        self.peer_version = v
        if changed:
            self._redraw_status_if_shown()          # the status screen may already be up (it opens when the link does)

    def on_peer_restart(self, code):
        """The child unit's restart code from its heartbeat (None = older unit that does not report one)."""
        changed = code != self.peer_restart
        self.peer_restart = code
        if changed:
            self._redraw_status_if_shown()

    def set_boot_note(self, text):
        self.boot_note = text

    def version_warning(self):
        """The other unit's version when it differs from ours (shown in amber on the status screen), else None."""
        v = self.peer_version
        return v if (v is not None and v != self.version) else None

    def on_alert_start(self):
        try:
            self.alert_active = True
            self._dismissed = False
            if self.is_parent:
                self._go(ALARM, time.ticks_ms(), None)
        except Exception as e:
            self._fail(e)

    def on_alert_end(self):
        try:
            self.alert_active = False
            self._hold_until = time.ticks_add(time.ticks_ms(), self.u["alert_hold_s"] * 1000)
        except Exception as e:
            self._fail(e)

    def on_test_audio(self, level_db):
        t = self.test
        if t is not None and t["result"] is None:
            t["pkts"] += 1
            t["level"] = max(level_db, t["level"] - 2)

    def on_test_end(self):
        if self.test is not None:
            self.test["ended"] = True

    # ------------------------------------------------------------ state machine
    def _go(self, state, now, hold_ms):
        self.state = state
        self._phase = 0
        self._phase_t = now
        if hold_ms is not None:
            self._until = time.ticks_add(now, hold_ms)
        self._draw(now)

    def _present(self, draw, brightness):
        """Draw a screen (the panel is still dark if it was off), then show it at this brightness."""
        t0 = time.ticks_ms()
        draw(self.gfx)
        self.display.show(brightness)
        self.last_draw_ms = time.ticks_diff(time.ticks_ms(), t0)

    def _draw(self, now):
        if self.display is None:
            return
        from ui import screens as S
        u = self.u
        s = self.state
        if s == OFF:
            self.display.hide()
        elif s == STATUS:
            me = self.battery_info(now)
            title = "PARENT UNIT" if self.is_parent else "CHILD ROOM"
            other = "CHILD" if self.is_parent else "PARENT"
            hint = "HOLD BUTTON: MENU" if self.is_parent else ""
            ver, warn = self.version, self.version_warning()
            restart = self.peer_restart if self.is_parent else None
            note = None if self.is_parent else self.boot_note
            off = self.sound_off and self.is_parent
            self._present(lambda g: S.draw_status(g, title, self.link_ok, me, self.peer, other, hint, ver, warn, restart, note, off),
                          u["brightness"])
        elif s == NOTE:
            t, d, c = self._note or ("", "", None)
            self._present(lambda g: S.draw_message(g, t, d, c), u["brightness"])
        elif s in (ALARM, PREVIEW):
            ph = self._phase
            self._present(lambda g: S.draw_alarm(g, ph), u["alarm_brightness"])
        elif s == LINKLOST:
            ph = self._phase
            self._present(lambda g: S.draw_linklost(g, ph), u["alarm_brightness"])
        elif s == MENU:
            idx = self.idx
            gl = self.actions.get("get_level")
            gs = self.actions.get("get_sens")
            labels = []
            for n in MENU_ITEMS:
                if n == "VOLUME" and gl:
                    n = "VOLUME %d" % gl()
                elif n == "MIC" and gs:
                    n = "MIC %d" % gs()
                labels.append(n)
            self._present(lambda g: S.draw_menu(g, labels, idx), u["brightness"])
        elif s == TEST:
            t = self.test or {"deadline": now, "pkts": 0, "level": -99.0, "result": None}
            rem = max(0, time.ticks_diff(t["deadline"], now) // 1000)
            self._present(lambda g: S.draw_test(g, rem, t["pkts"], t["level"], t["result"]), u["brightness"])
        elif s == ROLE:
            sw = self.switch
            if sw.state == "pick":
                labels, idx = sw.labels(), sw.idx
                self._present(lambda g: S.draw_menu(g, labels, idx, "ROLE"), u["brightness"])
            elif sw.state == "confirm":
                target = sw.target
                self._present(lambda g: S.draw_confirm(g, target), u["brightness"])
            elif sw.state == "done":
                self._present(lambda g: S.draw_message(g, "RESTARTING", "", S.GREEN), u["brightness"])
            else:
                err = sw.error
                self._present(lambda g: S.draw_message(g, "NOT SAVED", err, S.AMBER), u["brightness"])

    def _button(self, now):
        down = self.btn.value() == 0
        if down and self._press_t is None:
            self._press_t = now
        elif not down and self._press_t is not None:
            held = time.ticks_diff(now, self._press_t)
            self._press_t = None
            if held >= LONG_MS:
                return "long"
            if held >= 40:
                return "short"
        return None

    def _on_button(self, ev, now):
        s = self.state
        u = self.u
        if self.is_parent and not self.link_ok:
            self.acked = True                        # any press while the link is down silences the beeps (the screen does what it always did)
        if self.is_parent and s not in (MENU, TEST, ROLE) and ev == "short":
            if self._tap_n and time.ticks_diff(now, self._tap_t) <= u["mute_gap_ms"]:
                self._tap_n += 1
            else:
                self._tap_n = 1
            self._tap_t = now
            if self._tap_n >= MUTE_TAPS:             # 3 quick taps: sound off / on (voice and beeps)
                self._tap_n = 0
                self._toggle_sound(now)
                return
        else:
            self._tap_n = 0
        if s == OFF or s == BOOT or s == NOTE:
            if ev == "long" and self.is_parent:
                self.idx = 0
                self._go(MENU, now, 20000)
            else:
                self._go(STATUS, now, u["status_s"] * 1000)
        elif s == STATUS:
            if ev == "long" and self.is_parent:
                self.idx = 0
                self._go(MENU, now, 20000)
            elif ev == "long":
                self._go(OFF, now, None)
            else:
                self._until = time.ticks_add(now, u["status_s"] * 1000)    # restart the timer without redrawing: a draw takes
                                                                           # ~200 ms during which BOOT is not read (missed taps)
        elif s == ALARM:
            self._dismissed = True
            self._go(OFF, now, None)
        elif s == LINKLOST:
            self._go(OFF, now, None)
        elif s == MENU:
            if ev == "short":
                self.idx = (self.idx + 1) % len(MENU_ITEMS)
                self._go(MENU, now, 20000)
            else:
                self._select(now)
        elif s == TEST:
            self.test = None
            self._go(MENU, now, 20000)
        elif s == PREVIEW:
            self._go(OFF, now, None)
        elif s == ROLE:
            self._role_result(self.switch.tap() if ev == "short" else self.switch.hold(), now)

    def _role_result(self, res, now):
        """What the role switch asked for: redraw, back to the menu, or restart (config.json is already written)."""
        sw = self.switch
        if res == "cancel":
            self.switch = None
            self._go(MENU, now, 20000)
        elif res == "reset":
            from helpers import log
            log.write("ui", "role switch %s -> %s" % (self.role, sw.target))
            print("[ui] role %s -> %s: restarting" % (self.role, sw.target))
            self._go(ROLE, now, None)               # shows RESTARTING
            menu.restart()
        else:
            self._go(ROLE, now, 4000 if sw.state == "failed" else 20000)

    def _select(self, now):
        item = MENU_ITEMS[self.idx]
        if item == "TEST LIVE":
            fn = self.actions.get("test_live")
            ok = bool(fn and fn(self.u["test_s"]))
            self.test = {"deadline": time.ticks_add(now, self.u["test_s"] * 1000), "pkts": 0,
                         "level": -99.0, "result": None if ok else False, "ended": False}
            self._go(TEST, now, 6000 if not ok else None)
        elif item == "MIC":
            fn = self.actions.get("sens_step")
            if fn:
                fn()
            self._go(MENU, now, 20000)
        elif item == "VOLUME":
            fn = self.actions.get("volume_step")
            if fn:
                fn()
            self._go(MENU, now, 20000)
        elif item == "TEST ALARM":
            self._go(PREVIEW, now, 4000)
            fn = self.actions.get("alarm_preview")
            if fn:
                fn()
        elif item == "ROLE":
            self.switch = menu.RoleSwitch(self.role)
            self._go(ROLE, now, 20000)
        else:
            self._go(OFF, now, None)

    def tick(self, now):
        """Call once per loop (cheap when nothing changes)."""
        try:
            ev = self._button(now)
            if ev and (self.display is not None):
                self._on_button(ev, now)
            elif ev and self.is_parent and not self.link_ok:
                self.acked = True
            if self.display is None:
                return
            s = self.state
            if s == OFF:
                return
            if s == BOOT:
                if self._expired(now, self._until):
                    if self.is_parent:
                        self._go(STATUS, now, self.u["status_s"] * 1000)
                    else:
                        self._go(OFF, now, None)
            elif s == STATUS:
                if self._expired(now, self._until):
                    self._go(OFF, now, None)
                elif time.ticks_diff(now, self._btime) > BATT_REFRESH_MS - 1000:
                    self._draw(now)
            elif s in (ALARM, LINKLOST):
                if self.u["flash_ms"] and time.ticks_diff(now, self._phase_t) >= self.u["flash_ms"]:
                    self._phase ^= 1
                    self._phase_t = now
                    self._draw(now)
                if s == ALARM and not self.alert_active and self._expired(now, self._hold_until):
                    self._go(OFF, now, None)
            elif s == MENU:
                if self._expired(now, self._until):
                    self._go(OFF, now, None)
            elif s == PREVIEW or s == NOTE:
                if self._expired(now, self._until):
                    self._go(OFF, now, None)
            elif s == ROLE:
                if self._expired(now, self._until):
                    failed = self.switch is not None and self.switch.state == "failed"
                    self.switch = None
                    self._go(MENU if failed else OFF, now, 20000 if failed else None)
            elif s == TEST:
                t = self.test
                if t is None:
                    return
                if t["result"] is None:
                    done = t["ended"] or time.ticks_diff(now, t["deadline"]) > 3000
                    if done:
                        need = self.u["test_s"] * 50 * 0.5
                        t["result"] = t["pkts"] >= need
                        self._go(TEST, now, 8000)
                    elif time.ticks_diff(now, self._test_draw_t) >= 250:
                        self._test_draw_t = now
                        self._draw(now)
                elif self._expired(now, self._until):
                    self.test = None
                    self._go(MENU, now, 20000)
        except Exception as e:
            self._fail(e)


class NullHud:
    """Same interface as Hud, does nothing (used when a role is run without a HUD)."""
    link_ok = False

    def set_actions(self, **kw):
        pass

    def battery_info(self, now=None):
        return None, False

    def muted(self, now):
        return False

    def silence_requested(self):
        return False

    def sound_muted(self):
        return False

    def alert_dismissed(self):
        return False

    def on_link(self, up):
        pass

    def on_peer_status(self, pct, charging):
        pass

    def on_peer_version(self, v):
        pass

    def on_peer_restart(self, code):
        pass

    def set_boot_note(self, text):
        pass

    def hold_boot(self, ms):
        pass

    def on_alert_start(self):
        pass

    def on_alert_end(self):
        pass

    def on_test_audio(self, level_db):
        pass

    def on_test_end(self):
        pass

    def tick(self, now):
        pass
