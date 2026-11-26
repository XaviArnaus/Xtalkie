# main.py -- runs at boot. Reads /config.json and starts the role of this board.
#
#   /main.py  /config.json  /README.md     <- the project
#   /lib/...                                 <- everything else (drivers, board, helpers, net, dsp, ui, app)
#   /tools/...                               <- diagnostics you run by hand from Thonny
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


def main():
    cfg = config.load()
    role = cfg["role"]
    print("xtalkie: role '%s'" % role)
    if role == "idle":
        print("idle: nothing started (use this role to run the tools on a clean board)")
        return
    _warn_legacy()
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
    log.write("boot", "role=%s,free_kb=%d" % (role, free_kb))

    if role == "play":
        from app import play
        if cfg["auto_reboot"]:
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
        play.run(cfg, audio)
        return

    import board
    from ui.hud import Hud
    hud = Hud(cfg, role, board.i2c())

    if role == "loopback":
        from net.link import LoopbackNet
        from app import master
        if cfg["auto_reboot"]:
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
        master.run(cfg, audio, LoopbackNet(), hud)
    elif role in ("master", "slave"):
        from net.link import Net
        net = Net(cfg, role)
        net.start()
        if cfg["auto_reboot"]:
            from helpers import watchdog
            watchdog.start(cfg["watchdog_ms"])
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
except Exception as e:
    sys.print_exception(e)
    try:
        if config.load()["auto_reboot"]:
            print("restarting in 5 s")
            time.sleep(5)
            import machine
            machine.reset()
    except Exception:
        pass
