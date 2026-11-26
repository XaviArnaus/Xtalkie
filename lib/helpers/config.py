# helpers/config.py -- defaults plus an optional /config.json that overrides them (per board).
# The only thing that MUST differ between the two boards is "role".
import json

DEFAULTS = {
    "role": "loopback",          # master (child room) | slave (parent) | loopback (test on one board) | play (voice game)
    "port": 4747,
    "cpu_mhz": 160,              # 80 / 160 / 240. Lower = less battery; 160 leaves plenty of headroom for the audio loop
    "auto_reboot": False,        # True for unattended use: restart after a crash AND on a hang (watchdog)
    "watchdog_ms": 15000,        # only used when auto_reboot is true
    "log": True,                 # keep /events.csv on the board (alerts, link events, per-minute summary)
    "wifi": {
        "mode": "auto",          # auto: master = own access point, slave = joins it; or "ap" / "sta"
        "ssid": "babymon",
        "password": "change-me-please",   # WPA2 needs at least 8 characters: CHANGE IT
        "channel": 6,
        "master_ip": "192.168.4.1",       # where the slave finds the master
        "power_save": "none",             # station side only: none | min | max  (battery vs. latency)
    },
    "audio": {"mic_gain": 4, "volume": 0.75, "playback_gain": 2.0,
              "agc": True,           # automatic playback gain (quiet sound lifted, loud held back)
              "agc_max_gain": 150,   # at most 150x (+43 dB); quiet room sound needs a lot
              "volume_level": 4},    # 1..5, the starting level; the menu changes it and remembers it
    "gate": {"act_db": 10.0},    # any Gate2 setting can go here, e.g. "zcr_cap": 60 (lower = more speech alerts)
    "ui": {
        "enabled": True,         # False: no screen at all (battery is still reported to the other unit)
        "manual_refresh": True,  # draw a whole screen, then refresh once (verified on the board with screen_probe.py)
        "brightness": 60,        # status / menu screens (0-100)
        "alarm_brightness": 100,
        "status_s": 10,          # how long a BOOT tap shows the status screen
        "alert_hold_s": 10,      # the bell stays this long after the voice stops
        "flash_ms": 0,           # bell / no-link flashing period in ms (0 = no flashing, a steady picture)
        "test_s": 10,            # length of the live test
        "mute_s": 300,           # BOOT on the no-link screen silences the beeps for this long
    },
    "master": {"preroll_lead_ms": 200, "hb_ms": 1000, "verbose": True,
               "sens_level": 3,      # 1 (least sensitive) .. 5 (most); the parent unit's MIC menu changes it
               "max_open_s": 45,     # a stream longer than this is cut (feedback loop?), then a short pause
               "cooldown_s": 8},
    "play": {                    # the voice game (role "play"): speak, hear yourself, every clip is kept
        "trig_db": 12.0,         # a sound this far above the room floor starts a clip
        "end_db": 6.0,           # ... and a clip ends after hang_ms below floor + end_db
        "hang_ms": 800,
        "pre_ms": 240,           # kept from before the trigger, so no first syllable is cut
        "tail_ms": 300,          # kept after the last sound
        "min_ms": 300,           # shorter sounds (clicks) are ignored
        "max_s": 10,             # a longer sound is cut here
        "speed": 1.0,            # playback speed: 1.0 as spoken, 1.4 chipmunk, 0.75 deep
        "save": True,            # keep every clip as /clips/cNNNN_<seconds>s.wav
        "dir": "/clips",
        "max_total_kb": 6000,    # the oldest clips are deleted beyond this (6000 KB = about 3 minutes of audio)
        "min_free_kb": 2500,     # nothing is saved if the flash would drop below this
        "idle_off_s": 120,       # screen off after this long without a clip (0 = never)
    },
    "slave": {"jitter_frames": 5, "link_timeout_ms": 3000, "alarm_period_ms": 10000,
              "alarm_before_first_link": False, "verbose": True},
}


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def load(path="/config.json"):
    cfg = json.loads(json.dumps(DEFAULTS))       # deep copy
    try:
        with open(path) as f:
            _merge(cfg, json.load(f))
    except OSError:
        pass                                     # no file: defaults
    return cfg


STATE = "/state.json"          # settings changed from the menu (kept apart from config.json)


def state_load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def state_save(key, value):
    s = state_load()
    s[key] = value
    try:
        with open(STATE, "w") as f:
            json.dump(s, f)
    except OSError:
        pass
