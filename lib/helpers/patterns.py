# helpers/patterns.py -- the snore patterns the child unit has learned (dsp/gate.py), kept as JSON on the flash so they
# survive a restart and can be read afterwards (`bin/xtalkie patterns`). One small file (a few hundred bytes per
# pattern, at most 8 patterns). Written to a temporary file first, so a power cut never leaves a half-written file.
# Nothing here may stop the monitor: every function swallows its errors (load -> [], save -> False).
import json
import os

PATH = "/patterns.json"
MIN_FREE = 150000


def _free():
    st = os.statvfs("/")
    return st[0] * st[3]


def load(path=None):
    path = path or PATH
    for p in (path, path + ".tmp"):                 # the .tmp file is what is left after a cut between remove and rename
        try:
            with open(p) as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = data.get("patterns")
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save(items, path=None):
    path = path or PATH
    try:
        if _free() < MIN_FREE:
            return False
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(json.dumps({"patterns": items}))
        try:
            os.remove(path)
        except OSError:
            pass
        os.rename(tmp, path)
        return True
    except Exception:
        return False
