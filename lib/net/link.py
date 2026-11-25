# net/link.py -- WiFi (access point or station) and a non-blocking UDP socket.
import socket
import time


class Net:
    def __init__(self, cfg, role):
        w = cfg["wifi"]
        self.ssid = w["ssid"]
        self.password = w["password"]
        self.channel = w["channel"]
        self.power_save = w.get("power_save", "none")
        self.port = cfg["port"]
        mode = w["mode"]
        if mode == "auto":
            mode = "ap" if role == "master" else "sta"
        self.mode = mode
        self.master_addr = (w["master_ip"], self.port)    # where the slave sends its HELLO
        self.wlan = None
        self.sock = None
        self._last_try = 0

    def start(self, wifi=True):
        if wifi:
            import network
            if self.mode == "ap":
                self.wlan = network.WLAN(network.AP_IF)
                self.wlan.active(True)
                self.wlan.config(essid=self.ssid, password=self.password,
                                 authmode=network.AUTH_WPA2_PSK, channel=self.channel)
                print("[net] access point '%s' up, ip %s" % (self.ssid, self.wlan.ifconfig()[0]))
            else:
                self.wlan = network.WLAN(network.STA_IF)
                self.wlan.active(True)
                self.wlan.connect(self.ssid, self.password)
                t0 = time.ticks_ms()
                while not self.wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 15000:
                    time.sleep_ms(250)
                if self.wlan.isconnected():
                    print("[net] joined '%s', ip %s" % (self.ssid, self.wlan.ifconfig()[0]))
                else:
                    print("[net] '%s' not found yet, will keep trying" % self.ssid)
            pm = network.WLAN.PM_NONE                          # no power saving: lowest latency
            if self.mode == "sta":                             # an access point can not sleep, a station can
                pm = {"min": network.WLAN.PM_PERFORMANCE, "max": network.WLAN.PM_POWERSAVE}.get(self.power_save, pm)
            try:
                self.wlan.config(pm=pm)
            except Exception:
                pass
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.setblocking(False)

    def ensure(self):
        """Station mode: reconnect if the link dropped (at most every 5 s)."""
        if self.mode != "sta" or self.wlan is None:
            return
        if self.wlan.isconnected():
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_try) > 5000:
            self._last_try = now
            try:
                self.wlan.connect(self.ssid, self.password)
            except OSError:
                pass

    def send(self, data, addr):
        try:
            self.sock.sendto(data, addr)
            return True
        except OSError:
            return False

    def recv(self):
        try:
            return self.sock.recvfrom(1500)
        except OSError:
            return None


class LoopbackNet:
    """Stand-in for Net on a single board: packets are collected locally instead of sent."""
    peer = ("loopback", 0)
    master_addr = peer

    def __init__(self):
        self.packets = []

    def start(self, wifi=True):
        pass

    def ensure(self):
        pass

    def send(self, data, addr):
        self.packets.append(data)
        return True

    def recv(self):
        return None

    def take(self):
        p = self.packets
        self.packets = []
        return p
