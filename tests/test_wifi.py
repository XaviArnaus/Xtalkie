"""WiFi start-up: a dirty driver state (after a soft reboot) must not crash the app; power-save mapping."""
import sys
import types

from common import check, finish, patch_time

patch_time()
log = []


class WLAN:
    PM_NONE, PM_PERFORMANCE, PM_POWERSAVE = 0, 1, 2
    fail = {"active": 0, "connect": 0, "config": 0}         # how many calls fail with the real error text

    def __init__(self, i):
        self.i, self.up, self.connected = i, False, False

    def active(self, on):
        log.append(("active", self.i, on))
        if on and WLAN.fail["active"] > 0:
            WLAN.fail["active"] -= 1
            raise OSError("Wifi Internal State Error")
        self.up = on

    def connect(self, ssid, pw):
        log.append(("connect", self.i))
        if WLAN.fail["connect"] > 0:
            WLAN.fail["connect"] -= 1
            raise OSError("Wifi Internal State Error")
        self.connected = True

    def disconnect(self): log.append(("disconnect", self.i)); self.connected = False
    def isconnected(self): return self.connected
    def ifconfig(self): return ("192.168.4.7",)

    def config(self, **k):
        log.append(("config", self.i, tuple(sorted(k))))
        if "essid" in k and WLAN.fail["config"] > 0:
            WLAN.fail["config"] -= 1
            raise OSError("Wifi Internal State Error")


net = types.ModuleType("network")
net.WLAN, net.AP_IF, net.STA_IF, net.AUTH_WPA2_PSK = WLAN, 1, 0, 3
sys.modules["network"] = net

from helpers import config
from net.link import Net


_open = []


def start(role, ps="none", **fail):
    while _open:
        _open.pop().sock.close()                          # one UDP port per run, like on the board
    log.clear()
    WLAN.fail.update(active=0, connect=0, config=0)
    WLAN.fail.update(fail)
    c = config.load("/nonexistent")
    c["wifi"]["power_save"] = ps
    n = Net(c, role)
    n.start()
    _open.append(n)
    return n


n = start("slave")
check(log[0] == ("active", 0, False), "the station is switched off first, whatever state the last run left")
n = start("slave", connect=2)
check(n.wlan.connected and sum(1 for l in log if l[0] == "connect") == 3, "a refused connect is retried (3 tries, then connected)")
n = start("slave", connect=9)
check(not n.wlan.connected and n.sock is not None, "if the driver keeps refusing, start() still returns; ensure() keeps trying")
n.wlan.connected = False
n._last_try = -10000
n.ensure()
check(any(l[0] == "connect" for l in log[-4:]), "ensure() reconnects later")
n = start("slave", active=2)
check(n.wlan.up and n.wlan.connected, "the interface is restarted when 'Wifi Internal State Error' hits active(True)")
n = start("master", config=1)
check(n.mode == "ap" and sum(1 for l in log if l[0] == "config" and "essid" in l[2]) == 2, "the access point setup is retried once")
for role, ps, want in (("master", "max", 0), ("slave", "none", 0), ("slave", "min", 1), ("slave", "max", 2)):
    start(role, ps)
    got = [l for l in log if l[0] == "config" and l[2] == ("pm",)]
    check(len(got) == 1, "%s / power_save %s -> pm applied once" % (role, ps))
finish()
