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
    print("[boot] last run ended: %s; reset cause: %s; started by a person: %s; start-up screen: %s" % (
        bootinfo.NAMES.get(info["previous"], "?"), info["cause"], "yes" if info["manual"] else "no",
        "on" if show else "off"))
    i2c = board.i2c()
    shared = bootscr.open_screen(cfg, i2c)               # the ONE panel object, handed on to the HUD / play screen
    boot = bootscr.Boot(shared[0], shared[1], role, version.full(), show, u["brightness"])
    boot.step("CONFIG")

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
    log.write("boot", "role=%s,ver=%s,free_kb=%d,prev=%s,cause=%s,manual=%d" % (
        role, version.full(), free_kb, info["previous"], info["cause"], 1 if info["manual"] else 0))
    ready_ms = int(u["ready_s"] * 1000)

    if role == "play":
        from app import play
        from ui.playui import PlayUi
        boot.step("NETWORK", "-")                        # the play mode has no network
        ui = PlayUi(cfg, i2c, shared)
        _ready(boot, audio, cfg, info)
        if boot.shown:
            time.sleep_ms(ready_ms)                      # before the watchdog starts: a plain wait is fine here
        if cfg["auto_reboot"]:
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
        play.run(cfg, audio, ui=ui)
        return

    from ui.hud import Hud
    hud = Hud(cfg, role, i2c, shared)

    if role == "loopback":
        from net.link import LoopbackNet
        from app import master
        boot.step("NETWORK", "-")
        if cfg["auto_reboot"]:
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
        _ready(boot, audio, cfg, info)
        hud.hold_boot(ready_ms)
        master.run(cfg, audio, LoopbackNet(), hud)
    elif role in ("master", "slave"):
        from net.link import Net
        net = Net(cfg, role)
        net.start(wait=False)                            # the slave does not wait for the master: its screen and button work at once
        boot.step("NETWORK", "OK" if net.joined() else "SEARCHING")
        if cfg["auto_reboot"]:
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
        _ready(boot, audio, cfg, info)
        hud.hold_boot(ready_ms)
        if role == "master":
            from app import master
            master.run(cfg, audio, net, hud)
        else:
            from app import slave
            slave.run(cfg, audio, net, hud)
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
