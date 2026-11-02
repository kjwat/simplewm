# CURRENT HANDOFF — resize-wait fix applied for next login

Updated 2026-11-02T15:46:59.296421-05:00. Read this section first; history follows.

## Status

**Applied, awaiting the user's normal logout/login.** The live compositor is still original PID 1355. User explicitly said to find/apply the fix and stop the diagnostic-only process. Do not switch them to the older diagnostic-only launcher. Do not kill their session or open applications.

- Main source: `/home/keelan/simplewm/simplewm.c`, 50 ms per-monitor pending-resize deadline. Ordinary waits below the deadline retain baseline behavior. A timer wakes the output even without further client commits. New serials do not extend an ongoing deadline. Timer is removed on output destruction.
- Active-at-next-login executable: `/home/keelan/backups/simplewm-performance-20261102-153216/bin/simplewm` (uninstrumented). Main build is byte-identical to this executable. Its compiled .text matches the tested isolated candidate.
- User startup: `/home/keelan/.profile` now sources `/home/keelan/backups/simplewm-performance-20261102-153216/login-fix.sh`; it preserves the original tty1/SSH/rescue-console gating and selects `bin/session-fix`. That wrapper is the original session launcher with only the executable and log location changed. It preserves GDK_DPI_SCALE=1.083333 and the 104-DPI Xwayland launcher.
- System `/usr/local/bin/simplewm`, system launcher, font/config/display settings and libraries remain untouched. No root access required; sudo was unavailable. No default diagnostics/log buffering in the deployed binary. Normal session logs go to `~/.local/state/simplewm-performance/`.
- Main repository has uncommitted changes to simplewm.c, AGENTS.md and VISUAL-BASELINE.md, plus this untracked handoff. No push/commit performed.

## Evidence

- Three unchanged GLES2 runs: induced maximum presentation gaps **263.28, 261.77, 508.10 ms**. Three candidate runs: **66.89, 66.68, 67.25 ms**. Withheld-to-render maxima about **50.37, 50.37, 50.86 ms**. Ordinary resize presentation p95 remains **21.4–21.8 ms** in both. These are deliberate slow-client tests, not measured user latency. Raw traces have zero dropped records.
- AMD hardware GLES2 identity confirmed in `results/gles-independent/session.log`: Radeon Graphics / radeonsi / renoir. An amdgpu permission warning occurs, but the renderer explicitly identifies AMD, not llvmpipe. Headless presentation is not physical scanout.
- Zero changed pixels in entire 1920x1200 screenshots at native, resized and mixed native/Xwayland checkpoints, including regular/bold/italic Pango text. Same geometry and session GDK DPI factor. `results/candidate-pixels.json`.
- `tests/session-check.py`: PASS on candidate (native/Xwayland, input, workspaces, layouts, clipboard, reload, lock). `tests/motion-check.py`: PASS on candidate (real move/resize, pointer constraints, focus, Slurp).
- No-commit/continuous-reconfigure test: timer renders after **50.03 ms**, with **zero surface commits** and **10 new configures** during the wait. Clean exit while a new timer is armed also passed. `results/candidate-deadline-final/deadline-check.json`.
- Final protected-settings hashes and original live/system binary match the saved baseline. `git diff --check` passed.

## Rollback — when the user says “just roll it back”

Run `/home/keelan/backups/simplewm-performance-20261102-153216/rollback`. `--check` is read-only. This disables both experiment launchers, restores the original profile/source/local build when still experiment-owned, and restores the experiment documentation. It preserves unrelated edits and never kills open apps. If candidate is running, user must log out normally once to return to baseline. If still on original PID 1355, rollback needs no logout.

Original profile: `baseline/profile.before`; original main source: `baseline/simplewm.c.before`; original build: `baseline/config/home/keelan/.config/simplewm/build/simplewm`. Running and installed original executable copies are separate. `candidate.patch` and `applied-files.json` identify exactly what this task changed. Do not restore fonts/libraries/settings that this task did not modify. Preserve archive and this log after rollback.

## Next worker

1. Check `/proc/<simplewm PID>/exe` to see whether candidate is active; don't assume logout happened.
2. Ask for no new approvals for this already-authorized fix/rollback. User should judge normal reading/moving/resizing. If dissatisfied, execute rollback promptly rather than defending benchmark results.
3. Do not claim all sluggishness is cured: the confirmed fix addresses monitor-wide pending-resize waiting. Intermediate resize states can be shown sooner even though the pixel-producing paths are unchanged. Physical comfort remains a user check.

## Historical work log

# SimpleWM performance investigation handoff

Started 2026-11-02T15:32:18.076054-05:00.

## User intent and non-negotiable boundary

Improve responsiveness only if the preferred text appearance is preserved. User authorized the diagnostic-first plan and wants to say **just roll it back**. Also explicitly requested this handoff log. No renderer, font, DPI, scaling, sampling, blending, colour, scanout, library, geometry or clipping changes. Do not resurrect the rejected renovation. Read AGENTS.md and VISUAL-BASELINE.md before work.

## Initial state

- Main checkout: /home/keelan/simplewm at ff0577110310ba899b91da5d309e1a2c68ad678e, initially clean.
- Protected snapshot: /home/keelan/backups/simplewm-performance-20261102-153216/baseline (private, includes desktop screenshot).
- Running PID 1355; executable and installed binary SHA256: 143862edea5b51755a50aea35df2f92c9d1e60e6d11b82ec6170cbdc0bc3e601. They MATCH now. The pasted earlier report about PID 1294 and a replaced binary is stale.
- Running Xwayland now explicitly has -dpi 104. Do not revert to 96 based on the stale report.
- Actual display, Xft resources, font inventory/hashes, library copies/versions, source bundle/archive, relevant configs, process maps and allowlisted session settings are saved. No secrets/environment dump.
- No live compositor, installed file, personal setting, or source behavior changed.

## Investigation sequence

1. Preserve baseline (DONE).
2. Build isolated buffered timing instrumentation; retain resize and rendering behavior.
3. Measure resize requests/acks/commits, skipped monitor draws, input, render and presentation. Separate synthetic mechanism tests from evidence about real user stalls.
4. Only select a narrowly justified candidate after measurement. No unconditional bypass or timeout patch based just on suspicion.
5. Compare repeated timings and controlled pixel-identical scenes, native and Xwayland. Software tests do not certify GPU output or eye comfort.

## Rollback contract

At this point there is nothing to undo in the live desktop. Experiment files will live under /home/keelan/backups/simplewm-performance-20261102-153216. The original running and installed binaries are separately preserved. Do not automatically restore configs/libraries/fonts: they have not been modified. Do not kill/restart the user's session without accounting for open applications. Record every subsequent mutation and its inverse here. Preserve this log and baseline after rollback for traceability.

## Initial next step

Inspect existing headless tests and source; add diagnostic-only hooks in an isolated checkout. Validate overhead and obtain repeatable stall measurements before any performance edit.

## Work entry: diagnostic checkout

Created detached worktree `../backups/simplewm-performance-20261102-153216/checkout` at ff05771 (absolute path under the snapshot root above). Built and preserved an unmodified baseline executable as `baseline/simplewm.rebuilt`. Added `diagnostics/trace.h`, the exact-match instrumentation script, and diagnostic hooks only in the isolated checkout. No scheduling/pixel operations changed. Diagnostic records use a preallocated 12 MiB buffer and flush only on orderly exit; overflow is counted. `SIMPLEWM_TRACE` must point to a new file. Captures no key values or window text. Crashes/SIGKILL lose the memory buffer. Diagnostic build completed; validation pending. Main checkout contains only this untracked handoff document.

## Work entry: first measurements and checks

- Diagnostic `tests/motion-check.py`: PASS (private real pointer movement, move/resize, focus and slurp input); `results/motion.log`, `results/motion.csv`.
- Diagnostic `tests/session-check.py`: PASS (native/Xwayland, keys/workspaces, clipboard, configuration reload and lock); `results/session.log`, `results/session.csv`.
- Custom runner and deterministic GTK/Pango scene in `checkout/diagnostics/`. Private headless output 1920x1200 scale 1; no user configuration/services touched. Direct child processes use IPC `exec exec ...` intentionally so waitid does not return ECHILD. Parent relationships saved in each result.
- First Pixman experiment: ordinary resize largest presentation-event gap 23.03 ms; deliberate 250 ms configure callback delay yielded a 513.32 ms maximum presentation gap and 133 skipped redraws over five trials. This is an induced mechanism test, NOT a diagnosis of the live session and NOT a proposed bypass fix.
- GLES2 runs completed but emit amdgpu permission messages; backend identity still needs verification before treating this as hardware validation.
- `diagnostics/analyze.py` writes phase-specific distributions and explicitly distinguishes CPU submit timing, headless presentation, and physical scanout. All first-run trace buffers report zero drops. No performance candidate selected or installed.

## User steering: apply a fix now

User first said ready to save work/switch sessions, then explicitly stopped the diagnostic-only plan: "actually, fuck all this. i kno wwhat fast and slow is. find your fix, apply it, and let's get on with it". Proceed with a narrowly tested fix and rollback; no further permission questions. Preferred text appearance and rollback remain required.

Candidate: 50 ms per-monitor grace period for the already-confirmed resize wait, with a timer scheduling a redraw even if the app never commits. Deadline is not reset by subsequent configure serials while the batch remains pending. When it expires, render the existing scene through the same renderer/geometry/clipping/sampling paths. This allows intermediate old buffers to appear sooner during a slow resize; no scaling or font change. This is a new bounded wait, not restoration of the discarded resize/sampling pipeline.

Current login is tty1 autostart from ~/.profile sourcing /usr/local/share/simplewm/login.sh. No graphical login manager. sudo requires a password, so stage the candidate through the user-owned login profile, preserving the system executable. Backup ~/.profile before changing it; restore its exact original bytes on rollback when still experiment-owned. User will save work and log out normally.
