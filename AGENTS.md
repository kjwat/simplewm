# Exact ea715bb compositor baseline

The user explicitly requested a full rollback to
`ea715bb1994d11e3c0ba46280fdefc1416342609` on 2026-11-02, discarding
subsequent local changes and making the rollback the upstream baseline.
Keep simplewm.c, client.h, config, session helpers, rendering, geometry,
clipping, resizing, sampling, and Xwayland startup exactly at that commit.
Do not reintroduce the post-baseline workspace-key handoff, 104-DPI Xwayland
launcher, or 50 ms resize-wait experiment without a new user request.

SimpleUpdate version 9 and its rollback/unpin logic are retained so published
updater metadata does not downgrade. Publish WM rollback releases as forward
commits and record their published commit SHA in the installed manifest;
this baseline must remain eligible for ordinary upstream updates.

This is the Linux SimpleWM repository. Keep FreeBSD port changes in their
separate repository. See VISUAL-BASELINE.md for rollback scope.
