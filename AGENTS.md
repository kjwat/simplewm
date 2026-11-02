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

## Authorized performance exception (2026-11-02)

The user explicitly requested a tested fix with exact rollback. The new
per-monitor 50 ms resize-wait deadline is authorized: it bounds the existing
monitor-wide wait without changing geometry, clipping, sampling, fonts, or
renderer selection. Keep this narrow scheduling exception separate from the
rejected renovation above. See PERFORMANCE-HANDOFF.md for evidence, deployment
and the user's “just roll it back” instruction.
