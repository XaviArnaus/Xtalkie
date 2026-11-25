# helpers/watchdog.py -- optional hardware watchdog for unattended use (started by main.py when auto_reboot is on).
# If a loop stops calling feed() for the configured time, the board resets and main.py starts again.
_wdt = None


def start(ms):
    global _wdt
    from machine import WDT
    _wdt = WDT(timeout=ms)


def feed():
    if _wdt is not None:
        _wdt.feed()
