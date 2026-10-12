# Image build

The build uses the downloaded SimpleOS 0.6-r1 ISO as its base. Debian package
versions are resolved through normal signed trixie repositories; no host
programs or host configurations are installed or removed by this process.

The build staging directory is `/home/keelan/simpleos-build`:

* `original/0.6/`: unmodified downloaded ISO and source release.
* `rootfs/`: extracted runtime filesystem, updated with APT and Liquorix.
* `buildroot/`: separate Debian build/test environment, with compiler headers
  and the full upstream test dependencies.
* `simplesuite/`: verified official Git source at the recorded revision.
* `payload/usr/local/`: tested Suite and Simpleterm staged through their installers.
* `media/`: extracted ISO media, used to replace the live squashfs and boot files.

To reproduce from a new staging directory, extract the ISO with xorriso and
unsquashfs. Provision the runtime filesystem with Debian trixie's normal APT
repositories and the dedicated signed Liquorix trixie source. Install the
Liquorix image and headers metapackages, wlroots 0.18 runtime, Xwayland, Firefox
ESR, git, GTK/VTE, PipeWire/WirePlumber, portals, and the helpers named in the
project README. Keep the XFCE/Calamares live environment. Build/test/stage the
official Suite in a separate Debian root using its upstream release gate,
then stage Simpleterm with `install-simpleterm.sh --no-deps` and DESTDIR.

Divert `/usr/lib/os-release` to `/usr/lib/os-release.debian` using dpkg-divert
inside the staged image, then run `prepare-rootfs.py ROOTFS PAYLOAD SUITE_SOURCE`.
Run `make DESTDIR=ROOTFS install` for SimpleWM after building/testing it against
that Debian ABI. Ship Ubuntu Sans/Ubuntu Sans Mono and their font licenses,
Yaru themes/cursor and their licenses, and the original wallpaper under
`/usr/local/share`. Compile dconf defaults and refresh the font cache inside
the staged root. Keep machine-id empty and omit SSH host keys, private data,
Tailscale identities, apt archives, temporary runtime files and build artifacts.
Copy the clean WM source to `/usr/local/share/simplewm/source` and record its
`source_digest` from `scripts/simpleupdate` in the WM install manifest.

Finally:

```sh
python3 image/repack.py ORIGINAL_ISO ROOTFS MEDIA OUTPUT_ISO
```

This script accepts only extracted staging trees, never `/`. It preserves the
original hybrid boot loaders, retains a Debian fallback live boot entry, and
rebuilds all media checksums. Never put test VM passwords or validation SSH keys
into the image. See `../VALIDATION.md` for completed tests and remaining
release validation.
