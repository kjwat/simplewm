Interactive resize validation, 2026-10-23
=========================================

The baseline was commit `ea715bb1994d11e3c0ba46280fdefc1416342609`.
Before production edits, the existing motion regression passed and a private
Wayland fixture reproduced duplicate pending requests and missed reversals.
The original sources and binary were preserved outside the checkout. The
comparisons below replayed that source snapshot and the modified source with
the same resize trajectories. The installed/running compositor was not replaced.

After validation, the tested binary was installed at `/usr/local/bin/simplewm`
at the user's request. The previous binary is saved as
`/usr/local/bin/simplewm.pre-resize-ea715bb1994d`. The existing session continues
using the previous binary until logout and login.

Retained changes
----------------

- Compare new sizes with wlroots' scheduled request, rather than the client's
  previously committed configure. Preserve an outstanding serial when the
  target is unchanged, and send reversals even when they return to the current
  buffer's size. Retire the serial before processing a matching or later
  surface commit; acknowledgement alone does not complete it. Serial ordering
  uses wraparound-safe subtraction.
- Use wlroots' existing idle configure batching to replace unsent targets with
  the latest size, including reversals. Eliminate duplicate size requests from
  intervening surface commits. No additional frame, acknowledgement, buffer,
  or timer wait is retained.
- During native interactive resizing, present borders and clipping at the
  committed xdg window geometry while retaining the newest requested size.
  Continue this coordination through release and the final pending commit,
  including clients that choose cell-sized buffers. Track this per window so
  late commits cannot interfere with another window's grab. Clear the state
  on unmap and when returning to tiled/maximized/fullscreen geometry.

These changes improve correctness and visual coherence. They do not make a
slow client draw sooner: its outer edge now advances with its committed
contents. No scaling, animation, dependency, system setting, or output frame
scheduling change is used. Xwayland's resize path and the existing tiled
pending-resize rendering policy are unchanged.

Measurements
------------

Ryzen 7 7730U / AMD integrated graphics; wlroots 0.18.2; Wayland 1.23.1;
GTK 3.24.49; VTE 0.80.1; Mesa 25.0.7. Timing comparisons used GLES2 and a
private 1920x1200 headless output configured at 60000 mHz. Presentation events
are virtual, not measurements of the physical panel. Pixman was also used
for functional and sanitizer checks. No packages were installed.

Each trajectory sends 400 pointer targets at nominal 1 ms intervals, repeatedly
reverses direction, then releases at a final target. Controlled clients delay
acknowledgement/buffer submission by 0, 8, or 50 ms, retaining an already-started
redraw and choosing the newest subsequent request. Three runs per version gave:

| Controlled client | Configures before / after | Duplicate sizes before / after | Border/buffer mismatch presentations before / after | Final settle, ms, before / after |
| --- | --- | --- | --- | --- |
| No artificial delay | 744–747 / 400 | 344–347 / 0 | 22–23 / 0 | 1–2 / 1–2 |
| 8 ms delay | 442–444 / 400 | 46–48 / 0 | 25–26 / 0 | 17–20 / 14–19 |
| 50 ms delay | 408 / 400 | 10–11 / 0 | 26–27 / 0 | 64–67 / 64 |

Maximum received-but-uncommitted configure counts were 2 / 1, 20–21 / 19,
and 104 / 102–103 respectively. Slow-client backlog remains substantial;
there is no new cross-frame or acknowledgement flow control. Configure counts
demonstrate less redundant protocol traffic, not an FPS or latency speedup.

Real applications used private HOME/runtime directories and a private D-Bus
session, alongside a second native GTK window. Simpleterm rendered 1,000 lines
of generated history; Firefox loaded a local HTML document. Each also completed
a two-window tiled-layout regression. Three runs per version gave:

| Application | Configures before / after | Median committed-target age at virtual presentation, ms, before / after | Final settle, ms, before / after | Mismatch presentations before / after |
| --- | --- | --- | --- | --- |
| GTK TextView | 425 / 400 | 17 / 16 | 7–9 / 6–7 | 26 / 0 |
| Simpleterm | 425 / 400 | 17 / 16 | 8–10 / 8 | 26 / 0 |
| Firefox, interleaved recheck | 416–424 / 400 | 16–17 / 16–23 | 18–33 / 22–30 | 25–27 / 0 |

Firefox's recheck alternated baseline and changed builds and required both
the final configure and actual window geometry to settle. An earlier three-run
series gave final settle times of 7–19 ms before and 21–26 ms after, with target
ages of 16–20 ms before and 16 ms after. Some Firefox timing samples are worse;
these short, variable runs do not establish a latency improvement or rule out
a remaining application-specific timing regression. They are retained in the
raw results rather than presented as a speedup. The geometry changes are
justified by eliminating the reproducible border/buffer mismatch.

Target age associates a committed configure serial with its pointer target,
sampled during the headless presentation callback. A mismatch compares all
four border sizes/positions against committed xdg window geometry. A separate
hit-test checks that a pending shrink does not prematurely clip old contents.
These are compositor-state checks, not camera or pixel-response measurements.
Millisecond timing resolution, startup/scheduling variation, short trajectories,
and small sample counts limit the timing results. Physical input-to-photon
latency, DRM scanout timing, CPU/GPU time saved, and subjective smoothness on
the active desktop could not be established with these tests.

Coalescing experiments left out
------------------------------

A hard per-output-frame / wait-for-buffer coalescer increased GTK's median
target age from 18 to 32 ms in an initial 1280x720 headless test. Deferring
frame callbacks did not remove that delay. Both changes were removed.
An acknowledgement-gated version reduced slow-client configure traffic much
further, but Firefox target ages reached 22 and 29 ms in subsequent runs,
with longer final-settle samples. It provided no consistently safe latency
benefit across applications and was also removed. The retained implementation
adds no waiting policy or pacing heuristic.

Checks completed
----------------

- `make all`, configuration validation (22 cases), the existing motion
  regression, and the full private session regression passed. Session coverage
  includes native/Xwayland windows, focus, workspaces, maximize/restore,
  fullscreen, reload, screenshots, and locking.
- `make check-resize` passed pending/unsent reversals, serial preservation,
  acknowledgement without commit, stale commits, final release, minimum sizes,
  completely stalled clients, progress of another client, independent pending
  resizes, cell-sized buffers, tiled/floating transitions, a slow tiled client,
  unmap/remap, and destruction during resize.
- AddressSanitizer and UndefinedBehaviorSanitizer passed the controlled
  cases. Leak detection was disabled. GCC's instrumentation-only warning in
  the unchanged `util.c` formatting wrapper remains visible but is not fatal
  in this test build; all sanitizer checks remain enabled.
- GLES2 controlled and real-application cases passed. The private Xwayland GTK
  case passed floating resize and tiled-layout checks. Its asynchronous
  border/buffer mismatches remain; that path was not optimized. The
  Pixman-backed Xwayland session fell back to software rendering, so it
  supplies no hardware Xwayland performance conclusion.

Reproduction
------------

The standard test needs the project's existing development dependencies,
including wayland-client. Optional application cases use already-installed
GTK/Python GI, Simpleterm, Firefox, and Xwayland. No dependency is installed by
the test. Window/input activity remains in a private compositor.

```sh
make check-resize
python3 tests/resize-check.py --renderer gles2
python3 tests/resize-check.py --sanitize
python3 tests/resize-check.py --renderer gles2 --application gtk
python3 tests/resize-check.py --renderer gles2 --application simpleterm
python3 tests/resize-check.py --renderer gles2 --application firefox
python3 tests/resize-check.py --application x11
```

To replay the baseline with the same fixture:

```sh
resize_baseline_dir="$(mktemp -d)"
git archive ea715bb1994d | tar -x -C "$resize_baseline_dir"
make -C "$resize_baseline_dir" WLROOTS_PKG=wlroots-0.18 all
python3 tests/resize-check.py --source "$resize_baseline_dir" --measure --renderer gles2
```

`--measure` records old behavior without asserting the fixes. `--output PATH`
writes measurements and the run log as JSON. This audit's raw results,
source/binary checksums, and comparison summary are in
`build/resize-measurements/`; build artifacts are not version-controlled.

Update delivery, 2026-10-23
---------------------------

The resize fixes use the ordinary SimpleWM source rebuild and staged installer.
The stock SimpleOS 1.0 installation records its original compositor as a local
source digest, which previous updater releases preserve. Updater 8 recognizes
that exact snapshot only after hashing the installed source and confirming that
the fetched release descends from the published successor `ea715bb1994d`.
An edited, missing, linked or unrecognized local snapshot remains protected,
as does an older or divergent published history. See `updater/README.md` for
the recorded image fingerprint and release procedure.

Release checks passed the resize fixture, 22 configuration cases, and the
updater logic, ordinary transaction, migration, target, bootstrap, durable
recovery, seed and shipped-bootstrap handoff suites. The logic checks cover
35 decisions/failures, including the original ISO snapshot, modified/unknown
sources, missing snapshots/ancestors, symlinks and branch ancestry. Ordinary
checks verify that the ISO-style local manifest advances to a published SHA,
unchanged repeats skip builds, and rollback restores the original manifest.
The motion fixture's slurp selection assertion failed once with checks running
concurrently; its standalone rerun passed. No change to that fixture was made.

Pixel sampling, 2026-10-24
--------------------------

Surface buffers now use nearest sampling when an aligned source pixel maps
exactly to one physical output pixel on every intersecting output. Actual
scaling, fractional source crops, transformed buffers and mixed output scales
retain bilinear filtering. Surface commits, independently updating subsurfaces
and output changes refresh the selection; scene-node destruction releases its
listeners. Configure tracking, resize synchronization, borders and clipping
retain their existing behavior.

The user tested the installed trial on the physical desktop and reported a
clear improvement in appearance. Both the preceding build and trial preserve
the controlled checkerboard exactly, so that fixture does not identify the
original cause of the reported softening.

Release checks passed `make all`, 22 configuration cases, the complete GLES2
visual and resize fixtures, ordinary updater transactions and the shipped
bootstrap handoff. Sampling coverage includes integer and fractional output
scales, source crops, transformed buffers, independent subsurfaces and windows
spanning different output scales. Resize trajectories retain 400 configures,
zero duplicate requests and zero native border/buffer mismatch presentations.
The staged compositor matches the user-tested trial byte for byte, and its
updater 8 seed passes payload verification.

Plain `simpleupdate` fetches the official repository's default branch for
compositor sources. Publishing this change on `main` delivers it through the
existing updater 8 engine; its separately versioned payload is unchanged.
