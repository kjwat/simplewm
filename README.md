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
  wayland-protocols libxkbcommon-dev libinput-dev libxcb-icccm4-dev libcairo2-dev
make
sudo make install
```

Runtime helpers use distro packages `swaybg swayidle swaylock fuzzel grim slurp
wl-clipboard wlr-randr wlopm python3 python3-pil`. Simpleterm and Firefox are launched normally.
Programs and assets install exclusively in `/usr/local`. `DESTDIR` permits
staging; `make uninstall` removes only SimpleWM's own files, preserving user
configuration. The build produces `build/simplewm`; generated binaries stay
out of Git. The native lock client also builds with SimpleWM and installs under
`/usr/local/bin`, using the distro's Swaylock PAM service.

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

Super+Page Up/Down workspace shortcuts allow Super to arrive up to 30 ms after
the page key, accommodating nearly simultaneous presses. Bare Page Up/Down
presses wait at most 30 ms; releasing the key or pressing another key forwards
them sooner. This applies only when that page key has a Super-only workspace
binding. Typing and other shortcuts retain their normal timing.

`simplewm --check-config -c path` validates before starting. Super+Shift+R,
`simplewmctl reload`, or SIGHUP applies changes without restarting applications.
Invalid configuration or rejected output settings leave the working config in
place. Startup commands run once per session. Wallpaper paths may contain
spaces and `~/`; `background none` uses the configured background color.
Toolkit settings are applied to GTK and Fontconfig by a short-lived helper;
applications may require reopening for some font/theme changes.

SimpleWM ships the captured Ubuntu Sans and Ubuntu Sans Mono 1.006 font files.
The session uses 104 DPI, slight hinting and RGB antialiasing; the default
terminal font is Ubuntu Sans Mono 12, matching the size of 13 points at 96 DPI.
The fonts and settings install with an ordinary `simpleupdate`, including on
fresh SimpleOS installations. Log out and back in afterward. Existing stock
13-point terminal settings move to 12 once, with the old config saved in
`~/.local/state/simplewm/config-before-butterfonts`; other font choices stay as set.

Native touchpad pinch, swipe and hold gestures are forwarded to the
pointer-focused Wayland client through `zwp_pointer_gestures_v1` (version 3).
The wlroots 0.18 input path preserves event timestamps, finger counts, movement,
pinch scale/rotation and cancellation. Existing pointer movement, scrolling,
tapping, buttons and keyboard bindings keep their normal handling. No gesture
daemon or additional runtime dependency is needed.

To verify the protocol, run this inside a SimpleWM session (install the optional
Debian `wayland-utils` package if `wayland-info` is unavailable):

```sh
wayland-info | grep zwp_pointer_gestures_v1
```

Expect an interface entry with version 3. This confirms protocol advertisement;
it does not prove hardware events are arriving. In Firefox, confirm
`about:support` reports the Window Protocol as `wayland`, place the pointer over
a web page and pinch with two fingers. If Firefox starts through Xwayland,
close its processes and start `MOZ_ENABLE_WAYLAND=1 firefox`. For event tracing,
start a fresh Firefox process with `WAYLAND_DEBUG=1 MOZ_ENABLE_WAYLAND=1 firefox`
and look for `zwp_pointer_gesture_pinch_v1` begin/update/end events while
pinching. Other clients must also support the protocol; hold/swipe actions are
chosen by each application. Physical gesture recognition depends on the device
and libinput.

Existing ISO installations gain this through the ordinary `simpleupdate`
source rebuild and staged installation once this revision is published to the
official update repository. Log out and back in to run the new compositor;
configuration reload alone cannot replace the running executable. No ISO
rebuild, configuration migration or updater protocol change is required.
Before publication, a local checkout can be staged through
`sudo simpleupdate --wm-local /path/to/simplewm --rebuild`.
`make check-gestures` checks all cursor gesture listeners and their exact
wlroots send arguments, including both cancellation states.

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

New installations start with a small stable launcher and a versioned updater.
A normal `simpleupdate` invocation checks for updater improvements first. The
launcher retrieves release metadata from the official HTTPS repository
and checks every payload's size and SHA-256; no custom signing key is required.
Only an initialized replacement can become active; it receives the original
request after activation is durable. The previous updater and the ISO seed are
retained for recovery. Ordinary WM installation cannot replace the launcher or
active updater with an older bundled version.

Ordinary Suite/WM source retrieval still trusts the official GitHub repositories
and HTTPS; source components do not gain independent release signatures. Git
refuses redirects and file/exec transports, checks objects and ancestry, and
ignores user Git settings, hooks and credential helpers. Unchanged revisions
skip builds. Builds run as `nobody` in a private temporary home; `--verify` adds
the developer test suites. Configuration, runtime-library checks and a private
headless SimpleWM startup check run before installing a changed compositor.

Both changed source components are built before either is installed. Their
payloads, ownership inventory and provenance records form one durable
transaction. Interrupted source installation is recovered before network
access on the next ordinary invocation. Locally edited shared configuration
and unrelated files are preserved. Locally rebuilt managed programs are backed
up and replaced normally; conflicting unmanaged programs stop installation.
The last successful source transaction is retained, including local builds.

`simpleupdate --status` shows the last ordinary operation. Use
`simpleupdate --rollback-sources` from a console to restore the previous Suite/WM
files if the new session fails on your hardware. This works offline and does
not roll back Debian packages. `simpleupdate --previous-updater` selects the
previous verified updater and continues the request. Downloads and builds are
shown with a filling progress bar, elapsed time and current activity by default;
`--verbose` also shows full output, and transcripts remain in
`/var/log/simpleupdate`.

APT remains non-atomic. Package downloads precede installation, but a package
failure can require `sudo dpkg --configure -a` and `sudo apt-get -f install`
before retrying. Source rollback is not whole-system rollback. Explicit Debian
major upgrades and pending major-upgrade recovery retain their existing
implementation and sequence. A headless startup check cannot guarantee the
next hardware-backed login.

The 0.8-r5 bootstrap installs the newer updater and continues the original
request in the same invocation; run `simpleupdate` normally after installation.
`tests/update-handoff-check.py` exercises that shipped bootstrap against the
real new engine and source transaction, including a locally rebuilt program.
The archived r2/r3 updater tests
remain historical regression evidence; they do not establish a same-invocation
handoff from an already-running old Python script. Release and image assembly
instructions are in [updater/README.md](updater/README.md).

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

Super+L, idle locking, and suspend all use `simplewm-lock`. A centered clock
uses the configured monospace font over a heavily blurred copy of the active
wallpaper. The desktop palette supplies its colors; a soft tint around the
clock and entry keeps text readable on bright and dark wallpapers. Wallpaper
and palette changes apply on the next lock without separate lock settings.
The first typed character reveals the centered password field and is retained,
with one `*` per character. Enter verifies, a wrong password briefly shakes the
field and displays **try again**, and Escape clears the entry and returns to
the clock. Caps Lock and multiple keyboard layouts are shown while entering
the password. The session stays locked if the lock client crashes.

The lock client and launcher are part of the normal `make install` payload and
arrive through ordinary `simpleupdate`, including fresh installs. The updated
locker works immediately after installation; the compositor's new appearance
report is used after the next login. An older running compositor uses its
existing config and palette. The launcher caches only blurred wallpaper images
under `~/.cache/simplewm/lock`; a missing or unreadable image uses the theme's
solid background. See [lock/README.md](lock/README.md) for source attribution
and the offline preview command.

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
