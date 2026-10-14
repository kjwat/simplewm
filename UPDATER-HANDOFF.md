# Simpleupdate continuation handoff

Updated 2026-10-14. **Updater implementation, publication, integration and the
one final 0.8-r4 ISO are complete.** The ISO has not been booted or installed.
The earlier account's `UPDATER-HANDOFF-SESSION-A.md` is preserved as historical
evidence; its incomplete/conflict warnings describe the original checkpoint.

## Final artifacts and published revisions

- ISO: `/home/keelan/0.8/simpleos-0.8-r4-amd64.iso`
- ISO SHA256: `5481094c9494711b2546520f61379e030594207d29129d210ced3a0b9b8afa29`
- Report: `/home/keelan/0.8/BUILD-REPORT-r4.md`
- Provenance: `/home/keelan/0.8/SOURCES-r4.lock`
- Checksums: `/home/keelan/0.8/SHA256SUMS-r4`
- Evidence: `/home/keelan/0.8/verification-r4/`
- Matching Suite/WM source archives are beside the ISO; complete Git bundles and
  source snapshots are installed inside it. The old r3 ISO/docs remain intact.
- Image WM/source revision: `95605d0004976b5232445d177220e0b5530ad02f` (published).
- Image Suite revision: `be4468fcea012a1077be9562157b32892fb6893c` (published; no Suite repo changes).
- Production updater: signed release 2 from `aed7f0150b3423cce5a6df9b44f306f0a16e8e8a`.
- Implementation commit `e0f47c9`; release 1 metadata `38f6e49`; bytecode fix
  `aed7f01`; release 2 metadata `5b7834b`. All published to origin/main.
- The latest source revision at image build time adds the previous handoff docs.
  A later handoff-only revision need not match the immutable image source revision.

## Authorization and boundaries

The user asked to continue the other account's work. ONE final ISO and reinstall
were authorized earlier; the old r3 same-invocation bridge was cancelled.
Preserve Debian major-release migration implementation, ordering, configuration,
interfaces and protected tests. No subagents, host APT or live installation were
used. The critical integration gate passed before publication and final ISO.
Do not start a destructive disk installation without the actual target/context.
No further image build is needed for this completed updater task.

## Reconciled implementation

The retained architecture is `updater/launcher.py`, `engine.py`, `ordinary.py`,
`transaction.py`, release/seed tooling and Makefile integration. It was reconciled
against session A's interfaces after overlapping implementations were discovered.
The other implementation's headless startup idea was retained and strengthened
with actual compositor IPC output readiness.

- Stable bootstrap pins the production public key and fixed official HTTPS origin.
  Signed metadata identifies immutable payload commits plus exact sizes/hashes.
- Downloads/probes and source builds run as real nobody; root captures and checks
  build output. Ordinary WM payloads cannot replace the bootstrap or pinned key.
- Version directories, active/previous/pending/highest/rejected state and a two-way
  readiness gate make activation durable before the ordinary request can proceed.
- Failed candidates fall back to a verified predecessor and are quarantined;
  corrupt signatures, invalid ownership/modes, rollback and version reuse fail.
- Offline interrupted source recovery precedes network access. Grouped source
  transactions preserve complete backups and are safe to recover repeatedly.
  `--rollback-sources` restores the most recent retained source installation.
- Both changed components build before source installation. Personal homes and
  unknown local files are preserved. Modified shared files are not silently adopted.
- Ordinary state records download, verification, staging, installation and recovery
  phases. APT download precedes non-atomic installation; interrupted dpkg state
  receives explicit repair instructions. No APT rollback is claimed.
- Explicit major migration and pending migration recovery retain legacy authority
  and bypass bootstrap download. All 57 original legacy functions other than
  run/main remain identical; target helper, dependency contract and protected
  release/target tests are unchanged.
- Release 2 sets `sys.dont_write_bytecode` before module imports because isolated
  Python ignores PYTHONDONTWRITEBYTECODE. Installed diagnostics/probes stay clean.

The inherited work was preserved at
`/home/keelan/.cache/simplewm-update-audit/resume-20261014/inherited-work.tar.gz`.
The unused alternative launcher/public key remain in that same audit folder.

## Verification

Passing focused checks: update-bootstrap, update-durable, update-ordinary,
update-seed; unchanged update-check, update-logic, update-plain, update-release,
update-target; image and setup checks; Python compilation and whitespace checks.
Seed regression coverage proves diagnostics/probes create no Python bytecode.

`installed-test-9/output/result.json` is the comprehensive privileged integration
result: actual root/nobody identities, signed future release handoff, real APT
build dependencies, actual Suite/WM builds and grouped rebuild, actual image seed
finalizer, headless compositor startup, unchanged repeat, personal preservation,
retained offline rollback, failed replacement fallback, activation interruption,
bad signature refusal, and interrupted source recovery before offline network
failure. Full APT upgrade was simulated; HTTPS was an isolated signed fixture.
Test 7 passed the earlier subset. Attempts 1-6/8 exposed setup issues subsequently
fixed (symlinks, umask, fixture URLs/identity, private shm, missing Suite headers).
Their original logs remain preserved; they are not passing evidence.

The final production runtime was extracted fresh from the verified r3 ISO,
separate from test/build roots. Verified actual Suite/WM stages produced 506
explicit packaged paths. The runtime ships signed updater 2 and no operation state.
A disposable copy started from production seed 1 and successfully downloaded and
activated real production release 2 over official HTTPS, continued the same
`--wm-only` request, and repeated without reinstall/build. No transport fixture
was used. Actual WM headless startup passed; all 29
installed ELF files checked resolved against the production runtime libraries.
The initial public-smoke sandbox mount attempt failed on Python's symlink before
updater execution; the mount setup was fixed and the full public test then passed.

Final ISO extraction verified all three media checksum lists and compared every
packed file to staging: 262512 regular files,
28598 symlinks, ownership/modes/xattrs and
262 hardlink groups. BIOS/UEFI and MBR/GPT structure,
setuid sudo/pkexec, exact component/seed revisions, empty updater state and absence
of private/test keys were verified. Source archives match their published commits.

Limits: no final ISO VM/hardware boot or Calamares disk installation; no real full
Debian/Liquorix upgrade. Headless operation does not prove next-login/hardware
behavior. APT rollback is not provided. No old-r3 bridge is promised.

## Signing-key custody

Production private key: `/home/keelan/.local/share/simpleupdate-signing/release-private.pem`
(owner-only file 0600 in 0700 parent). Never print it, commit it or include it in
an ISO. Secure backup is needed to preserve future updater signing capability.
Public key: `updater/release-key.pem`, SHA256 `7a354e11e7f6bb6e3b7cc2f99fae8ce26e94c56b59360aed5a0ce62e89ef139b`.
For another engine release, commit code, sign a strictly increasing version with
`updater/release.py`, verify installation, then publish metadata and immutable
payloads together. `updater/README.md` documents the maintainer workflow.

## Useful paths

- All continuation audit work: `/home/keelan/.cache/simplewm-update-audit/`.
- Final assembly/control/logs: `release-r4/` below that audit directory.
- Final production filesystem: `release-r4/rootfs`; packed extraction:
  `release-r4/packed-root`. Build fixtures are only in `release-r4/buildroot`.
- Public updater test state is only in disposable `release-r4/smoke-root`.
- Production seed copies: `production-seed` and `production-seed-v2`.
- Existing cached build env: `runtime-test-5/rootfs`; full integration env:
  `installed-test-9/rootfs`. Do not package either test environment.
- `sudo -n` requires authentication; `pkexec` works with desktop authentication.
- `rg` is unavailable; use grep/find. Read `/home/keelan/simplesuite/AGENTS.md`
  before any future Suite change.
