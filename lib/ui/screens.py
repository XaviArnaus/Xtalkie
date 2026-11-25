# ui/screens.py -- the screens of the monitor, drawn with ui/gfx.py on a 368 x 448 panel.
from ui.gfx import BLACK, WHITE, RED, GREEN, AMBER, ORANGE, GRAY, DGRAY


def draw_status(g, title, link_ok, me, other, other_name, hint):
    g.clear(BLACK)
    g.text_c(title, 18, 4, GRAY)
    g.circle(184, 130, 62, GREEN if link_ok else RED)
    if link_ok:
        g.check(184, 130, 62, WHITE)
    else:
        g.cross(184, 130, 62, WHITE)
    g.text_c("CONNECTED" if link_ok else "NO LINK", 215, 4, GREEN if link_ok else RED)
    g.rect(20, 262, 328, 2, DGRAY)
    for i, (name, info) in enumerate((("ME", me), (other_name, other))):
        y = 290 + i * 72
        pct, charging = info
        g.text(name, 20, y + 18, 3, WHITE)
        g.battery(140, y, 110, 54, pct, charging)
        if pct is None:
            g.text("USB" if charging else "--", 270, y + 13, 4, AMBER if charging else GRAY)
        else:
            g.text("%d%%" % pct, 270, y + 13, 4, WHITE)
    if hint:
        g.text_c(hint, 424, 2, GRAY)


def draw_alarm(g, phase):
    g.clear(RED if phase == 0 else BLACK)
    c = WHITE if phase == 0 else ORANGE
    g.bell(184, 185, 190, c)
    g.text_c("ALERT", 335, 8, c)
    g.text_c("BUTTON: DISMISS", 420, 2, WHITE if phase == 0 else GRAY)


def draw_linklost(g, phase):
    g.clear(RED if phase == 0 else BLACK)
    c = WHITE if phase == 0 else ORANGE
    g.cross(184, 165, 190, c)
    g.text_c("NO LINK", 320, 8, c)
    g.text_c("BUTTON: MUTE", 420, 2, WHITE if phase == 0 else GRAY)


def draw_menu(g, items, idx):
    g.clear(BLACK)
    g.text_c("MENU", 16, 5, GRAY)
    for i, name in enumerate(items):
        y = 70 + i * 72
        sel = i == idx
        g.rect(24, y, 320, 62, WHITE if sel else DGRAY)
        g.text_c(name, y + 17, 4, BLACK if sel else WHITE)
    g.text_c("TAP:NEXT HOLD:OK", 432, 2, GRAY)


def draw_test(g, remaining, pkts, level_db, result):
    g.clear(BLACK)
    g.text_c("LIVE TEST", 24, 5, GRAY)
    if result is None:
        g.text_c("LISTENING", 110, 5, WHITE)
        g.text_c("%d S" % remaining, 175, 7, AMBER)
        frac = max(0.0, min(1.0, (level_db + 80) / 50.0))
        g.rect(24, 290, 320, 50, WHITE)
        g.rect(28, 294, 312, 42, BLACK)
        g.rect(28, 294, int(312 * frac), 42, GREEN if frac < 0.75 else AMBER)
        g.text_c("PKT %d" % pkts, 362, 4, GRAY)
        g.text_c("TALK NEAR THE CHILD UNIT", 420, 2, GRAY)
    else:
        ok = result
        g.circle(184, 190, 70, GREEN if ok else RED)
        if ok:
            g.check(184, 190, 70, WHITE)
        else:
            g.cross(184, 190, 70, WHITE)
        g.text_c("AUDIO OK" if ok else "NO AUDIO", 300, 6, GREEN if ok else RED)
        g.text_c("PKT %d" % pkts, 370, 4, GRAY)
