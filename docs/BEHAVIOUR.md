# Xtalkie: what every button press does (version 0.6.0)

One physical control: the **BOOT button**. This page lists, per unit and per screen, what a **tap** and a **hold** do,
and what the units do on their own. Written from the code; when the behaviour changes, change this page in the same
commit. (Touch input will replace most of this: see the last section.)

## 1. How the button works

- **Tap** = press and release in under 1.2 s (shorter than 40 ms is ignored as bounce).
- **Hold** = keep it down for **1.2 s or more**. The action happens **when you let go**, not while you hold.
- Holding longer than 1.2 s makes no difference (except at start-up, section 5, where at least 2 s is needed).
- The panel is **dark unless something is shown**. A press on a dark unit never does anything except wake a screen.
- Do not hold BOOT while the board is being reset or powered: that enters the chip's download mode.

## 2. Quick card

| Where | Tap | Hold |
|---|---|---|
| Child unit, dark | status screen | status screen |
| Child unit, status | restart the 10 s timer | dark |
| Parent unit, dark | status screen | **menu** |
| Parent unit, status | restart the 10 s timer | **menu** |
| Parent unit, bell (alert) | dismiss (dark) **and stop the voice** | same |
| Parent unit, any screen except menus | **3 quick taps**: sound off / on | (resets the count) |
| Parent unit, no link | acknowledge: beeps stop until the link changes, dark | same |
| Menu | next item | select the item |
| TEST LIVE running | back to the menu | back to the menu |
| TEST ALARM running | dark | dark |
| Role list | next entry | choose the entry |
| Role confirmation | **NO** (back to the list) | **YES** (writes config.json, restarts) |
| Play mode, screen dark | wake the screen | open the play menu |
| Play mode, screen on, idle | nothing | open the play menu |
| Play mode, recording a clip | ignored | ignored |
| Start-up screen (the "ready" step) | status screen | menu (parent) / status (child) |
| Start-up, within the first 3 s after READY | (nothing) | hold **2 s**: role chooser |

Every menu, list and confirmation goes dark by itself after **20 s** without a press (4 s for "NOT SAVED").

## 3. Child unit (role `master`, in the child's room)

It must never light the room or make a sound by itself. It listens, decides with the gate, and streams to the parent.

| Situation | Screen | Sound |
|---|---|---|
| Normal running | dark | none |
| Child calls / alert | dark (the parent shows the bell) | none (the parent plays it) |
| Power switched on by a person | start-up screen, then dark after 4 s | one short beep |
| Automatic restart (crash, watchdog, reset button), also a crash loop | **dark** | none |
| Tap or hold on the dark unit | status screen for 10 s | none |

Status screen of the child unit: title CHILD ROOM, software version, green check = CONNECTED / red cross = NO LINK, battery
of this unit (ME) and of the parent (PARENT), and at the bottom how this run started:

- `STARTED BY A PERSON`: power switch, deploy, role switch.
- `RESTART: CRASH` (`X2` = crashes in a row): the program crashed and restarted itself.
- `RESTART: NO CLEAN STOP`: watchdog, reset button, or a crash that ran no code.
- `RESTART: OTHER`: restarted and nothing else is known.

The child unit has **no menu**: a toddler cannot change anything. Hold on the status screen only turns the screen off.
To change its role: power-cycle it and use the start-up chooser (section 5), edit `config.json`, or run `pc/deploy.py`.

If it does not answer at all (no tap response, no link on the parent) for a minute, connect it to the computer.

## 4. Parent unit (role `slave`) and the loopback test role

The loopback role behaves like the parent unit on one board.

### 4.1 What happens by itself

| Event | Screen | Sound |
|---|---|---|
| Link comes up (first time, or after a loss) | status screen 10 s | none |
| Child calls / alert | **bell**, until dismissed or 10 s after the sound ends | the child's audio |
| Link lost (3 s without a packet) | **red cross: NO LINK**, stays | 3 beeps every 10 s, until acknowledged |
| Link returns | status screen 10 s | beeps stop |
| No alarm before the first contact | (power-up with the child unit off: no alarm until it was heard once) | |

- Bell: tap or hold = dismiss the screen **and stop the voice** of this alert (the rest of the stream is dropped; the next alert plays again).
- **Sound off / on**: 3 quick taps (each within 1.2 s of the previous one) on the parent unit, on any screen except the menus. OFF = no voice and no beeps (no-link beeps and TEST ALARM too); the bell still shows. A screen says SOUND OFF / SOUND ON for 3 s (ON also gives one beep), and the status screen shows an amber `SOUND OFF` line on top while it is off. **It is remembered across restarts** until you switch it on again the same way. Taps 1 and 2 still do their normal job (wake the status screen, dismiss).
- No link: tap or hold = **acknowledge**: the beeps stop and the screen goes dark. Nothing beeps again until the link has come back and been lost once more (then: full-screen alarm and beeps again). A tap on the dark or status screen while the link is down also silences the beeps. A press during the beeps stops them at once.
- A sound longer than 45 s is cut by the child unit and paused 8 s (stops an acoustic feedback loop).

### 4.2 Status screen (tap, or the link coming up)

Title PARENT UNIT, software version, link icon, battery of this unit (ME) and the child (CHILD), bottom line
`HOLD BUTTON: MENU`. Amber lines under the link text:

- `CHILD RESTARTED` (`X3` = 3 crashes in a row): the child unit restarted by itself. Stays until a person restarts the child.
- `CHILD HAS <version>`: the two units run different software.

### 4.3 The menu (hold on a dark or status screen)

Six items: tap = next, hold = select. Idle for 20 s: the screen goes dark.

| Item | Hold does |
|---|---|
| TEST LIVE | The child streams its microphone for 10 s; screen shows level bar and packet count, then AUDIO OK or NO AUDIO for 8 s, back to the menu. Any press during the test: back to the menu |
| TEST ALARM | Bell screen and 3 beeps for 4 s (any press: dark) |
| VOLUME n | n = 1..5 and back to 1; a beep at the new level; stays in the menu; remembered |
| MIC n | n = 1..5 = the child unit's sensitivity (1 = least, 5 = most), sent to the child, remembered there |
| ROLE | opens the role list (4.4) |
| EXIT | dark |

### 4.4 ROLE (also in the play menu and the start-up chooser)

1. **List**: MASTER, SLAVE, PLAY, BACK. The cursor starts on the current role. Tap = next, hold = choose.
   Choosing the current role or BACK goes back (to the menu; at start-up: carries on starting).
2. **Confirmation** `SWITCH TO <role> / THE UNIT RESTARTS`: **hold = YES**, **tap = NO** (back to the list).
3. YES: only the `role` key of `config.json` is changed (old file kept as `config.json.bak`), the screen says
   RESTARTING, the unit restarts and shows its start-up screen with one beep.
4. If the file cannot be written: NOT SAVED for 4 s, then back, nothing changed.

## 5. Start-up (every role)

Order: **CONFIG, AUDIO, NETWORK, READY**, each ticking green on the start-up screen (NETWORK shows SEARCHING in amber
while a parent unit has not joined the WiFi yet; it does not wait). Then READY stays 4 s, and the parent unit goes on to
its status screen.

| Start | Parent unit / play / loopback | Child unit |
|---|---|---|
| Power switched on by a person | screen + one beep | screen + one beep |
| Automatic restart | screen, **no** beep | **dark, no beep, no waiting for the button** |
| Crash loop (3 in a row, each run under a minute) | **role chooser** (title CRASHES) | **dark**, serial output only |

**Role chooser at start-up**: while READY is shown, for about 3 s the screen says `HOLD BUTTON 2 S: CHOOSE ROLE`.
Hold the button for at least 2 s, then let go: the role list of 4.4 opens. It runs before any
role code starts, so a role that crashes at start can still be switched. If nobody presses anything for 2 minutes the unit
starts with its current role.

Settings in `config.json` under `ui`: `boot_screen` (`auto` | `always` | `never`), `boot_beep`, `ready_s`,
`chooser_window_s` (0 = no chooser at start-up), `chooser_hold_s`, `chooser_timeout_s`, `crash_limit` (0 = never).

## 6. Play mode (role `play`, one board, no network)

| What | Screen | Sound |
|---|---|---|
| Listening | green ring, SPEAK, clip count | none |
| A clip was recorded | blue disc, LISTEN, clip count | the clip, played back |
| 2 minutes without a sound | dark (burn-in protection) | none |
| Tap on the dark screen | SPEAK again | none |

Nothing is ever drawn while a clip is being recorded. A press during a recording is ignored.

**Hold while idle** opens the play menu (the microphone is closed while it is open; 20 s idle closes it):

| Item | Hold does |
|---|---|
| VOLUME n | 1..5 and back to 1; beep; remembered |
| SPEED x | 0.75 (deep), 1.0 (as spoken), 1.4 (chipmunk); remembered |
| ROLE | role list (4.4) |
| EXIT | back to listening |

## 7. Times at a glance

| What | Time |
|---|---|
| Hold threshold | 1.2 s (2 s for the start-up chooser) |
| Status screen | 10 s |
| Menu, list, confirmation idle timeout | 20 s |
| TEST ALARM | 4 s; TEST LIVE 10 s + result 8 s |
| NOT SAVED | 4 s |
| Bell after the sound ended | 10 s |
| Link considered lost | 3 s without a packet; beeps every 10 s |
| Stream cut / pause | after 45 s / 8 s |
| Quick taps for sound off / on | 3, at most 1.2 s apart |
| Start-up screen "ready" | 4 s; chooser window 3 s; chooser idle 2 min |
| Play screen off | 2 min |
| A run that counts as stable (ends a crash loop) | 1 min |

## 8. For the touch screen (step 5)

Where one button forces compromises today:

- Tap/hold means different things in each screen (section 2). With touch, each screen shows its own buttons.
- Hold-to-select and hold-to-confirm exist only because there is one button. Touch can use real buttons and a confirm dialog.
- The child unit's "no menu" rule is deliberate (a toddler). It must survive touch: a touch on the child unit should at
  most show the status, and anything that changes settings needs a deliberate gesture.
- The role chooser at start-up (hold 2 s) can become a "CHOOSE ROLE" button on the start-up screen.
- Keep the BOOT button as a fallback: it is the only input that works with a dead touch controller, and the start-up
  chooser must stay reachable without touch.
