# ui/chooser.py -- the boot chooser: pick this unit's role at start-up, before any role code runs.
#
# Reached two ways (see main.py):
#   - hold BOOT for about 2 s while the start-up screen shows "HOLD BUTTON 2 S: CHOOSE ROLE"
#   - after the unit crashed several times in a row (crash loop): the chooser appears instead of restarting the
#     same role once more, even on the child unit (a unit that keeps crashing is not watching the child anyway)
# It is the same list as the ROLE menu: MASTER / SLAVE / PLAY / BACK, then a confirmation (hold = yes, tap = no).
# Choosing the role the unit already has, BACK, or doing nothing for `timeout_s` returns, and the start goes on with
# the role in config.json. A changed role is written to config.json and the unit restarts.
import time

from helpers import config
from ui import menu
from ui import screens as S


def choose(display, gfx, brightness, current, why="hold", timeout_s=120, feed=None, btn=None):
    """Blocking. Returns True if the unit should go on starting (role unchanged); a role change restarts the
    board and does not return on a real unit. Returns False only when there is no screen or button to use."""
    if display is None:
        return True                              # nothing to choose with: carry on
    try:
        btn = btn or menu.Button()
    except Exception as e:
        print("[chooser] no button:", e)
        return True
    title = "CRASHES" if why == "crash" else "ROLE"
    print("[chooser] role chooser (%s), current role '%s'" % (why, current))
    btn.wait_release()
    sw = menu.RoleSwitch(current)

    def show(draw):
        try:
            draw(gfx)
            display.show(brightness)
        except Exception as e:
            print("[chooser] screen error:", e)

    def redraw(now):
        if sw.state == "pick":
            labels, i = sw.labels(), sw.idx
            show(lambda g: S.draw_menu(g, labels, i, title))
        elif sw.state == "confirm":
            target = sw.target
            show(lambda g: S.draw_confirm(g, target))
        elif sw.state == "done":
            show(lambda g: S.draw_message(g, "RESTARTING", "", S.GREEN))
        else:
            err = sw.error
            show(lambda g: S.draw_message(g, "NOT SAVED", err, S.AMBER))
        return time.ticks_add(now, 4000 if sw.state == "failed" else timeout_s * 1000)

    until = redraw(time.ticks_ms())
    while True:
        if feed:
            feed()
        now = time.ticks_ms()
        ev = btn.read(now)
        if ev:
            res = sw.tap() if ev == "short" else sw.hold()
            if res == "cancel":
                return True
            if res == "reset":
                print("[chooser] role %s -> %s: restarting" % (current, sw.target))
                try:
                    from helpers import log
                    log.write("chooser", "role switch %s -> %s" % (current, sw.target))
                except Exception:
                    pass
                redraw(now)
                menu.restart()
                return False
            until = redraw(now)
        elif time.ticks_diff(now, until) >= 0:
            if sw.state == "failed":
                sw.state = "pick"
                until = redraw(now)
            else:
                print("[chooser] nobody answered: starting as '%s'" % current)
                return True
        time.sleep_ms(20)
