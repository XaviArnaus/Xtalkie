# main.py -- runs at boot. Reads /config.json and starts the role of this board.
#
#   /main.py  /config.json  /README.md     <- the project
#   /lib/...                                 <- everything else (drivers, board, helpers, net, dsp, ui, app)
#   /tools/...                               <- diagnostics you run by hand from Thonny
#
# Start-up order: config, then the panel (opened once, shared with the HUD), then audio, network, ready.
# Every step is printed with its time and shown on the start-up screen (see ui/boot.py). The child unit stays
# dark after an automatic restart (see helpers/bootinfo.py).
import sys

if "/lib" in sys.path:
    sys.path.remove("/lib")
sys.path.insert(0, "/lib")          # our libraries first: an old file in / can never shadow them

import time

from helpers import config

# files of the first, flat layout: not used any more, and best deleted (tools/cleanup_old.py does it)
LEGACY = ("audio.py", "board.py", "config.py", "es8311.py", "gate2.py", "gfx.py", "log.py", "master.py",
          "net.py", "power.py", "proto.py", "screen.py", "slave.py", "ui.py", "watchdog.py",
          "disk.py", "ui_demo.py", "screen_probe.py", "battery_check.py", "record_raw.py")


def _warn_legacy():
    try:
        import os
        old = [f for f in os.listdir("/") if f in LEGACY]
        if old:
            print("[main] old files from the flat layout are still in /: %s" % ", ".join(old))
            print("[main] they are ignored; run tools/cleanup_old.py to delete them")
    except Exception:
        pass


def _ready(boot, audio, cfg, info):
    """Last start-up step; one short beep when a person switched the unit on (and the screen is lit)."""
    boot.step("READY")
    if boot.shown and info["manual"] and cfg["ui"]["boot_beep"]:
        try:
            audio.beep(n=1)
        except Exception as e:
            print("[boot] ready beep failed:", e)


def _after_chooser(boot, shared):
    """The chooser used the panel: bring back the start-up screen, or darkness if none was meant to be shown."""
    if boot.shown:
        boot.redraw()
    elif shared[0] is not None:
        try:
            shared[0].hide()
        except Exception:
            pass


def _finish_boot(boot, audio, cfg, info, role, shared):
    """READY step and beep, then a short wait for BOOT to be held (the role chooser). Nothing of the role has
    started yet, so the chooser is reachable whatever the role's code does. Returns True if it waited."""
    u = cfg["ui"]
    hold_s, window_s = u["chooser_hold_s"], u["chooser_window_s"]
    can = bool(boot.shown and window_s and shared[0] is not None)
    if can:
        boot.hint = "HOLD BUTTON %d S: CHOOSE ROLE" % hold_s
    _ready(boot, audio, cfg, info)
    if not can:
        return False
    from ui import chooser, menu
    btn = None
    try:
        btn = menu.Button()
        wanted = btn.held_for(int(window_s * 1000), int(hold_s * 1000))
    except Exception as e:
        print("[boot] button not available:", e)
        wanted = False
    if wanted:
        chooser.choose(shared[0], shared[1], u["brightness"], role, "hold", u["chooser_timeout_s"], btn=btn)
    boot.hint = None
    boot.redraw()
    return True


def main():
    cfg = config.load()
    role = cfg["role"]
    import version
    print("xtalkie %s: role '%s'" % (version.full(), role))
    if role == "idle":
        print("idle: nothing started (use this role to run the tools on a clean board)")
        return
    _warn_legacy()

    from helpers import bootinfo
    from ui import boot as bootscr
    import board
    u = cfg["ui"]
    info = bootinfo.begin()
    show = bootscr.should_show(u["boot_screen"], role, info["manual"])
    print("[boot] last run ended: %s; reset cause: %s; started by a person: %s; crashes in a row: %d; start-up screen: %s" % (
        bootinfo.NAMES.get(info["previous"], "?"), info["cause"], "yes" if info["manual"] else "no",
        info["crashes"], "on" if show else "off"))
    i2c = board.i2c()
    shared = bootscr.open_screen(cfg, i2c)               # the ONE panel object, handed on to the HUD / play screen
    boot = bootscr.Boot(shared[0], shared[1], role, version.full(), show, u["brightness"])
    boot.step("CONFIG")
    if u["crash_limit"] and info["crashes"] >= u["crash_limit"]:
        if role == "child":
            # the child unit NEVER lights the room by itself, not even in a crash loop: the parent unit's "no link"
            # alarm tells that something is wrong. A person power-cycles it (start-up screen + chooser).
            print("[boot] %d crashes in a row: child unit stays dark (power-cycle it to get the start-up screen)" % info["crashes"])
        else:
            # a crash loop: do not start the same role once more without asking (the chooser needs no role code)
            print("[boot] %d crashes in a row: role chooser instead of the same role" % info["crashes"])
            from ui import chooser
            chooser.choose(shared[0], shared[1], u["brightness"], role, "crash", u["chooser_timeout_s"])
            _after_chooser(boot, shared)

    try:
        import machine
        machine.freq(int(cfg["cpu_mhz"]) * 1000000)
        print("[cpu] %d MHz" % (machine.freq() // 1000000))
    except Exception as e:
        print("[cpu] frequency not changed:", e)

    from board.audio import Audio
    a = cfg["audio"]
    level = config.state_load().get("volume_level", a["volume_level"])
    audio = Audio(mic_gain=a["mic_gain"], volume=a["volume"], playback_gain=a["playback_gain"],
                  agc=a["agc"], agc_max_gain=a["agc_max_gain"], level=level)
    audio.start()
    boot.step("AUDIO")

    from helpers import log
    log.enabled = cfg["log"]
    import os
    try:
        st = os.statvfs("/")
        free_kb = st[0] * st[3] // 1024
        total_kb = st[0] * st[2] // 1024
        print("[disk] %d KB free of %d KB" % (free_kb, total_kb))
    except Exception:
        free_kb = -1
    log.write("boot", "role=%s,ver=%s,free_kb=%d,prev=%s,cause=%s,manual=%d,crashes=%d" % (
        role, version.full(), free_kb, info["previous"], info["cause"], 1 if info["manual"] else 0, info["crashes"]))
    ready_ms = int(u["ready_s"] * 1000)

    if role == "play":
        from app import play
        from ui.playui import PlayUi
        boot.step("NETWORK", "-")                        # the play mode has no network
        ui = PlayUi(cfg, i2c, shared)
        waited = _finish_boot(boot, audio, cfg, info, role, shared)
        if boot.shown and not waited:
            time.sleep_ms(ready_ms)                      # before the watchdog starts: a plain wait is fine here
        if cfg["auto_reboot"]:
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
        play.run(cfg, audio, ui=ui)
        return

    from ui.hud import Hud
    hud = Hud(cfg, role, i2c, shared)
    hud.set_boot_note(bootinfo.summary(info))            # a tap on the child unit shows how it started

    if role == "loopback":
        from net.link import LoopbackNet
        from app import child
        boot.step("NETWORK", "-")
        _finish_boot(boot, audio, cfg, info, role, shared)
        if cfg["auto_reboot"]:
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
        hud.hold_boot(ready_ms)
        child.run(cfg, audio, LoopbackNet(), hud)
    elif role in ("child", "parent"):
        from net.link import Net
        net = Net(cfg, role)
        net.start(wait=False)                            # the parent does not wait for the child: its screen and button work at once
        boot.step("NETWORK", "OK" if net.joined() else "SEARCHING")
        _finish_boot(boot, audio, cfg, info, role, shared)
        if cfg["auto_reboot"]:                           # started after the chooser window: the chooser may wait for minutes
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
        hud.hold_boot(ready_ms)
        if role == "child":
            from app import child
            child.run(cfg, audio, net, hud)
        else:
            from app import parent
            parent.run(cfg, audio, net, hud)
    else:
        print("unknown role: %s" % role)


try:
    main()
except KeyboardInterrupt:
    print("stopped")
    try:
        from helpers import bootinfo
        bootinfo.mark_clean()                            # stopped on purpose: the next start is not a crash restart
    except Exception:
        pass
except Exception as e:
    sys.print_exception(e)
    try:
        if config.load()["auto_reboot"]:
            from helpers import bootinfo
            bootinfo.mark_auto()                         # tells the next start "this was automatic" (child unit: stay dark)
            print("restarting in 5 s")
            time.sleep(5)
            import machine
            machine.reset()
    except Exception:
        pass
