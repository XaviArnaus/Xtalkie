#!/usr/bin/env python3
"""Runs every host-side test (no hardware needed; Python 3 only). About 1.5 minutes: two tests run in real time."""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ["test_layers.py", "test_gate.py", "test_loopback.py", "test_tools.py", "test_clock_tools.py", "test_clock.py", "test_names.py", "test_wifi.py", "test_version.py", "test_boot.py", "test_roles.py", "test_chooser.py", "test_play.py", "test_link.py", "test_mute.py", "test_nightclips.py", "test_safety.py"]
failed = []
t0 = time.time()
for t in TESTS:
    print("\n=== %s" % t, flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, t)], cwd=HERE)
    if r.returncode:
        failed.append(t)
print("\n%s  (%d of %d test files passed, %.0f s)" % ("ALL PASSED" if not failed else "FAILED: " + ", ".join(failed),
                                                    len(TESTS) - len(failed), len(TESTS), time.time() - t0))
sys.exit(1 if failed else 0)
