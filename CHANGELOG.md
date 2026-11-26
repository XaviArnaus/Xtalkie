# Changelog

Bump `VERSION` in `lib/version.py` for every change that goes onto a board, and add a line here.
`pc/deploy.py` adds the git commit to what the board reports (`+` = modified files), `pc/versions.py` lists the boards.

## 0.7.0
- Rename: the roles `master` / `slave` are now `child` / `parent` (the unit in the child's room and the unit with the
  parent), because the parent unit has the control and the child unit only sends. No change in behaviour. Everywhere:
  the role in `config.json` and in the role menu / chooser, `app/child.py` and `app/parent.py` (were `master.py`,
  `slave.py`), the settings sections `child` and `parent`, `wifi.child_ip` (was `master_ip`), the serial and
  `events.csv` tags (`[child]`, `[parent]`, `child,...`, `parent,...`), `deploy.py <port> child|parent`, the docs and
  the tests. The wire protocol is unchanged, so a 0.6.x unit still talks to a 0.7.0 unit.
- A `config.json` written with the old names still works: the old role names, the sections `master` / `slave` and
  `wifi.master_ip` are translated when the file is loaded (tests/test_names.py). `deploy.py` also still accepts
  `master` / `slave` as the role and removes the old `lib/app/master.py` and `slave.py` from the board.
- Old lines in an existing `events.csv` keep the old tags. The history of this file below keeps the old names.

## 0.6.4
- Parent unit: after the child unit restarted, the two stayed at NO LINK for minutes (found while redeploying).
  Cause not proven (no serial output of that moment); likely a stale association or a driver stuck refusing
  connect(). Now: the parent counts how long it hears nothing from the child. After 20 s it restarts its WiFi
  interface from scratch (the way start-up does), whatever `isconnected()` says, and again every 30 s while the
  silence lasts. A healthy link is never touched. New serial lines: `[net] WiFi connection lost, reconnecting`,
  `[net] nothing heard from the other unit for N s: restarting the WiFi interface`.
- The 3-tap sound switch needed several tries on the board: every tap redrew the screen (about 200 ms, BOOT is not
  read meanwhile). A tap on the status screen now only restarts its timer, and the allowed gap between taps is
  1200 ms (`ui.mute_gap_ms`, was 800).
- UNVERIFIED on the boards. Expected time to find the child again after a restart: about 10 to 40 s.

## 0.6.3
- Parent unit: BOOT on the bell screen now also STOPS THE VOICE of that alert (before, only the screen went dark and
  the audio played to the end). The rest of that stream is dropped; the next alert plays normally.
- Parent unit: 3 quick BOOT taps (each within `ui.mute_gap_ms` = 800 ms of the one before) switch the sound OFF or ON.
  OFF = no voice and no beeps (no-link beeps, test alarm). The bell screen still shows. The state is remembered in
  `state.json` (`sound_off`), also after a restart. A short SOUND OFF / SOUND ON screen confirms it, ON gives one
  beep, and the status screen shows an amber `SOUND OFF` line at the top for as long as it is off. Not active in the
  menu screens, and not on the child unit.
- UNVERIFIED on the boards: the confirmation screen and the position of the SOUND OFF line; whether 800 ms feels right.

## 0.6.2
- No-link alarm (found in the first hardware test): a BOOT press now ACKNOWLEDGES it until the link changes. Before, it
  muted the beeps for 5 minutes and they came back in a loop; a press on the status screen did nothing. Now:
  any press while the link is down silences the beeps, a press during the beeps stops them at once (the beep loop checks
  the button), and the beeps return only after the link came back and was lost again (new full-screen alarm).
  The `ui.mute_s` setting is gone.
- UNVERIFIED on the boards.

## 0.6.1
- Fix (found in the first hardware test): the ready beep (a single beep) was inaudible, and the first beep of an alarm
  too: the speaker amplifier needs more than 160 ms to wake up. `Audio.beep()` now plays 300 ms of silence
  (`lead_frames=15`) after switching the amplifier on, before the first tone. Every beep starts 300 ms later.
- UNVERIFIED on the boards: that 300 ms is enough (raise `lead_frames` if the first beep is still weak).

## 0.6.0
- The child unit stays dark and silent after ANY automatic restart or crash loop (no chooser, no blink, no beep).
  To avoid "looks bricked":
  - a BOOT tap on the child unit's status screen now shows how this run started, at the bottom: `STARTED BY A PERSON`,
    `RESTART: CRASH X2`, `RESTART: NO CLEAN STOP`, `RESTART: OTHER`;
  - the child unit reports "I restarted by myself" (and the crashes in a row) in every heartbeat (appended after the
    version; older units ignore it). The parent's status screen then shows an amber `CHILD RESTARTED` (`X3`) line until
    a person restarts the child unit, and the parent logs/prints it once. The status screen is redrawn when this (or the
    other unit's version) arrives, so it is right even when it opened together with the link.
- Not covered: a crash loop before the app starts (or a watchdog / hardware reset that runs no code): then nothing can
  be shown. If a unit does not answer for a minute, connect it to the computer.
- UNVERIFIED on the boards: the amber and gray lines' position on the status screen.

## 0.5.0
- Boot chooser: hold BOOT for 2 s while the start-up screen says `HOLD BUTTON 2 S: CHOOSE ROLE` (a 3 s window after
  READY; nothing of the role has started yet, so it works whatever the role's code does) to pick MASTER / SLAVE / PLAY.
  Same list and confirmation as the ROLE menu; choosing the current role, BACK, or no answer for 2 minutes carries on
  with the role in `config.json`.
- Crash loop: after 3 crashes in a row the chooser appears instead of starting the same role once more, right after the
  CONFIG step. NOT on the child unit: it stays dark and silent in a crash loop too (the parent unit's "no link" alarm
  is the signal; a person power-cycles the child unit to get the start-up screen and the chooser).
  A run of one minute ends the loop.
  The count lives in the RTC marker (now 7 bytes; units that still have the old marker simply start from 0) and is
  printed and logged at every boot (`crashes=`).
- The watchdog now starts after the chooser window (the chooser may wait for minutes).
- Config (`ui`): `chooser_window_s` (3, 0 = no chooser at start-up), `chooser_hold_s` (2), `chooser_timeout_s` (120),
  `crash_limit` (3, 0 = never).
- UNVERIFIED on the boards: holding the button for 2 s right after power-up, the chooser screens, crash counting after
  real crashes and watchdog restarts.

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
