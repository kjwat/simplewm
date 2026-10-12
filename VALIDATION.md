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
  `1d1c3b8c2bd352611ec3fe686e089ed9b25fa04a` passed its full release gate and
  standalone Simpleterm checks.

The prepared SimpleOS ISO has booted in UEFI and BIOS QEMU virtual machines.
The UEFI live system passed checks for the Liquorix kernel, canonical installation
paths, fonts, configuration, removal of dwm, and preserved file capabilities.
An attended Calamares disk installation was started successfully.

Disk installation completion, installed-system boot and desktop acceptance,
slideshow rendering, and checks against the final ISO remain release work.
This source publication does not certify a finished ISO. Physical hardware and
the subjective mouse feel still require validation after installation.
