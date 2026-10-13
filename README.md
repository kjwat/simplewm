# SimpleWM

A small C Wayland tiler for SimpleOS, built on wlroots 0.18. Balanced columns,
click-to-focus, a quiet border, and a wallpaper; no panel or title strips.
Single windows occupy the whole display. Dialogs float with their parent.
Native Wayland and on-demand Xwayland both work. The compositor handles
clipboard, primary selection, drag/drop, cursor constraints, fractional scaling,
output management, idle inhibition, and secure session locking.

The protocol/lifecycle core is derived from dwl 0.7, commit
`74e45c4014ae7048ecbb76eb6f54034b8b479480`, under GPL-3.0. SimpleWM adds its own
layout, runtime text configuration, maximize/restore, input policy, IPC, and
session tools. Upstream: https://codeberg.org/dwl/dwl . See LICENSE and LICENSE.dwm.

## Build and installation

On Debian 13:

```sh
sudo apt install build-essential pkg-config libwlroots-0.18-dev libwayland-dev \
  wayland-protocols libxkbcommon-dev libinput-dev libxcb-icccm4-dev
make
sudo make install
```

Runtime helpers use distro packages `swaybg swayidle swaylock fuzzel grim slurp
wl-clipboard wlr-randr wlopm python3 python3-pil`. Simpleterm and Firefox are launched normally.
Programs and assets install exclusively in `/usr/local`. `DESTDIR` permits
staging; `make uninstall` removes only SimpleWM's own files, preserving user
configuration. The build produces `build/simplewm`; generated binaries stay
out of Git.

Start with `simplewm-session` from a text login, or select SimpleWM in a display
manager that searches `/usr/local/share/wayland-sessions`.

## Configuration

Edit `~/simplewm/config`, or press Super+Shift+C. On SimpleOS,
`~/.config/simplewm` links to `~/simplewm`: both paths refer to the same settings.
`simplewm-setup` creates the source checkout from the bundled Git history without
requiring a network connection and preserves existing settings during migration.
The distributed config is a commented reference for every directive. Strings
with spaces use quotes; `set $name value` defines variables. `include path`
accepts globs relative to the including file, with at most eight nesting levels.
Later bindings replace earlier bindings for the same chord; rules match globbed
`app_id` and `title`, with later matching values taking precedence. Output and
input rules are applied in file order, from broad rules to specific devices.
Fonts, hinting, themes, colors, gaps, layouts, keyboard repeat/layout/options,
cursor, wallpaper, input, display resolution/refresh/scale/rotation/position,
workspaces, application rules, and startup commands are configurable. Workspaces
stop at 1 and 9; Super+1 always reaches the first workspace. Super+S opens the
launcher. Super+A launches LibreOffice Writer; Super+Q opens SimpleVol.

`simplewm --check-config -c path` validates before starting. Super+Shift+R,
`simplewmctl reload`, or SIGHUP applies changes without restarting applications.
Invalid configuration or rejected output settings leave the working config in
place. Startup commands run once per session. Wallpaper paths may contain
spaces and `~/`; `background none` uses the configured background color.
Toolkit settings are applied to GTK and Fontconfig by a short-lived helper;
applications may require reopening for some font/theme changes.

`simplewmctl status` reports JSON with displays, layout, focused client,
workspaces, and window geometry. Other commands use the same actions as
`bindsym`, for example `simplewmctl workspace 2` or `simplewmctl maximize`.
The control socket is private to the logged-in user and refuses actions while
locked. It performs no polling. See HELP.txt for the default shortcuts.

## Updates

Run **`simpleupdate`** once to bring the system up to date. It updates Debian and Liquorix using normal signed APT repositories,
then updates SimpleSuite from `https://github.com/kjwat/simplesuite.git` and
SimpleWM from `https://github.com/kjwat/simplewm.git`. No new package manager or
automatic background updater is involved. Ordinary `apt update` and
`apt full-upgrade` remain available for Debian and Liquorix.

Before ordinary APT updates, SimpleUpdate checks Debian sources in both
`sources.list`/`*.list` and deb822 `*.sources` files. It replaces rolling
`stable`/`oldstable` names with the installed Debian codename, preserving the
original file as `*.simpleupdate-backup`, and refuses mismatched releases.
These checks also apply before component-only updates install build dependencies.
Before installing packages, it also checks the release information in APT's
actual package indexes, including indexes supplied by unfamiliar mirrors.
APT can accept a fixed release's status changing to `oldstable`, while codename
changes continue to require approval.
Debian mirrors outside `debian.org` should explicitly use the Debian archive
`Signed-By` keyring. SimpleOS's diverted Debian `os-release` identifies the
underlying release separately from the SimpleOS version.

SimpleUpdate checks Debian's HTTPS stable-release metadata during ordinary
updates. A newer major release prompts for explicit approval; pressing Enter
continues ordinary updates. Failed release detection reports the problem and
leaves current-release updates available. Noninteractive runs only report a
new release. Package installation still requires normal signed APT metadata.

For an approved major upgrade, read the linked
[Debian release notes](https://www.debian.org/releases/stable/release-notes/),
log out of every SimpleWM session, switch to a text console with Ctrl+Alt+F2,
log in, and run `simpleupdate --release-upgrade`. Type the new codename to
start preflight. Plain `simpleupdate` offers this same process when a new stable
release is available. SimpleUpdate supports the next stable major release only;
it refuses to skip Debian releases. It checks package state and both Git
repositories, then creates a temporary userspace for that target release with
mmdebstrap. If mmdebstrap is absent, its package is downloaded and checked against
current signed APT metadata, then extracted into the work directory without
installing host packages or refreshing host caches.

Inside the target userspace, SimpleUpdate retrieves the selected SimpleWM Git
revision, resolves its development dependencies using target APT, selects the
newest installable wlroots development ABI, and determines its actual pkg-config
module. The target compiler builds against target headers and libraries. Default
configuration, linkage, configuration tests and the headless compositor session
test must pass. Compiler errors abort before installed-release APT changes. There
is no attempt to edit C source or fall back to an older wlroots ABI. Compatible
future Git source and its `build-dependencies.json` are used automatically.
SimpleSuite's build dependencies are also resolved in that userspace.

Only after that succeeds does SimpleUpdate request final confirmation to change
the installed Debian system. Declining leaves installed packages and configuration
unchanged. It backs up `/etc`, the invoking user's `.config`/shell settings,
package state and installed source/configuration records under `/var/backups/simpleupdate`,
saves the verified SimpleWM payload and dependency versions durably, and finishes
current-release updates. It then switches Debian repositories to the
new codename, disables third-party sources (including Liquorix), backports and
proposed updates, and runs Debian's documented minimal upgrade followed by a
full upgrade. APT's package-removal and configuration prompts remain interactive.
SimpleSuite rebuilds through the existing installation routines. The previously
compiled SimpleWM payload is checked against the upgraded system's libraries and
configuration before transactional installation, even when its Git revision is
unchanged. Reboot before starting SimpleWM, and restore only third-party
repositories that support the new release.
Backups preserve configuration symlinks and separately save their target contents
in `linked-configuration.tar.gz`, including settings stored outside `.config`.

Major upgrades can require source changes and rebuilding can fail. Configuration
backups and source-install transactions do **not** roll back Debian. Review the
APT transcript and release notes after an interrupted upgrade; after resolving
APT problems, retry source builds from a text console with
`simpleupdate --rebuild`. A small record in `/var/lib/simpleupdate` remembers an
unfinished release upgrade across restarts. Ordinary and component-only updates
remain blocked until APT is healthy on the approved release and both source
rebuilds/installations succeed; skipped or failed components do not clear that
record. The saved SimpleWM payload is checked for corruption and reused during
recovery. Ext4 is supported. No snapshots, partition changes, filesystem conversion,
or bootloader management are required or performed. Interrupted Debian package
upgrades can require manual APT recovery from a console or Debian rescue media.

`simpleupdate --dry-run` previews ordinary operations without sudo, commands or
system writes. `simpleupdate --release-upgrade --dry-run` previews the major
upgrade when a newer stable release exists; it never asks for approval or
executes the plan. HTTPS release detection still needs network access.
`--check` retains the existing update-checking interface and may refresh APT
caches and fetch temporary Git sources; it never approves a release upgrade.

Git uses verified HTTPS, refuses redirects and file/exec transports, checks
objects, and ignores user Git settings, hooks, and credential helpers. There is
no claim of independent signature verification: trust is in these official
GitHub repositories and HTTPS. Builds and tests run without root privileges in
a private temporary home. An unchanged installed revision skips rebuilding.
Normal updates build changed revisions and install them without running developer
tests. `--verify` explicitly adds the full release suites. SimpleWM configuration
and runtime-library checks always run before installation. Each
component has a recoverable source-install transaction; a failed build never reaches the
installation, and partial installation restores that component's old files.
Successful earlier components remain updated if a later component fails.

The 0.8-r2 ISO ships published Suite and WM revisions and their Git history.
Its original updater already fetches the latest official releases and installs
changed components, including Simpleterm and the updater itself, in one run of
`simpleupdate`. Reinstalling that ISO follows the same path; no component flags
or preliminary updater command are needed. A regression test runs the unmodified
updater shipped in that ISO with no arguments, fresh-install manifests, real Git
ancestry and installation transactions.

Simpleterm is built and installed with every changed SimpleSuite release,
including its Bash prompt asset. Published terminal fixes arrive through the
same updater on fresh installs. Simpleterm 0.2.7 restores the wallpaper palette
with **Use colors from system theme** and saves the working **Simpleterm**
preset. Open terminals can finish normally; close and reopen Simpleterm to use
the updated preferences code.

Personal configurations, documents, dotfiles, browser profiles, and suite data
are preserved. APT keeps modified conffiles. Build dependencies come from APT
only when a build is needed. Source snapshots and revision manifests live in
`/usr/local/share/{simplewm,simplesuite}`. Transcripts live in
`/var/log/simpleupdate`; APT also keeps its normal system logs.

```sh
simpleupdate
```

Restart SimpleWM by logging out and in after a compositor update. Existing
applications continue running during updates. Reboot to use a new kernel.
The image retains a current Debian kernel as a fallback. Liquorix boots by
default on both live media and installed disks; its package and headers track
the Liquorix APT metapackages. Liquorix is unsigned, so Secure Boot must be off
unless you arrange your own signing.

## Wallpaper and palette

Super+W opens the wallpaper wizard in Simpleterm. Clean installs use Fill.
You can also run
`wallpaper-theme /path/to/picture` or `wallpaper-theme --mode fill --zoom 1.5 /path/to/picture`.
Running `wallpaper-theme` without an image also opens the terminal prompts.
The tool retains the palette extraction and contrast rules from your original
`wallpaper-theme-dwm.sh`, applying the result to SimpleWM borders/background,
GTK, Fuzzel, Simpleterm's ANSI colors, Xresources, and existing Firefox profiles.
It adds a small `palette.conf` include instead of replacing your WM config.
Font settings remain separate. Existing GTK CSS, Firefox preferences and chrome
styles are preserved. Open Simpleterm windows reload their colors automatically.
Restart Firefox after its first palette change.
`wallpaper-theme --wallpaper-only PATH` changes only the image;
`wallpaper-theme --rollback` restores the previous files.

## SimpleOS image

The ISO keeps the XFCE live desktop and attended Calamares installer. Its
slideshow introduces SimpleWM and its shortcuts. The installed system boots
to a text login and starts SimpleWM on tty1 after authentication; tty2 and SSH
remain ordinary shells. Super+F1 shows help, Super+Shift+C edits the config,
and Super+Shift+R reloads it. The default wallpaper is the original SimpleOS
background. Click focus, mouse acceleration, speed, scroll direction, touchpad
tapping, repeat timing, Ubuntu Sans/Ubuntu Sans Mono, slight hinting and RGB
subpixel preferences were copied from the reference Ubuntu installation.
Applications/assets are system-wide in `/usr/local`; user settings and data
use ordinary XDG home paths. Git is ready for installing your Scriptorium dots.

`image/prepare-rootfs.py` applies the policy to a disposable extracted image
after signed APT provisioning and source staging. `image/repack.py` rebuilds
the live filesystem and replays the original hybrid BIOS/UEFI boot setup,
restoring the rootless extraction's ownership, setuid bits and capabilities,
and regenerating the media manifests. See `image/README.md` for exact inputs.

## Verification

`tests/config-check.py` exercises validation, includes, bounds, and failures.
`tests/session-check.py` runs real GTK Wayland windows, virtual keyboard input,
clipboard, layouts, maximize/restore, workspaces, reload, and Xwayland against
the compositor. `VALIDATION.md` records completed checks and the image's
remaining validation work.
