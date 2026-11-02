# Compositor baseline and platform boundary

The user rejected the post-ea715bb visual renovation because it regressed the
window system and font readability. Keep rendering, resizing, scene clipping,
and surface sampling on the ea715bb1994d11e3c0ba46280fdefc1416342609 baseline.
Do not restore the discarded interactive-resize presentation pipeline,
SurfaceSampling/tracksampling policy, or its replacement geometry/rendering
paths as an optimization or automatic upstream reconciliation.

The independent workspace-key handoff fix and 104-DPI Xwayland launcher are
intentionally retained. See VISUAL-BASELINE.md for the exact scope and checks.

This is the Linux SimpleWM repository. Do not merge FreeBSD port code or
platform-specific replacements into it. Keep FreeBSD port work in its separate
repository. Neither a source update nor a metadata repair authorizes bringing
the rejected visual renovation back.
