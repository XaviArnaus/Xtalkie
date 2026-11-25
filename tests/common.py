"""Shared setup for the host-side tests: stubs first, our lib next, MicroPython's time functions."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, ROOT)


def patch_time(real=False):
    """real=True: sleeping really sleeps (threaded simulations). Otherwise sleeping is instantaneous."""
    time.sleep_ms = (lambda ms: time.sleep(ms / 1000)) if real else (lambda ms: None)
    time.ticks_ms = lambda: int(time.monotonic() * 1000)
    time.ticks_us = lambda: int(time.monotonic() * 1e6)
    time.ticks_diff = lambda a, b: a - b
    time.ticks_add = lambda a, b: a + b


def check(cond, msg):
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        global FAILED
        FAILED = True


FAILED = False


def finish():
    sys.exit(1 if FAILED else 0)
