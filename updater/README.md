# Versioned updater and image seed

`launcher.py` is the stable protocol-1 entry point installed as
`/usr/local/bin/simpleupdate`. It retrieves `main/updater/release.json` from the
fixed official HTTPS origin. Payload bytes come from the recorded immutable Git
revision and are checked against the recorded sizes and SHA-256 hashes. Trust is
in the official repository and verified HTTPS; there is no custom signing key.
Transport/download and initialization probes run as `nobody`. Payload code
runs only after verification; ordinary source builds also run as `nobody`.

Version directories live in `/usr/local/libexec/simpleupdate/versions`.
`/var/lib/simpleupdate/updater.json` durably records active, previous, pending,
highest verified version and rejected versions. A two-way handshake keeps
ordinary work behind durable activation. An interrupted activation or failed
initialization restores a verified predecessor. Corrupt payloads,
unsupported protocols and rollback metadata stop before component work. The
launcher belongs to the ISO bootstrap; ordinary WM installation
excludes it. New updater releases must remain compatible with protocol 1.

`engine.py` loads `legacy.py`, the preserved release-migration authority.
Only the ordinary callback uses `ordinary.py` and `transaction.py`. Explicit
major migration and its pending recovery bypass updater downloads. The target
helper stays beside legacy.py and its copy/import contract is unchanged.

Ordinary phase records live in `/var/lib/simpleupdate/ordinary.json`.
The active source journal is `/usr/local/.simpleupdate-ordinary`; the most recent
successful transaction is retained at `/usr/local/.simpleupdate-previous`.
Backups are copied during recovery, never consumed, so recovery can itself be
interrupted. Unknown files are not adopted. Personal homes are outside the
installation transaction. The root-owned ownership inventory is
`/usr/local/share/simpleupdate/owned.json`.

## Maintainer release

No private key or signature is required. No tool publishes code automatically.

1. Complete the checks appropriate to the change and commit the implementation files.
2. Run `python3 updater/release.py --version N --revision COMMITTED_SHA`.
   Use a new increasing integer.
3. Commit `updater/release.json`. The recorded revision
   is the implementation commit, which precedes this metadata commit.
4. Verify `python3 updater/install.py --destdir /disposable/seed`. Unrecorded
   working-tree changes to payload files are refused. Stage the normal WM
   installer with `make DESTDIR=/disposable/wm-payload install`.
5. Publish the verified implementation and metadata together before shipping
   an ISO that depends on them. Confirm the fixed HTTPS metadata file and
   immutable payload paths are reachable and match their recorded sizes/hashes.

The launcher deliberately has no production environment override for origins,
state directories or bypassing verification. Tests import it with
fixtures or use a private test HTTPS origin inside a disposable namespace.
Never copy test keys, fixture trust roots, command shims, logs, credentials or
recovery journals into a release image.

## ISO assembly

Use the normal Suite and WM staged payloads, including their source snapshots,
Git bundles and revision manifests. Install the versioned seed through the WM
Makefile. After assembling the image, run:

```sh
python3 image/seed-updater.py ROOTFS \
  --payload SUITE_PAYLOAD/usr/local --payload WM_PAYLOAD/usr/local
```

This verifies the versioned seed, checks every explicitly packaged file against
the assembled image, records ownership, and protects updater system directories.
It does not adopt arbitrary existing `/usr/local` files. Seed directories must
be root-owned in the image. The booted system creates updater state on first use.

The previous r3 handoff requirement was superseded by one new ISO. Do not claim
that replacing the script changes an old interpreter already in flight.

## Validation and limits

Fast checks: `tests/update-bootstrap-check.py`, `update-durable-check.py`,
`update-ordinary-check.py`, and `update-seed-check.py`. Preserve and run the
existing migration/target tests unchanged.

`tests/update-installed-check.py --rootfs CACHED_ISO_ROOT --work-dir NEW_DIR`
requires administrator authentication and Bubblewrap. It copies the rootfs,
uses a test HTTPS release, installs the seed via the Makefile, performs
actual dependency installation and Suite/WM compilation as root/nobody, and records
same-request replacement, unchanged repeat, personal-file preservation and
retained source rollback, failed replacement fallback, interrupted activation,
offline interrupted source recovery. It also verifies
explicit image ownership and a real grouped rebuild. Full Debian/Liquorix
upgrade is simulated. The test
uses local HTTPS port 443 while running; its trust roots affect only the copy.

APT has no automatic rollback. Minimum free-space checks and APT's archive
checks do not guarantee sufficient room for every possible future build.
Headless startup verifies basic compositor operation, not graphics hardware or
next-login success. Retained source rollback may not work with libraries changed
by a Debian major upgrade; complete that upgrade's established recovery first.
