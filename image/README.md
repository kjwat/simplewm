# Image build

The SimpleOS 1.0 build uses the verified SimpleOS 0.8-r5 ISO as its base. Debian package
versions are resolved through normal signed trixie repositories; no host
programs or host configurations are installed or removed by this process.

The build staging directory is `/home/keelan/simpleos-build`:

* `original/0.6/`: unmodified downloaded ISO and source release.
* `rootfs/`: extracted runtime filesystem, updated with APT and Liquorix.
* `buildroot/`: separate Debian build/test environment, with compiler headers
  and the full upstream test dependencies.
* `simplesuite-next/`: verified official Git source at the recorded revision.
* `payload-next/usr/local/`: tested Suite, SimpleTerm and SimplePlay staged through their installers.
* `media/`: extracted ISO media, used to replace the live squashfs and boot files.

To reproduce from a new staging directory, extract the ISO with xorriso and
unsquashfs. Provision the runtime filesystem with Debian trixie's normal APT
repositories and the dedicated signed Liquorix trixie source. Install the
Liquorix image and headers metapackages, wlroots 0.18 runtime, Xwayland, Firefox
ESR, git, GTK/VTE, PipeWire/WirePlumber, portals, and the helpers named in the
project README. Keep the XFCE/Calamares live environment. Build/test/stage the
official Suite in a separate Debian root using `make full` and its upstream
checks, then stage it with `make DESTDIR=PAYLOAD install-full`. This uses the
Suite's complete installer and its generated installation receipt, including
new applications, without an image-builder program list. Include `simpleplay-core`
and the FFmpeg, SDL 2, libass, FluidSynth, libsidplayfp, JSON-GLib and SoundFont
runtime packages. `simpleupdate` installs their build dependencies and stages
the complete Suite payload when updating a system installed from an older ISO.

Divert `/usr/lib/os-release` to `/usr/lib/os-release.debian` using dpkg-divert
inside the staged image, then run `prepare-rootfs.py ROOTFS PAYLOAD SUITE_SOURCE`.
The Suite revision is read from the staged install manifest; an explicit
`--suite-revision` must agree with it.
Run `make DESTDIR=ROOTFS install` for SimpleWM after building/testing it against
that Debian ABI. Ship Ubuntu Sans/Ubuntu Sans Mono and their font licenses,
Yaru themes/cursor and their licenses, and the original wallpaper under
`/usr/local/share`. Compile dconf defaults and refresh the font cache inside
the staged root. Keep machine-id empty and omit SSH host keys, private data,
Tailscale identities, apt archives, temporary runtime files and build artifacts.
Copy the clean WM source to `/usr/local/share/simplewm/source` and record its
published Git commit as `simplewm_source_sha` in
`/usr/local/share/simplewm/install-manifest`, alongside
`repository=https://github.com/kjwat/simplewm.git`. For unpublished local changes,
use `source_digest` from `scripts/simpleupdate` instead. Generated build files and
Git metadata do not belong in the source snapshot.

The image builder generates all Bash application shortcuts from the staged
Suite's `command-abbreviations`, plus `term`, `play`, `check`, and `trident`, in
both the system Bash configuration and the new-user skeleton. It rejects
missing executable targets instead of shipping incomplete aliases. Run
`python3 tests/image-check.py`, `python3 tests/setup-check.py`,
`python3 tests/update-check.py`, `python3 tests/update-logic-check.py`, and
`python3 tests/update-plain-check.py` before
repacking. Update comparisons use ancestry for both Suite and WM; older,
diverged, and unrecorded installed histories are preserved. Suite updates also
install a Git bundle so later comparisons retain the installed history.
The offline source bundle
must include `main`; setup explicitly checks out that branch.

Fresh users inherit the tested butterfonts environment and 104 DPI Xresources;
the live display helper uses the same DPI. System Fontconfig selects the bundled
Ubuntu faces with slight hinting and RGB antialiasing, and SimpleTerm follows
Ubuntu Sans Mono 12. Firefox policy defaults set integer
`gfx.font_rendering.cleartype_params.pixel_structure=1` and string
`layout.css.devPixelsPerPx="1"`. Explicit policy types preserve the numeric
preference on Linux, where an unknown 0/1 preference would otherwise become a
boolean. Personal browser profiles are never copied into release media.

Before repacking a new-bootstrap image, stage both components with their source
snapshots, Git bundles and manifests, and finalize the updater seed:

```sh
sudo python3 image/seed-updater.py ROOTFS \
  --payload SUITE_PAYLOAD/usr/local --payload WM_PAYLOAD/usr/local
```

This verifies the versioned updater and every explicitly packaged file, records
ownership without adopting unrelated files, and fixes system parent ownership
and permissions. Publish and verify the HTTPS updater metadata and payloads
before shipping; see `../updater/README.md`. No signing key is required.
No updater state or retained test recovery transaction belongs in a fresh ISO.

Finally:

```sh
python3 image/repack.py ORIGINAL_ISO ROOTFS MEDIA OUTPUT_ISO
```

This script accepts only extracted staging trees, never `/`. It preserves the
original hybrid boot loaders, retains a Debian fallback live boot entry, and
rebuilds all media checksums. Release branding and the volume ID come from the
prepared image's `VERSION`. Rootless builds pass `--ownership-pseudo FILE`
with ownership, privileged modes and capabilities verified against the actual
base image; the older bundled metadata is historical. Never put test VM passwords or validation SSH keys
into the image. See `../VALIDATION.md` for completed tests and remaining
release validation.
