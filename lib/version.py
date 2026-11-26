# version.py -- what code is on this board.
#
# VERSION is bumped by hand for every change that goes onto a board (see CHANGELOG.md).
# pc/deploy.py also writes lib/_build.py (git commit + "modified" flag) on the board, so a deployed unit reports
# e.g. "0.2.0 6f14f8d" or "0.2.0 6f14f8d+" (+ = files differed from the commit). A hand-flashed unit has no
# _build.py and reports just "0.2.0". No hardware access here: usable from every layer and from the PC.
VERSION = "0.7.0"

try:
    from _build import COMMIT, DIRTY
except ImportError:
    COMMIT, DIRTY = None, False


def full():
    """The version text shown on screens, written to the log and sent to the other unit (ASCII, short)."""
    if not COMMIT:
        return VERSION
    return "%s %s%s" % (VERSION, COMMIT, "+" if DIRTY else "")
