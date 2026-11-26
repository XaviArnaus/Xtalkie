"""The roles are called child / parent (0.7.0); a config.json written with the old names master / slave still works."""
import json
import os
import tempfile

from common import check, finish

from helpers import config


def load_text(d, text):
    p = os.path.join(d, "config.json")
    with open(p, "w") as f:
        f.write(text)
    return config.load(p)


check(config.DEFAULTS["child"]["sens_level"] == 3 and "parent" in config.DEFAULTS, "the default settings sections are child / parent")
check("master" not in config.DEFAULTS and "slave" not in config.DEFAULTS, "no old names are left in the defaults")
check(config.SWITCHABLE == ("child", "parent", "play"), "the role menu offers child / parent / play")
with tempfile.TemporaryDirectory() as d:
    c = load_text(d, '{"role": "master", "master": {"sens_level": 5}, "slave": {"jitter_frames": 9}, "wifi": {"master_ip": "10.0.0.1"}}')
    check(c["role"] == "child", "an old config.json with role master starts as the child unit")
    check(c["child"]["sens_level"] == 5 and c["child"]["cooldown_s"] == 8, "the old 'master' section is read as 'child' (other settings keep their defaults)")
    check(c["parent"]["jitter_frames"] == 9, "the old 'slave' section is read as 'parent'")
    check(c["wifi"]["child_ip"] == "10.0.0.1" and "master_ip" not in c["wifi"], "wifi.master_ip is read as wifi.child_ip")
    check("master" not in c and "slave" not in c, "no old keys remain after loading")
    c = load_text(d, '{"role": "slave"}')
    check(c["role"] == "parent", "role slave starts as the parent unit")
    c = load_text(d, '{"role": "parent", "slave": {"jitter_frames": 9}, "parent": {"jitter_frames": 3}}')
    check(c["parent"]["jitter_frames"] == 3, "when both names are present the new one wins")
    c = load_text(d, '{"role": "slave", "slave": null}')
    check(c["role"] == "parent" and c["parent"] is None, "a null section stays null (used by the crash-loop test)")
    c = load_text(d, '{"role": "child", "child": {"sens_level": 2}}')
    check(c["role"] == "child" and c["child"]["sens_level"] == 2, "a config in the new names is read as written")
    p = os.path.join(d, "config.json")
    with open(p, "w") as f:
        f.write('{"role": "master", "wifi": {"ssid": "abc"}}')
    ok, msg = config.save_role("parent", p)
    saved = json.load(open(p))
    check(ok and saved["role"] == "parent" and saved["wifi"] == {"ssid": "abc"}, "the role switch writes the new name and keeps the rest")
    check(not config.save_role("slave", p)[0], "the role menu cannot write an old role name")
finish()
