# Restored compositor baseline

The user rejected the visual/latency renovation after ea715bb because of
regressions, including font readability. The renovation was still present in
upstream a50eca9 despite the installed system having been rolled back.

The working source now restores simplewm.c and client.h from
`ea715bb1994d11e3c0ba46280fdefc1416342609`, retaining only these changes within
those two files:

- Filter consumed workspace shortcut keys during focus handoff, and mark them
  consumed before dispatch changes focus.
- Select the independent simplewm-xwayland launcher for 104-DPI X11 startup.

No other changes to those two baseline files remain. In particular, the custom
surface-sampling addon/listeners, interactive resize/commit presentation changes,
stalled-client rendering change, and replacement geometry paths are removed.
This deliberately also removes the fullscreen, monitor-removal and size-hint
changes bundled into that renovation. They are not being advertised as retained
fixes. Session resources, fonts, desktop code, configuration parser/defaults,
updater implementation, and the standalone DPI helper are not rolled back.

The renovation-specific resize/visual/sampling fixtures and validation reports
were removed because they assert or endorse the discarded implementation.
Existing session, pointer/motion and DPI tests remain.

## FreeBSD audit

The current Linux WM checkout has no FreeBSD-specific code, and the available
post-ea715bb commits contain no FreeBSD port changes. Recent Scriptorium commit
`af05570` routes FreeBSD installations to a separate native upstream; it does
not modify this WM's compositor. Config, desktop and session helper sources
in this checkout still match ea715bb (apart from the separately added Xwayland
launcher). This audit does not claim to cover other machines or unrecorded work.

## Verification

- `make -j2`: passed against system wlroots 0.18.2.
- `PATH="$PWD/scripts:$PATH" /usr/bin/python3 tests/session-check.py`: passed,
  including native/Xwayland windows, workspace-key isolation, focus, layouts,
  maximize/restore, clipboard, configuration reload and secure lock.
- `make check-motion check-xwayland-dpi`: passed, including real private pointer
  movement/resize and Slurp input checks; default 104-DPI and opt-out 96-DPI
  Xwayland launches retained their resources and Wayland output scale.
- `make DESTDIR=/tmp/simplewm-baseline-stage-jt_97nfc install`: passed. Staged
  compositor bytes match the built executable and include the DPI helper.
- `git diff ea715bb -- simplewm.c client.h`: only the two retained fixes above.

These are isolated build/session checks, not a claim of subjective physical
panel readability validation. No live compositor, personal settings, installed
manifest or updater pin was changed. Git history is preserved; this is a forward
source rollback, not deletion of historical commits. Upstream will retain the
rejected code until this cleanup is committed and published.
