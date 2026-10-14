# Updater session A: implementation checkpoint and concurrent-edit conflict

Updated 2026-10-14 16:13 UTC. **Not complete. Do not publish or build an ISO.**

The user superseded the original r3 compatibility requirement: ONE final ISO
and reinstall are authorized. No legacy bridge is needed. Preserve Debian
major-release migration exactly. Critical updater-first and recovery tests must
pass before producing the final ISO. Maintain a handoff for the other account.

## Concurrent editing detected — resolve before further writes

At approximately 16:12 UTC this session discovered another implementation being
written into the SAME checkout. This session did NOT create:

- `scripts/simpleupdate-launcher` (different bootstrap architecture)
- `updater/trusted-key.pem`
- The current `updater/ordinary.py` beginning with
  `Durable ordinary-update state and source transactions. No Debian migration policy.`

This session had written a DIFFERENT `updater/ordinary.py`, beginning with
`Ordinary maintenance using existing source, build and APT interfaces.` It was
overwritten by the other writer while this session was working. Do not assume
the current files constitute a coherent implementation. In particular this
session's `updater/engine.py` expects `ordinary.run(update, args, log, version)`
and `ordinary.STATE`; inspect compatibility with the other writer's exports.

An async question asks the user which session should own implementation. File
edits are paused to avoid overwriting the other account. This separate handoff
is the only new write after detecting the collision. There are no commits or
pushes by this session. Starting HEAD was
`3cf0c5cae9cb6734134420d99387f599dfa815e1`.

## Files created/changed by this session

- `UPDATER-HANDOFF.md`: initial audit, original-r3 evidence and scope change.
- `updater/launcher.py`: standalone protocol-1 bootstrap; pinned OpenSSL signature,
  fixed raw.githubusercontent.com origin, signed per-file SHA256 and sizes,
  version directories, durable active/previous/pending/rejected state, init probe
  as nobody, readiness pipe, fallback, same-argument handoff, lock retained in
  child, no repeat payload downloads. Testability is via importing and fixtures,
  not production environment overrides.
- `updater/engine.py`: imports signed legacy.py and ordinary.py; readiness/probe
  entry points, unprivileged build worker, calls legacy main with ordinary hook.
- `updater/transaction.py`: ordinary-only durable grouped source transaction,
  complete backups before mutation, fsync of files/directories, idempotent copy
  restoration (never consumes backups), retained previous installation,
  root-owned captured payload using directory FDs/O_NOFOLLOW, known-file
  ownership inventory, preserves modified shared files and unknown files.
- `updater/release.py`: sign committed implementation using an external private
  key. No publication. Requires payload code committed before release metadata.
- `updater/install.py`: verify signed seed before staging launcher and versioned
  files through normal Makefile DESTDIR install.
- `updater/seed-inventory.py`: register ONLY explicit package payloads after
  verifying assembled image bytes match, never adopt all of /usr/local.
- `simpleupdate-requirements.json`: component minimum updater/protocol contract.
- `tests/update-bootstrap-check.py`, `tests/update-durable-check.py`.
- Makefile now installs `updater/launcher.py` through `updater/install.py`, not
  the legacy script as the command. **release-key.pem/release.json/release.sig
  required by this installer DO NOT EXIST YET; make install is not ready.**
- `scripts/simpleupdate`: only ordinary callback, QUIET flag (default false),
  optional ordinary-only CLI flags. Callback executes AFTER existing Debian
  release decision/recovery check and only when neither upgrading nor recovering.
  No migration function, target helper, dependency metadata, or protected test
  was edited. Existing legacy default behavior remains in place when no hook.

## Verified in this session

All passed before concurrent edits were detected:

1. `python3 tests/update-bootstrap-check.py`: real ephemeral RSA signatures,
   actual subprocess handoff, bad signatures/corrupt files refused, broken
   replacement before readiness falls back, rejected version not downloaded
   again, interrupted activation restored, signed metadata rollback rejected.
   Transport and UID dropping are fixtures. NOT root/nobody integration proof.
2. `python3 tests/update-durable-check.py`: real files, injected install failure,
   subprocess os._exit during installation AND during recovery, repeated recovery,
   retained rollback, personal config/manuscript/unknown tool preserved, escaped
   staging link refused. This exercises transaction.py independently.
3. `python3 tests/update-release-check.py`: passed UNCHANGED.
4. `python3 tests/update-target-check.py`: passed UNCHANGED.
5. `python3 tests/update-check.py`: passed UNCHANGED.
6. Python compilation of created modules and legacy script passed at that point.

No real new-ISO installed-payload integration has run. No real ordinary run with
the new orchestrator has run. No signing key was created by this session. No
production signature/metadata was generated. No final ISO has been built.

## Work still needed / known issues in this session's approach

First resolve concurrent architecture ownership; do not blindly combine both
launchers or declare success based on isolated tests.

- Reconcile/restore ordinary orchestration. The overwritten version gathered both
  sources with existing Git/ancestry helpers, checked minimum updater requirements,
  downloaded APT packages first, recorded explicit states, audited interrupted dpkg
  before any retry, built all changed components as nobody through engine's worker,
  froze output as root, excluded bootstrap files from ordinary WM installation,
  installed both component payloads as one recoverable group, verified revisions
  and WM config, recorded reboot/success, retained last source rollback. APT was
  explicitly non-atomic; failures preserved dpkg repair instructions/state.
- Planned but NOT applied: offline source recovery before bootstrap networking;
  currently network failure blocks reaching ordinary recovery. Must fix.
- Planned but NOT applied: private headless compositor startup smoke check after
  compilation, before live replacement. Existing checks only cover config/linkage.
  Next-login hardware-specific failures still require retained rollback.
- `launcher.py` offline diagnostic path currently skips fallback if active payload
  is corrupt. Ordinary active verification restores previous if available.
- Verify exact loaded metadata identifier equals its version directory name.
- Audit launcher file/directory ownership, cancellation and supervisor death,
  malformed metadata, unsupported protocol, space failures and lock contention.
- Complete signing-key custody and release generation, seed Makefile integration,
  image inventory generation for Suite + WM including source snapshots/manifests.
- Real integration must exercise actual signed future updater delivery, actual
  components/builds, failed replacement, interruption, repeat and permissions.
- Update README/image instructions, final limitations and handoff; focused commits
  only after coherent verification. Do not publish partial state.

## Cached environment / avoid needless rebuilds

- `/home/keelan/.cache/simplewm-update-audit/r3-root`: preserved ISO extraction.
- `/home/keelan/.cache/simplewm-update-audit/runtime-test-5/rootfs`: previous real
  test root with cached build dependencies. Root-owned, don't modify blindly.
- Previous evidence: `runtime-test-5/output/result.json` proves the OLD updater's
  path only. It is not evidence for new code.
- `/home/keelan/.cache/simplewm-lock-build/env.sh` supplies local sysroot headers,
  pkg-config paths and LDFLAGS; its debs directory has cached packages.
- `image/prepare-rootfs.py`, `image/repack.py`, `image/README.md` are existing ISO
  process. Inspect/update minimal updater integration; don't reconstruct a VM lab.
- sudo noninteractive fails (password required). `pkexec` exists. Real namespace
  test will need administrator authentication or a correctly mapped existing
  environment. Rootless unshare works but newuidmap/newgidmap are absent; one UID
  mapping is NOT proof of real root/nobody separation.
- `rg` absent; use grep/find. Do not read credentials or private signing keys
  into tool output. No host APT or live system install has been performed.
