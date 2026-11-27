# Xtalkie: hardware test for the 0.2.0 - 0.6.0 changeset

Everything since the `live-test-1` tag passed the host-side tests only (`python tests/run_all.py`). This list is the
first test on the real boards, ordered so the whole thing takes the least time. What every button does is in
[BEHAVIOUR.md](BEHAVIOUR.md). Tick the boxes; write down anything that differs and send it back together with the
serial output marked **[send]**.

**Rollback:** `git checkout live-test-1`, then `python pc/deploy.py <port> <role> ...` on each board.
**Names used below:** CHILD = the board in the child's room (role `child`), PARENT = the other board (role `parent`).
**Unresponsive unit:** if a unit does not answer for a minute, connect it to the computer (Thonny), read the serial output.

## 0. Prepare

- [ ] Both boards on USB, Thonny closed. Deploy (same SSID and password on both; `--night` only for step 12):
  `python pc/deploy.py <port> child --ssid xtalkie --password <8+ chars>` and the same with `parent`.
  (The default WiFi name is now `xtalkie`. A board whose old `config.json` still says `babymon` would not find the other one: deploy rewrites it.)
- [ ] `python pc/versions.py` lists both boards as `0.6.x <commit>` with roles child and parent (it restarts them afterwards).
- [ ] Open Thonny on one board, press Stop, then Ctrl+D in the shell (soft reboot) and copy everything it prints. **[send]**
  Look for: `xtalkie 0.6.x ...: role`, the `[boot] last run ended: ...; reset cause: ...; started by a person: ...; crashes in a row: ...`
  line, four `[boot] +NNN ms` step lines, `[net]` lines, `[disk]`.
  Do the same for the other board. A soft reboot may not look like a power-on: that is expected and is part of what we learn.

## 1. Start-up screens (PARENT first)

Switch the PARENT off and on with its power switch.

- [ ] Start-up screen shows XTALKIE, `0.6.x <commit>`, PARENT UNIT, and CONFIG / AUDIO / NETWORK / READY ticking green one by one.
- [ ] NETWORK shows amber SEARCHING (CHILD still off) and the screen does not freeze for 15 s.
- [ ] One short beep at READY. Amber hint `HOLD BUTTON 2 S: CHOOSE ROLE` appears for about 3 s, then goes.
- [ ] After about 4 s more: the status screen (NO LINK, red cross), then dark. No alarm beeps (no contact yet).
- [ ] Layout: nothing overlaps or runs off the screen (title, version, steps, hint). Photo if odd. **[send]**
- [ ] Power-on to usable: you can press BOOT (status screen) during SEARCHING, without waiting.

## 2. Child unit stays dark (CHILD)

- [ ] Power-switch the CHILD off and on: start-up screen with one beep, then dark after 4 s. (Hint line shows for 3 s.)
- [ ] Restart the CHILD without marking it as a person's doing: `python -m mpremote connect <port> reset` (these boards have no RESET button; close Thonny and `pc/watch.py` first, and the CHILD must be running main.py): the screen stays **dark** and silent. Tap BOOT: the status screen's bottom line says
  `RESTART: NO CLEAN STOP` (or `OTHER`; with `mpremote ... reset` it is `OTHER`, because mpremote stops the program with Ctrl+C first, which counts as a clean stop; `NO CLEAN STOP` needs a watchdog restart or a hang). The text is dark gray. **[send the serial output of this boot if it lit up, or the bottom line if not]**
- [ ] The CHILD never lights or beeps on its own during all of the tests below. Note if it does.
- [ ] CHILD hold on status: dark. CHILD has no menu, however long you hold.

## 3. Link, versions, restart report (both on)

- [ ] PARENT shows the status screen when the link comes up: green check, CONNECTED, battery of both units, version `0.6.x <commit>`.
- [ ] No amber line on either unit (same version). The CHILD status shows `STARTED BY A PERSON` at the bottom.
- [ ] Restart the CHILD the same way (`mpremote ... reset`), wait for the link: the PARENT shows (tap BOOT if needed) amber `CHILD RESTARTED`, and stays so.
- [ ] Power-switch the CHILD off and on: the amber `CHILD RESTARTED` line disappears once it reports again.
  If it stays, the RTC memory survives the power switch (the battery keeps it alive): **[send]** that, and which unit.
- [ ] Optional: change `VERSION` in `/lib/version.py` on one board (Thonny), reset it: the other shows amber `CHILD HAS ...` / `PARENT HAS ...`.
  Put it back afterwards (redeploy).

## 4. Parent menu

Hold BOOT on the PARENT (about 1.5 s), let go.

- [ ] The menu has 6 items (TEST LIVE, TEST ALARM, VOLUME n, MIC n, ROLE, EXIT), all inside the screen, text readable. Photo. **[send]**
- [ ] Tap moves the highlight, hold selects. 20 s of nothing: screen goes dark.
- [ ] TEST LIVE: talk near the CHILD, level bar moves, ends with AUDIO OK. A press during the test goes back to the menu.
- [ ] TEST ALARM: bell and 3 beeps, dark after 4 s.
- [ ] VOLUME: number steps 1..5 and wraps, a beep at each step. MIC: number steps and the CHILD reacts to it (more/less sensitive).
- [ ] EXIT goes dark.

## 5. Alerts and link loss

- [ ] Clap or call near the CHILD: PARENT shows the bell and plays the audio. A tap dismisses the bell, the sound continues.
- [ ] While the bell shows and the voice plays, tap BOOT: the screen goes dark and the voice stops at once; the next alert plays normally.
- [ ] 3 quick taps (about 2 per second): SOUND OFF screen for 3 s. Make an alert: the bell shows, no voice. Switch the CHILD off: NO LINK, no beeps.
  Tap once: status screen with amber SOUND OFF on top (check the layout). Power-cycle the PARENT: still SOUND OFF. 3 quick taps: SOUND ON and one beep.
- [ ] Snoring-like noise / room noise: no alert (as in `live-test-1`).
- [ ] Switch the CHILD off: after about 3 s the PARENT shows the red cross and beeps 3 times every 10 s. Tap: screen dark and the beeps stop for good (also if you tap during the beeps, or later on the status screen). Switch the CHILD on, then off again: the full-screen alarm and the beeps start again.
- [ ] Switch the CHILD on again: the PARENT shows the status screen, beeps stop.

## 6. Role switch from the menu

- [ ] PARENT: menu, ROLE: list shows CHILD / PARENT / PLAY / BACK with the cursor on PARENT. Hold on PARENT and on BACK: back, nothing changes.
- [ ] Choose PLAY: confirmation `SWITCH TO PLAY MODE / THE UNIT RESTARTS`, HOLD: YES, TAP: NO. Tap: back to the list. Nothing written.
- [ ] Choose PLAY again, hold = YES: RESTARTING, the board restarts in play mode with start-up screen and one beep.
- [ ] Thonny file view: `/config.json` has `"role": "play"` and your WiFi settings still in it; `/config.json.bak` has the old file; no `.new` file left. **[send the file contents with the password blanked]**
- [ ] The file system type does not matter to you, but if anything says NOT SAVED, send the line below it. **[send]**

## 7. Play mode

- [ ] Green ring SPEAK. Speak: after your sound the blue LISTEN disc and your voice played back. Clip count rises.
- [ ] Hold BOOT while idle: menu with VOLUME n, SPEED x, ROLE, EXIT. Microphone is silent meanwhile. SPEED 0.75 / 1.0 / 1.4 changes the playback.
- [ ] Press BOOT during a recording: nothing happens (no glitch in the clip).
- [ ] Screen dark after 2 minutes; tap wakes it.
- [ ] Menu, ROLE, PARENT, confirm: the board restarts as the PARENT again (config.json role `parent`, WiFi settings intact).

## 8. Role chooser at start-up

- [ ] Power-switch the PARENT on, and as soon as the hint `HOLD BUTTON 2 S: CHOOSE ROLE` shows, hold BOOT for at least 2 s, then let go: the role list opens.
  (Do not hold BOOT while switching on: that enters download mode.)
- [ ] Choosing the current role or BACK carries on starting normally. Doing nothing for 2 minutes also carries on.
- [ ] Power-switch the CHILD on and hold as above: the chooser opens (a person started it). After an automatic restart (`mpremote ... reset`) it does **not** wait.

## 9. WiFi order and slow start

- [ ] Switch the PARENT on **before** the CHILD: it is usable at once (menu works), shows NO LINK, then the link comes up by itself when the CHILD is on. `[net] joined` appears in the serial output.

## 10. Crash loop (do this one last; it needs Thonny to edit the file, and `pc/watch.py` to read the output)

The two crashes are made on purpose with a bad config. Both use `auto_reboot` so the board restarts itself.

- [ ] CHILD: in Thonny set `/config.json` to `{"role": "child", "auto_reboot": true, "gate": {"nonexistent": 1}}` and reset it.
  Expected: it restarts every 5 s or so; serial shows `crashes in a row: 1, 2, 3, ...`, then `child unit stays dark`; the screen stays **dark and silent** (the very first start after your own reset may light up: a person did it); the PARENT shows NO LINK and beeps. **[send the serial output]**
- [ ] Restore the CHILD with `python pc/deploy.py <port> child ...` (rewrites config.json).
- [ ] PARENT: set `/config.json` to `{"role": "parent", "auto_reboot": true, "parent": null}` and reset it.
  Expected: after 3 crashes in a row the role chooser appears (title **CRASHES**). Choosing the current role carries on and crashes again.
  **[send the serial output]**
- [ ] Restore the PARENT with `python pc/deploy.py <port> parent ...`.
- [ ] `/events.csv` on each board (Thonny file view): the `boot` lines show `prev=`, `cause=`, `manual=`, `crashes=`. **[send events.csv]**

## 11. What to look at in the serial output

| You see | It means |
|---|---|
| `last run ended: none ... started by a person: yes` | cold power-on, as expected |
| `last run ended: run (no clean end) ... reset cause: 3` (or similar) | a reset button or watchdog restart; the CHILD must stay dark |
| `started by a person: no` but you switched it on | the reset cause or RTC memory did not behave as assumed: send the line, set `"ui": {"boot_screen": "always"}` on that board meanwhile |
| `[boot] +NNN ms CONFIG/AUDIO/NETWORK/READY` | how long start-up takes; the READY time is "power-on to usable" |
| `[net] searching for 'xtalkie' ...` then `[net] joined ...` | the non-blocking WiFi join |
| `[ui] screen disabled` | the shared panel did not start: send the lines before it |

## 11b. The clock (0.8.0)

- [ ] `python pc/deploy.py <port> child ... ` prints `setting the board's clock ...`; the serial output at the next start
  says `[clock] YYYY-MM-DD HH:MM:SS (chip)` with the right time. **[send]**
- [ ] `python pc/settime.py <port>` shows computer and board with the same time and `clock chip: set`.
- [ ] Unplug USB, switch the unit off with PWR for two minutes (battery in), switch it on, connect USB later and read the
  `boot` line in `events.csv` (`python -m mpremote connect <port> fs cat :events.csv`): `clock=chip,sysclock=lost` and a
  date/time that is right = the chip kept the time while the power was off. **[send]** that line
- [ ] `events.csv` lines start with the date and time; a line with `-` means the clock was not set.
- [ ] After a hard restart (`python -m mpremote connect <port> reset`) the time is still right.

## 12. The real night (after everything above)

- [ ] Redeploy both with `--night`: `python pc/deploy.py <port> child --ssid ... --password ... --night`, `... parent ... --night`.
- [ ] CHILD on USB power, PARENT within range. Check at start: link up, CHILD dark.
- [ ] Morning: `python pc/versions.py` (restarts the boards, do it only when the night is over), and copy `/events.csv` from both boards. **[send]**
  Look for `boot` lines in the middle of the night: each is a restart; `crashes=` tells how many in a row.

## What I would watch most

- Start-up order changed (panel before audio) and the WiFi join no longer waits: both only matter on real boards.
- The child unit's "dark" rule depends on the RTC memory surviving resets and on `reset_cause()`: sections 2, 3 and 10 test that.
- Screen layout of the new lines (amber `CHILD RESTARTED`, gray start note, hint, six-item menu).
- Whether holding BOOT for 2 s right after power-up feels easy enough, or whether the 3 s window is too short.
