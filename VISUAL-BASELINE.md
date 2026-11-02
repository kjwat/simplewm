# Full ea715bb rollback

The 2026-11-02 rollback restores the complete WM source tree from
`ea715bb1994d11e3c0ba46280fdefc1416342609`, including simplewm.c, client.h,
Makefile, default config, session helpers, and compositor tests.
The later workspace-key handoff, 104-DPI Xwayland wrapper, visual renovation,
and 50 ms resize-wait experiment are removed.

The only retained post-baseline implementation files are SimpleUpdate's
scripts/simpleupdate, updater/ordinary.py, and updater/release.json.
The associated updater tests and documentation are retained as well.
Updater release 9 remains byte-for-byte valid; reverting its metadata to
release 7 would be rejected by machines that have already verified release 9.
No renderer, resize, input, sampling, geometry, or DPI exception is retained.

This is a forward upstream rollback commit so normal SimpleUpdate can install
it from the previously published release. Installed provenance uses the new
published commit SHA, rather than a local pin or an invented version string.
The performance login override is disabled. Installation does not restart the
running compositor; the restored binary takes effect at the next normal login.

## Verification

- Build and the original ea715bb private native/Xwayland session checks passed.
- The original pointer/motion/resize and Slurp checks passed.
- Updater decision/recovery, ordinary installation, and bootstrap checks passed.
- Every implementation file outside the retained SimpleUpdate payload exactly
  matches ea715bb; updater release 9 payload metadata remains unchanged.
