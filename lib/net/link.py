# net/link.py -- WiFi (access point or station) and a non-blocking UDP socket.
import socket
import time

RECOVER_MS = 20000          # station: this long without hearing the other unit -> restart the WiFi interface
RECOVER_EVERY_MS = 30000    # ... and not more often than this


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
            mode = "ap" if role == "child" else "sta"
        self.mode = mode
        self.child_addr = (w["child_ip"], self.port)    # where the parent sends its HELLO
        self.wlan = None
        self.sock = None
        self._last_try = 0
        self._joined = False
        self._down_since = None                 # since when the application hears nothing from the other unit
        self._last_reset = time.ticks_add(time.ticks_ms(), -RECOVER_EVERY_MS)

    def _up(self, network, iface):
        """Bring an interface up from a clean state. After a soft reboot (Thonny's Run / Ctrl+D) the previous
        run may have left the WiFi driver connecting; starting on top of that gives 'Wifi Internal State Error'."""
        w = network.WLAN(iface)
        try:
            w.active(False)
        except OSError:
            pass
        time.sleep_ms(300)
        for attempt in range(3):
            try:
                w.active(True)
                return w
            except OSError as e:
                print("[net] wifi did not start (%s), retrying" % e)
                try:
                    w.active(False)
                except OSError:
                    pass
                time.sleep_ms(500)
        raise OSError("WiFi would not start")

    def _connect(self):
        """Start connecting (station). Returns False if the driver refused three times; ensure() keeps trying."""
        for attempt in range(3):
            try:
                self.wlan.connect(self.ssid, self.password)
                return True
            except OSError as e:
                print("[net] connect refused (%s), retrying" % e)
                try:
                    self.wlan.disconnect()
                except OSError:
                    pass
                time.sleep_ms(500)
        return False

    def joined(self):
        """True when the network is usable: access point up, station joined, or no WiFi at all (tests)."""
        return self.wlan is None or self.mode == "ap" or self.wlan.isconnected()

    def start(self, wifi=True, wait=True):
        """wait=False (the parent at boot): start joining and return at once; ensure() keeps trying and joined()
        says when it worked. wait=True: wait up to 15 s for the join."""
        if wifi:
            import network
            if self.mode == "ap":
                self.wlan = self._up(network, network.AP_IF)
                for attempt in range(3):
                    try:
                        self.wlan.config(essid=self.ssid, password=self.password,
                                         authmode=network.AUTH_WPA2_PSK, channel=self.channel)
                        break
                    except OSError as e:
                        print("[net] access point setup failed (%s), retrying" % e)
                        time.sleep_ms(500)
                else:
                    raise OSError("access point would not start")
                print("[net] access point '%s' up, ip %s" % (self.ssid, self.wlan.ifconfig()[0]))
            else:
                self.wlan = self._up(network, network.STA_IF)
                self._connect()
                if wait:
                    t0 = time.ticks_ms()
                    while not self.wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 15000:
                        time.sleep_ms(250)
                if self.wlan.isconnected():
                    self._joined = True
                    print("[net] joined '%s', ip %s" % (self.ssid, self.wlan.ifconfig()[0]))
                elif wait:
                    print("[net] '%s' not found yet, will keep trying" % self.ssid)
                else:
                    print("[net] searching for '%s' ..." % self.ssid)
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

    def _recover(self, now, why):
        """Start the station over from a clean state (the way start() does): the driver can sit in a state where
        connect() keeps being refused, or hold an association with an access point that has restarted."""
        self._last_reset = now
        self._last_try = now
        self._joined = False
        print("[net] %s: restarting the WiFi interface" % why)
        try:
            self.wlan.disconnect()
        except OSError:
            pass
        try:
            import network
            self.wlan = self._up(network, network.STA_IF)
            self._connect()
            try:
                pm = {"min": network.WLAN.PM_PERFORMANCE, "max": network.WLAN.PM_POWERSAVE}.get(self.power_save, network.WLAN.PM_NONE)
                self.wlan.config(pm=pm)
            except Exception:
                pass
        except Exception as e:
            print("[net] restart of the WiFi interface failed:", e)

    def ensure(self, link_ok=None):
        """Station mode: reconnect if the link dropped (at most every 5 s). link_ok = the application's view (False:
        nothing heard from the other unit). If that lasts more than RECOVER_MS the WiFi interface is restarted from
        scratch, at most every RECOVER_EVERY_MS, whatever isconnected() says (a stale association after the access
        point restarted looks 'connected' but carries nothing)."""
        if self.mode != "sta" or self.wlan is None:
            return
        now = time.ticks_ms()
        if link_ok is not None:
            if link_ok:
                self._down_since = None
            elif self._down_since is None:
                self._down_since = now
        if (self._down_since is not None and time.ticks_diff(now, self._down_since) > RECOVER_MS
                and time.ticks_diff(now, self._last_reset) >= RECOVER_EVERY_MS):
            self._recover(now, "nothing heard from the other unit for %d s" % (time.ticks_diff(now, self._down_since) // 1000))
            return
        if self.wlan.isconnected():
            if not self._joined:
                self._joined = True
                try:
                    print("[net] joined '%s', ip %s" % (self.ssid, self.wlan.ifconfig()[0]))
                except Exception:
                    pass
            return
        if self._joined:
            print("[net] WiFi connection lost, reconnecting")
        self._joined = False
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
    child_addr = peer

    def __init__(self):
        self.packets = []

    def start(self, wifi=True, wait=True):
        pass

    def joined(self):
        return True

    def ensure(self, link_ok=None):
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
