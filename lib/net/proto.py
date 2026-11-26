# net/proto.py -- the tiny UDP protocol between master and slave.
# Every datagram: 2-byte magic, type, flags, 4-byte sequence number, then the payload.
import struct

MAGIC = b"BM"
T_AUDIO = 1      # payload: 320 samples, 16-bit little endian, mono, 16 kHz (640 bytes)
T_END = 2        # the audio stream of this event is over
T_HB = 3         # master -> slave, once a second: payload = gate_open (1 byte), floor_db*10 (int16)
T_HELLO = 4      # slave -> master, once a second: lets the master learn the slave's address + battery
T_CMD = 5        # slave -> master: a command (CMD_LIVE = stream the live microphone for N seconds)
CMD_LIVE = 1
CMD_SENS = 2     # set the child unit's sensitivity level 1..5 (arg)
F_PREROLL = 1    # audio from before the alert (sent so the start of a word is not lost)
F_TEST = 2       # audio of a live test (the slave shows the test screen, not the alert)

_HDR = "<2sBBI"
HDR_LEN = 8


def pack(ptype, seq, payload=b"", flags=0):
    return struct.pack(_HDR, MAGIC, ptype, flags, seq & 0xFFFFFFFF) + payload


def parse(data):
    """Return (type, flags, seq, payload) or None if this is not one of our datagrams."""
    if len(data) < HDR_LEN or data[:2] != MAGIC:
        return None
    ptype, flags, seq = struct.unpack_from("<BBI", data, 2)
    return ptype, flags, seq, data[HDR_LEN:]


# The software version rides at the END of HELLO and HB payloads: 1 length byte + ASCII text. Units without
# this feature read only the first bytes of those payloads and ignore the rest, so old and new units mix.
VER_MAX = 24


def _ver_bytes(version):
    v = str(version).encode()[:VER_MAX]
    return bytes([len(v)]) + v


def _ver_parse(payload, offset):
    """The version text after `offset` bytes, or None (old unit, or damaged)."""
    if len(payload) <= offset:
        return None
    n = payload[offset]
    if n == 0 or n > VER_MAX or len(payload) < offset + 1 + n:
        return None
    try:
        return bytes(payload[offset + 1:offset + 1 + n]).decode()
    except Exception:
        return None


def pack_hb(seq, gate_open, floor_db, batt=None, charging=False, sens=0, version=None, restart=None):
    """restart (0..255) follows the version field: 0 = started by a person, n > 0 = restarted by itself (see
    helpers/bootinfo.restart_code). Without a version an empty version field keeps the layout."""
    f = 0 if floor_db is None else int(floor_db * 10)
    b = 255 if batt is None else int(batt)
    body = struct.pack("<BhBBB", 1 if gate_open else 0, f, b, 1 if charging else 0, sens)
    if version or restart is not None:
        body += _ver_bytes(version or "")
    if restart is not None:
        body += bytes([min(255, max(0, int(restart)))])
    return pack(T_HB, seq, body)


def parse_hb(payload):
    """(gate_open, floor_db, battery_percent or None, charging, sensitivity level or 0) or None."""
    if len(payload) < 3:
        return None
    g, f = struct.unpack("<Bh", payload[:3])
    batt = None
    charging = False
    sens = 0
    if len(payload) >= 5:
        b, fl = struct.unpack("<BB", payload[3:5])
        batt = None if b == 255 else b
        charging = bool(fl & 1)
    if len(payload) >= 6:
        sens = payload[5]
    return bool(g), f / 10, batt, charging, sens


def parse_hb_version(payload):
    """Software version text of the master, or None."""
    return _ver_parse(payload, 6)


def parse_hb_restart(payload):
    """The master's restart code (0 = started by a person, n > 0 = restarted by itself), or None (older unit)."""
    if len(payload) <= 6:
        return None
    n = payload[6]
    if n > VER_MAX or len(payload) <= 7 + n:
        return None
    return payload[7 + n]


def pack_hello(seq, batt=None, charging=False, version=None):
    b = 255 if batt is None else int(batt)
    body = struct.pack("<BB", b, 1 if charging else 0)
    if version:
        body += _ver_bytes(version)
    return pack(T_HELLO, seq, body)


def parse_hello_version(payload):
    """Software version text of the slave, or None."""
    return _ver_parse(payload, 2)


def parse_hello(payload):
    """(battery_percent or None, charging)."""
    if len(payload) < 2:
        return None, False
    b, fl = struct.unpack("<BB", payload[:2])
    return (None if b == 255 else b), bool(fl & 1)


def pack_cmd(seq, cmd, arg=0):
    return pack(T_CMD, seq, struct.pack("<BB", cmd, arg))


def parse_cmd(payload):
    if len(payload) < 2:
        return None, 0
    return struct.unpack("<BB", payload[:2])


def level_db(payload):
    """Level (dBFS) of one audio payload; used by the live test screen."""
    import math
    vals = struct.unpack("<%dh" % (len(payload) // 2), payload)
    acc = 0
    for v in vals:
        acc += v * v
    r = math.sqrt(acc / len(vals))
    return 20 * math.log10(r / 32768) if r > 0 else -99.0
