# Visual behavior validation, 2026-10-24

The baseline is commit `2cf4a98289564d82e54b47f6e3fa0fc5489dd10c`.
Before compositor edits, the current source was archived and built separately.
The same fixtures run against that snapshot and the changed source. All window,
input and display tests use private runtimes and headless outputs. The installed
compositor and live session were not replaced or restarted during validation.

## Selected changes

- **5 — Fullscreen restoration.** Save the pre-fullscreen geometry only when
  entering fullscreen. Repeated state requests still receive a configure, but
  do not replace the restore geometry. Preserve its size and translate its
  position when moving between monitors. A fullscreen request before initial
  mapping still obtains a valid restore size.
- **6 — Monitor removal.** Move only the removed monitor's clients. Preserve
  floating positions relative to the destination usable area in both axes,
  including vertical and negative-origin layouts. Select an enabled destination
  and preserve fullscreen/maximized restore geometry. Sanitizer testing of an
  offset-monitor transition exposed an existing null-parent access in the
  scene hit-test walk; the walk now stops safely at its root.
- **8 — Stalled tiled clients.** Allow the original tiled-resize coordination
  chance for one output frame callback, then continue scene submission even if
  a client remains pending. Schedule that next callback explicitly. Repeated
  configure requests while stalled do not restart the wait; completing the
  pending batch permits the next independent resize to coordinate again.
  Floating clients retain their exemption. Slow tiled contents may be clipped
  at the requested allocation while other windows continue updating.
- **9 — Application size limits.** Manual floating geometry honors native and
  Xwayland minimum/maximum sizes, including independent axes and fixed sizes.
  Absent maxima remain unbounded; contradictory X11 limits retain the minimum
  within the protocol's dimension range. Tiled, maximized and fullscreen
  allocations remain compositor-controlled. X11 aspect ratios and resize
  increments are not added by this change.
- **17 — Xwayland presentation.** Derive floating borders and clipping from the
  committed surface buffer, rather than XWM's eagerly updated requested size.
  Update presentation on X11 buffer commits without sending another configure.
  Keep X11 configure replies intact, including required same-size synthetic
  ConfigureNotify events. Attach/detach the commit listener with association.
  Native configure serial and acknowledgement handling remains unchanged.

The subsequently reported Super+Page Up/Down problem was also reproduced and
fixed. A focus handoff exposed the consumed page key in `wl_keyboard.enter`'s
held-key list, allowing Xwayland to generate page events inside an application.
Mark shortcut keys consumed before dispatch can change focus, and exclude
consumed or grace-queued keys from that handoff. Ordinary held keys and modifier
state remain available. The existing 30 ms late-Super grace is unchanged.

No animation, renderer switch, dependency, system setting, or resize-request
frame/acknowledgement pacing is introduced.

## Observed results

| Case | Baseline | Changed |
| --- | --- | --- |
| 420x280 floating window, repeated fullscreen request, then restore | Restored to 1280x720 | Restored to 420x280 |
| Fullscreen transfer/restoration and removal of its output | Restore checks failed | Restore checks passed |
| Monitor removal in horizontal, vertical and offset layouts | Incorrect movement or lost relative position | Unrelated window unchanged; transferred geometry preserved |
| Native min/max, independent axes and fixed size | Checks failed | Checks passed; layout allocations preserved |
| Eligible stalled tiled client, about 200 ms private loop | 0 scene submissions and 0 virtual presentations | 13 scene submissions and 13 virtual presentations while the client remained pending |
| Controlled X11 delayed/stale buffers and reversals | Pending/stale borders and clipping diverged | Coherent at every checked stage; no configure feedback |
| X11 GTK application, three alternating before/after runs | 28, 32, 31 mismatch presentations | 0, 0, 0 mismatch presentations |
| Consumed workspace Page Down held across Xwayland focus change | Application received repeated Page Down events | No page press/release leaked for Page Up or Page Down, with Super already held or arriving late |

The three X11 GTK runs had 29/34/32 baseline presentations and 28/33/32 changed
presentations. Their final settle times were 123–158 ms before and 109–163 ms
after. These overlapping, variable samples do not establish a latency speedup.
The private Xwayland server used software fallback, so they supply no hardware
Xwayland performance claim.

Controlled native 400-target trajectories at 0/8/50 ms redraw delays retained
400 configures, zero duplicate sizes and zero mismatch presentations both
before and after. Normal-run final settles were 4/22/77 ms before and 4/18/68 ms
after; these individual samples do not establish lower latency. Simpleterm and
Firefox passed real application resize/reversal and two-window tiled checks.
Firefox timing varied: an alternating recheck had a 16 ms median target age
in both versions and a 12/21 ms final settle before/after. A preceding changed
run under concurrent tests had a 96 ms settle. No Firefox speedup is claimed.

## Checks and reproduction

Passed: normal build; 22 config cases; controlled native GLES2 resizing;
Pixman/GLES2 visual regressions; ASan/UBSan controlled native and visual checks;
real GTK Xwayland resizing with and without sanitizers; Simpleterm/Firefox
application checks; motion and real Slurp; and the native/Xwayland session
regression, also run under ASan/UBSan. The lock suite passed after the focus-key
change. New session coverage holds Page Up/Down across populated-workspace
focus changes and early Super release, including enough time to expose X11
autorepeat, then checks ordinary bare page delivery.

```sh
make -j2 all
make check-visual
python3 tests/visual-check.py --renderer gles2
python3 tests/visual-check.py --sanitize
make check-resize
python3 tests/resize-check.py --renderer gles2
python3 tests/resize-check.py --application x11
python3 tests/resize-check.py --application x11 --sanitize
python3 tests/session-check.py
```

`tests/visual-check.py --source BASELINE --measure` records old behavior without
asserting the fixes. `tests/resize-check.py` supports the same comparison flags.
Both support `--output FILE`. The stalled-client test substitutes only the
child-ownership check so that a socketpair client exercises the eligible gate.
The controlled X11 test substitutes the request transport while using a real
committed wl_surface, and is complemented by real Xwayland application tests.

Raw measurements and logs are retained locally in `build/visual-measurements/`.
Headless presentation events are not physical panel measurements. Physical
input-to-photon latency, real DRM hotplug timing and hardware Xwayland rendering
remain unmeasured. ASan leak detection is disabled; the existing util.c format
warning is tolerated only in sanitizer fixture builds.

## Delivery through simpleupdate

These are ordinary SimpleWM source changes and need no updater engine change.
Published updater 8 already recognizes the exact stock SimpleOS 1.0 WM source
fingerprint, checks its source bytes and requires the fetched revision to
descend from `ea715bb1994d11e3c0ba46280fdefc1416342609`. The installed stock
snapshot matched that fingerprint during validation. Modified or unknown local
source snapshots keep their existing protection.

The updater fetches the current official WM source, rebuilds and stages through
the Makefile, records its Git revision, source snapshot and bundle, checks
startup, and installs through the source transaction with rollback. Tests passed
the 35 source-selection decisions/failures, ordinary installation and rollback,
bootstrap, durable recovery, seed installer and shipped-bootstrap handoff.
The live version-8 release metadata and all immutable payload sizes/hashes were
also verified. A fresh physical ISO boot was not performed.

After publication, use plain `simpleupdate`, or `simpleupdate --wm-only` to
select the compositor. Log out and log back in to activate the installed binary.
Configuration reload does not replace the running executable. The updater
retains the previous installation for `simpleupdate --rollback-sources`.
