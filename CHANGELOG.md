# Changelog

Bump `VERSION` in `lib/version.py` for every change that goes onto a board, and add a line here.
`pc/deploy.py` adds the git commit to what the board reports (`+` = modified files), `pc/versions.py` lists the boards.

## 0.4.0
- Role switching from the menu. Parent unit: MENU > ROLE (the menu now has 6 items). Play mode: hold the button
  while it is idle > VOLUME, SPEED, ROLE, EXIT. ROLE lists MASTER / SLAVE / PLAY / BACK, asks for confirmation
  (hold = yes, tap = no), writes `config.json`, and restarts the board (marked as started by a person, so the start-up
  screen shows).
- `config.json` is changed safely: only the `role` key, the old file kept as `config.json.bak`, the new text written to
  `config.json.new`, read back, then renamed over the old file. A file that cannot be parsed is never overwritten.
  `config.load()` falls back to `config.json.new` if a switch was cut off between removing and renaming.
- The child unit (master) still has no menu: a toddler cannot switch its role.
- Play mode: the button works (long press = menu, tap = wake the screen); the menu opens only when no clip is being
  recorded and the microphone is closed meanwhile. SPEED (0.75 / 1.0 / 1.4) is remembered in `state.json`.
- Shared pieces moved to `lib/ui/menu.py` (button, VOLUME action, role switch).
- UNVERIFIED on the boards: the menu and confirmation screens, the restart, the play menu.

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
