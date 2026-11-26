# Changelog

Bump `VERSION` in `lib/version.py` for every change that goes onto a board, and add a line here.
`pc/deploy.py` adds the git commit to what the board reports (`+` = modified files), `pc/versions.py` lists the boards.

## 0.3.0
- Start-up screen (name, version, role, steps CONFIG / AUDIO / NETWORK / READY), then the ready screen for `ui.ready_s`
  (4) seconds, then the status screen on the parent unit. Every step is also printed with its time (`[boot] +123 ms`).
- The panel is opened once in `main.py` and shared with the HUD / play screen (no double initialisation).
- Child unit (master): stays DARK after an automatic restart (crash, watchdog, reset button) so a 3 a.m. restart never
  lights the room. It lights only when a person started it. Decided from an RTC-memory marker plus
  `machine.reset_cause()`; both raw values are printed and logged at every boot (`boot,...,prev=,cause=,manual=`).
  `pc/deploy.py` and `pc/versions.py` mark their restarts as "manual".
- One short ready beep when a person switches a unit on (`ui.boot_beep`). Never after an automatic restart.
- `ui.boot_screen`: `auto` (default) | `always` | `never` overrides the decision.
- The slave no longer waits up to 15 s for WiFi at power-up: its screen and button work at once and the NETWORK step
  shows SEARCHING.
- UNVERIFIED on the boards: what each kind of reset reports, whether RTC memory survives them, the screen layout.

## 0.2.0
- Renamed to Xtalkie (code, docs, boot message). Default WiFi name is now `xtalkie` (was `babymon`):
  a board whose `config.json` still names `babymon` will not find one on the default.
- Software version: `lib/version.py`; shown at boot, in the log (`boot,...,ver=`), and on the status screen.
- The units tell each other their version (appended to HELLO and HB; older units ignore it). The status screen
  shows an amber `<OTHER> HAS <version>` line when the versions differ.
- `pc/deploy.py` stamps the commit on the board; `pc/versions.py` lists the version and role of connected boards.

## 0.1.0 (git tag `live-test-1`, shown as "unknown" by `pc/versions.py`)
- Baby monitor: master / slave, snore-aware gate, alerts, menu, live test, volume and MIC levels, link-loss alarm.
- WiFi start fix (`Wifi Internal State Error`).
- Play mode (one board, records and replays voice clips); not yet tried on a board.
