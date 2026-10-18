# Native touchpad gestures verification — 2026-10-18

- Built against installed wlroots 0.18.2 with all compiler warnings treated as
  errors, including the lock client.
- `make check-gestures` exercises the eight real compositor cursor listeners and
  checks every wlroots gesture send argument: timestamps near uint32 wrap,
  fingers, signed movement, absolute pinch scale, signed rotation and both
  normal/cancelled ends. Cursor position is unchanged. The optional real
  `wayland-info` check confirms `zwp_pointer_gestures_v1` version 3 in a headless
  SimpleWM session. Send functions are intercepted for payload assertions;
  this does not simulate libinput hardware or a browser.
- All 22 configuration checks and the existing native Wayland/Xwayland session
  regression passed, including keyboard shortcuts, focus, clipboard, reload,
  screenshots and session lock. Corrected its stale font expectation from 13
  to the already shipped 12; no font configuration changed.
- Existing updater containment/rollback, logic, ordinary orchestration, shipped
  bootstrap handoff and seed validation checks passed. The real updater build
  and Makefile installation successfully staged the compositor, documentation
  and source snapshot in a temporary prefix, with runtime linkage verified.
- No new dependency, updater release or migration is required. Existing ISOs
  receive the compositor through the normal source update after publication;
  a new login starts the updated binary. No remote publication or host install
  was performed during these checks.
- Physical libinput touchpad gestures and Firefox pinch-to-zoom remain manual
  hardware acceptance checks. See README.md for protocol and Firefox tracing
  instructions.

# SimpleOS 0.8 verification

Font defaults verified on 2026-10-15:

- The normal Makefile installation stages all four unmodified Ubuntu 1.006
  variable font files, their recorded SHA-256 checksums and Ubuntu Font Licence.
- Real Fontconfig matching selects the staged files for regular, bold, italic
  and bold italic despite newer Ubuntu fonts on the host. Unrelated families
  remain available; slight hinting and RGB antialiasing are retained.
- Real GTK/VTE measurements at 104 DPI give 10 by 22 pixel character cells for
  Ubuntu Sans Mono 12 at normal zoom, matching the approved 13-point test at
  zoom 96/104. Simpleterm requires no application changes.
- The C build, 22 configuration cases, theme/font checks, image defaults,
  offline setup and existing ordinary-update/seed checks pass. Setup checks
  include adopting the old stock 13-point size once, keeping its backup and
  preserving custom or later intentional font choices.

Historical signed-bootstrap verification on 2026-10-14 (0.8-r4):

Custom release signing has since been removed. Versioned delivery, activation
and recovery remain; signature-specific fixtures/assertions were removed from
the existing tests. The r5 build report records the focused replacement checks.

- The stable launcher, signed/versioned engine and grouped ordinary-source
  transaction are exercised by `update-bootstrap-check.py`,
  `update-durable-check.py`, `update-ordinary-check.py` and `update-seed-check.py`.
  Real signatures, real child processes, durable file replacement, abrupt process
  exits during install and recovery, failed-build grouping, ownership preservation,
  minimum-updater requirements and activation acknowledgement all pass.
- `update-installed-check.py` passed in a disposable copy of the cached r3
  userspace. Seed installation uses the actual Makefile. A real signed future
  updater is downloaded as UID/GID 65534, activated, and handles the same plain
  request. WM compilation/staging runs as nobody, APT dependencies install as
  root, and real headless compositor IPC confirms an initialized output.
- The installed test also passed unchanged repeat, offline source rollback,
  failed replacement fallback, rejected-version repeat, interrupted activation,
  corrupted signature refusal and interrupted source recovery before a failing
  network request. Personal configuration, manuscripts and unknown tools survive.
  Evidence: `/home/keelan/.cache/simplewm-update-audit/installed-test-9/output/result.json`.
- HTTPS/Git transport use isolated fixtures for unpublished code. The test TLS
  certificate is trusted only inside the copied rootfs. Full Debian/Liquorix
  upgrade is simulated; package dependencies, Git history, compilation and
  installation are real. This is not a VM boot/Calamares/hardware-login test.
- Existing updater, release and target checks pass unchanged. Every original
  Python function except the ordinary dispatch/output hooks is AST-identical
  to the baseline; the target helper, dependency metadata and migration tests
  are unmodified. No host APT or live-system installation was performed.
- The expanded installed run also passed real Suite compilation (including
  Simpleterm), grouped Suite/WM rebuild, and image seed finalization over 485
  explicitly packaged paths. It verified root ownership and the production
  image inventory tool. Final ISO artifacts and their checksums are recorded
  separately in the release build report.

Reproduction requires root, Python 3, OpenSSL, Git and Bubblewrap. The test uses
local HTTPS port 443 and writes only a newly created work directory:

```sh
sudo python3 tests/update-installed-check.py \
  --rootfs /path/to/cached-iso-test-root \
  --work-dir /path/to/new-disposable-test
```

The following r3 self-replacement evidence predates the new bootstrap and does
not validate its protocol or claim an in-flight handoff from the old updater.

Updater self-replacement verification on 2026-10-14:

- The original `simpleos-0.8-r3-amd64.iso` matches its recorded SHA-256:
  `11532a030dbe37581fd30ce77faec2a67bc6daa12419296b996f1f3b7622800a`.
  Its extracted updater is byte-identical to SimpleWM revision
  `4793cbca276a6a5e1155911eb153250083b7e661`; updater SHA-256 is
  `30efd2a1e729d2c5ad3aecb6cc2d702324ebc0edea0facf097e9d49227519d5f`.
- `tests/update-iso-check.py` runs that untouched executable with no arguments
  in a disposable copy of the ISO filesystem. Its manifests, source bundles,
  package database and original development packages are preserved. Bubblewrap
  provides private mount/PID/IPC/UTS namespaces and minimal root capabilities;
  Git, compilation and staging actually run as UID/GID 65534 (`nobody`).
- The first run installs the newly declared dependencies, including previously
  absent `libcairo2-dev`, builds SimpleWM revision
  `48ca08c4ff1418fe8db2931d72ac8ac17e3621c4`, and transactionally installs the
  new updater, its sibling target helper, and the native locker. The updater
  SHA-256 becomes
  `9154d62621ba79893d587534c252224a00e33c16c9f1f35c78c3e651dd00f5d9`.
  The second ordinary invocation executes that replacement and skips unchanged
  Suite/WM builds. Both invocations exit successfully; runtime linkage, personal
  configuration/document preservation and transaction cleanup are checked.
- Signed APT index refresh and dependency installation, source object/ancestry
  checks, strict compilation, configuration validation, source bundling and
  installation are real. Official Git origin configuration stays intact; a
  test-only command shim substitutes local HTTP source transport to exercise an
  unpublished commit. Debian/Liquorix full-upgrade is simulated, and daemon
  startup is disabled in the disposable filesystem. This is an updater test
  using the original ISO userspace, rather than a new VM boot/installation test.
- The fast plain-update regression now covers the archived r2 and r3 scripts
  and today's script, installs the actual replacement updater/helper bytes,
  then reloads the replacement for the next no-argument run. All updater
  transaction, decision, release and target-environment suites pass.

To reproduce after extracting `live/filesystem.squashfs` with `unsquashfs`, run
from this repository (the work directory must not already exist):

```sh
sudo python3 tests/update-iso-check.py \
  --rootfs /path/to/original-r3-rootfs \
  --work-dir /path/to/new-disposable-test \
  --suite-source /path/to/simplesuite
```

The harness copies the extraction before writing anything. Its `output/`
directory retains `first.log`, `repeat.log`, command/credential records and
`result.json`. Host tools required are Python 3, Git and Bubblewrap; signed APT
repositories and the official repository identity check require network access.
The selected WM source is this repository's committed `HEAD`; Suite is pinned
to the revision recorded in the original ISO so its unchanged-build path is
also tested.

Lock-screen source verification on 2026-10-14:

- Strict C build of the compositor and native lock client, with warnings as errors.
- `tests/lock-check.py`: effective appearance and older-compositor fallback,
  contrast on bright/dark/color extremes, private wallpaper-only blur caching,
  renderer on small outputs, first-key and UTF-8 editing/masks, full password
  clearing, ignored input during authentication, and staged runtime linkage.
- Isolated Wayland session with actual virtual-keyboard input, two outputs and
  mixed scales: production lock readiness, repeated idle/suspend requests,
  centered clock/entry, Escape, denied compositor actions while locked, and
  client-crash containment. Rejection and successful UTF-8 unlocking use a
  separately linked test authentication fixture; real passwords are never used.
- The unmodified 0.8-r2 updater validates the actual staged installation.
  Original and current updater regression paths install the new launcher,
  native lock client and target helper through a plain `simpleupdate` transaction.
- Native previews use the current wallpaper/palette and the production drawing
  code. The preview and test authentication fixture are never installed.
- Password input checks also pass AddressSanitizer and UndefinedBehaviorSanitizer
  with leak detection enabled. The full existing configuration, theme, setup,
  image, updater and native/Xwayland desktop regression suites pass.

Source verification on 2026-10-12:

- C build with warnings as errors; config, theme and transaction checks.
- Offline setup from bundled Git history; personal edits and backups preserved;
  source/config paths share the same files and repeat setup is idempotent.
- Real headless Wayland/Xwayland desktop checks, including bounded workspaces
  and GTK xdg-foreign dialogs in separate processes.
- Terminal wallpaper wizard, Fill default, palette generation and rollback.
- Ordinary updates skip developer tests; --verify opts into them.

The corrected 0.8 removes workspace notifications and the GTK wallpaper chooser.
Configuration, theme, offline setup and updater checks were rerun successfully.
The session regression now intercepts notify-send and checks workspace shortcuts
without suppressing notifications. Its rerun could not start a compositor:
the current sandbox prohibits creating local sockets. Simpleterm's real file
monitor passed repeated red/blue palette replacements, font preservation,
invalid-file handling and restoration without a display. GUI session reruns
are subject to that same socket restriction.

The 0.8 VM boot/installation walkthrough was waived by the user to conserve
compute. Image structure and checksums are checked; release results are recorded
beside the final image in RELEASE-NOTES.txt and BUILD-REPORT.md. The older 0.7 findings follow for provenance.

# Validation status

Source checks completed on 2026-10-12 in an isolated Debian 13 build root:

* Release build with compiler warnings treated as errors.
* Configuration validation, includes, variable redefinition, bounds and invalid
  settings.
* Real headless Wayland sessions with native GTK and Xwayland clients: shortcuts,
  balanced layouts, focus, maximize/restore, floating geometry, workspace moves,
  clipboard and primary selection, reload failure, output guards, IPC,
  screenshots and session locking.
* The same session checks under AddressSanitizer and UndefinedBehaviorSanitizer.
  Leak detection was disabled for that run.
* SimpleSuite/SimpleWM updater failure injection: failed build/test containment,
  interrupted installation recovery, partial installation rollback, configuration
  and user data preservation, source snapshots and staged paths.
* Wallpaper palette generation, Unicode/spaced paths, preservation of font
  settings and existing GTK/Firefox configuration, and rollback.
* The official SimpleSuite revision
  `fc7701c15f21ac1aa33db572e46a5ee6ff6de647` passed its full release gate and
  standalone Simpleterm checks, including SimpleSave's optional SimpleWM backup.
* SimpleCheck's real terminal/Git test committed, pushed and pulled the SimpleWM
  folder without changing its peer repositories. The installed host SimpleCheck
  and SimpleSave binaries also passed their integration checks.

The prepared SimpleOS ISO has booted in UEFI and BIOS QEMU virtual machines.
Both live systems passed checks for the Liquorix kernel, canonical installation
paths, fonts, configuration, removal of dwm, and preserved file capabilities.
Signed Debian/Liquorix APT checks and official GitHub update checks passed in the
live VM. A real unprivileged SimpleWM rebuild passed the native/Xwayland session
gate and transactional installation. An earlier session-test timeout left the
working binaries intact; the retry passed with an emulation-tolerant timeout.
An attended Calamares disk installation was started successfully, and its
SimpleWM slideshow rendered correctly.

Disk installation completion, installed-system boot and desktop acceptance,
and checks against the final ISO remain release work.
This source publication does not certify a finished ISO. Physical hardware and
the subjective mouse feel still require validation after installation.
