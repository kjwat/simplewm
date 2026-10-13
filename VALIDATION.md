# SimpleOS 0.8 verification

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
