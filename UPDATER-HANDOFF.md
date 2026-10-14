# Simpleupdate continuation handoff

Updated 2026-10-14. **Implementation and integration are in progress. Do not
publish or produce the final ISO until critical checks pass.** This file now
supersedes the work-status section in `UPDATER-HANDOFF-SESSION-A.md`, which
preserves the detailed earlier audit and concurrent-edit checkpoint.

## Authorization and boundaries

The user asked this session to pick up the other account's work. ONE final ISO
and reinstall were authorized in the earlier session; the old r3 bridge was
cancelled. Preserve Debian major-release migration implementation, ordering,
configuration, interfaces and protected tests. No subagents. No host APT or live
installation. Make focused commits only after verifying the implementation.

## Inherited state and reconciliation

Repository `/home/keelan/simplewm`; starting HEAD
`3cf0c5cae9cb6734134420d99387f599dfa815e1`, main already ahead of origin by two
commits. No Suite changes are needed. Read Suite AGENTS.md before any change.

Two overlapping architectures were inherited. The `updater/launcher.py`,
`engine.py`, `transaction.py`, release/seed tooling and Makefile path from
session A are the retained architecture. The overwritten ordinary orchestrator
has been reconstructed against those interfaces; the alternative's headless
startup-check idea was retained and strengthened to query real compositor IPC.
The alternate launcher/public key were moved out of the checkout, not discarded.
All inherited files were backed up first:
`/home/keelan/.cache/simplewm-update-audit/resume-20261014/inherited-work.tar.gz`.

Changes in this continuation:
- Actual ordinary source planning, minimum-updater checks, package download phase,
  root/nobody build-worker handoff, grouped Suite/WM install and persistent phases.
- Stable launcher cannot be replaced by ordinary WM payloads.
- Root captures build output before inspecting/installing it.
- Offline source recovery precedes bootstrap network requests; explicit rollback
  is offline. APT interruption records require dpkg repair, not fictitious rollback.
- Two-way readiness/activation handshake; engine waits for durable activation.
- Ownership/mode checks, version-directory identity, pinned seed fallback,
  offline diagnostic fallback, version-reuse rejection, process-group cleanup.
- Explicit seed installer umask after real integration exposed inherited 002.
- New ordinary orchestration, actual signed seed/engine and privileged installed
  integration tests. Migration code/helper/tests are unchanged except the
  original session A ordinary callback/optional flags/default-false QUIET hook.

## Verification so far

Passing: `update-bootstrap-check.py`, `update-durable-check.py`,
`update-ordinary-check.py`, `update-seed-check.py`; unchanged
`update-release-check.py`, `update-target-check.py`, `update-check.py`,
`update-logic-check.py`, `update-plain-check.py`. Python compilation passed.

Unit/fixture evidence is explicitly distinguished from real root/nobody proof.
`update-installed-check.py` uses an ephemeral signed HTTPS fixture, real Git
history, signed seed installation through Makefile, real WM/dependency builds,
plain invocation/repeat and offline retained rollback inside bwrap. Full APT
upgrade is simulated; dependency installation is real inside the copied root.
Administrator authentication via pkexec succeeded. No host APT/install.

Real attempts:
- installed-test-1: fixture seed overlay failed on existing symlinks; fixed.
- installed-test-2: launcher rejected seed directory mode 775; installer now
  sets umask 022. No component updates had begun.
- installed-test-3/4: fixed test HTTPS path and repository identity fixtures.
- installed-test-5/6: real WM builds completed; private namespace lacked /dev/shm
  for headless buffers. Added private shm. Startup probe now waits for outputs.
- installed-test-7: PASSED all root/nobody checks, future signed updater handoff,
  real WM build/startup, repeat, retained rollback, rejected replacement fallback,
  interrupted activation, bad signature and offline interrupted source recovery.
  Evidence: `installed-test-7/output/result.json`.
- installed-test-8: added real Suite build and image finalizer; cached environment
  lacked Suite headers. Fixture now installs declared build dependencies first
  and uses the same detached source checkout as ordinary planning.
- installed-test-9: PASSED. Includes real Suite seed build, actual image
  ownership finalization and grouped Suite/WM --rebuild before all recovery cases.
  Evidence: `installed-test-9/output/result.json`; this supersedes test-7.

Implementation committed as `e0f47c9`. Production release 1 was signed from
that exact commit and its installed seed initialized successfully. Metadata
commit/publication and final ISO are next.
Production signing key generated at
`/home/keelan/.local/share/simpleupdate-signing/release-private.pem` (0600,
parent 0700). Never print/copy it into artifacts. Public key is
`updater/release-key.pem`, SHA256
`7a354e11e7f6bb6e3b7cc2f99fae8ce26e94c56b59360aed5a0ce62e89ef139b`.
New `image/seed-updater.py` verifies signed seed plus explicit Suite/WM staging
files, rejects missing provenance and update state, and normalizes image root
ownership. README, updater/README and image/README now document the architecture. The installer still needs production release
metadata before ordinary `make install` from this checkout can succeed.

## Remaining work

Critical integration and documentation now pass. Commit verified implementation,
then generate
signed metadata from the committed revision and verify production seed staging.
Complete image validation and final ISO only after critical tests pass, using the
real payload/install path. Do not ship an image whose published authenticated
updater endpoint is missing. Do not silently publish code without resolving the
release step. Record all limits, especially full APT upgrade simulation and
hardware/next-login behavior not established by headless startup.

## Cached environments

- Original ISO/source archives: `/home/keelan/0.8/`.
- Original extracted ISO: `/home/keelan/.cache/simplewm-update-audit/r3-root`.
- Real previous test with cached dependencies:
  `/home/keelan/.cache/simplewm-update-audit/runtime-test-5/rootfs` (root-owned).
- New integration copies: `installed-test-N` below the same audit directory.
- Local WM headers/toolchain: `/home/keelan/.cache/simplewm-lock-build/env.sh`.
- `sudo -n` needs authentication; `pkexec` works with desktop authentication.
- `rg` is unavailable in exec_command; use grep/find.
- Never print private keys or credentials. Test transport keys stay in the
  disposable audit directory and must never enter release artifacts.

## Release checkpoint

`e0f47c9` implementation and `38f6e49` signed release 1 were published to
origin/main after the passing installed-test-9 gate. Live official HTTPS metadata
and every immutable payload file verified against the production public key.
Review found isolated Python ignores PYTHONDONTWRITEBYTECODE: engine now sets
`sys.dont_write_bytecode` explicitly, with an actual installed-diagnostic cache
regression assertion. This small fix will be signed as release 2. Final ISO
still has not been built. Plan to also demonstrate real public release 1 -> 2
delivery in an isolated image copy, in addition to the comprehensive fixtures.
