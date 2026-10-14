SimpleWM's lock client adapts the session-lock, seat/input, shared-memory,
event-loop, password-memory and PAM subprocess code from Swaylock 1.8.2:
https://github.com/swaywm/swaylock/tree/v1.8.2 (MIT, ../LICENSE.swaylock).
Upstream commit: a1cf39ab0ff0687994a66ba116b316bc59849e2c.
The authentication service remains the distro's `/etc/pam.d/swaylock`, supplied
by its `swaylock` package. No setuid binary or custom PAM policy is installed.

`main.c` retains the upstream Wayland output/session lifecycle with a smaller
CLI, literal image paths, and an explicit successful-authentication guard on
unlock. The upstream signal-to-unlock hook and Swaylock configuration lookup
are omitted. `password.c` adds character counts and entry visibility while
retaining upstream UTF-8 editing, clearing, locked memory and asynchronous PAM.
The renderer receives only the mask count and status, never password bytes.
The reduced Linux-PAM application declarations in `include/pam-compat.h` use
its stable `libpam.so.0` ABI; see ../LICENSE.pam. This also builds with the
development packages installed by the original SimpleOS updater.

`ui.c` and `render.c` provide the SimpleWM presentation, minute clock updates
across suspend and clock adjustments, and a 280 ms rejection shake. Output
hotplug and resizing still use the upstream ext-session-lock lifecycle.
`scripts/simplewm-lock` resolves the active compositor appearance, prepares a
private blurred wallpaper cache, and adjusts the palette for contrast. A solid
theme background is used when image preparation fails. Concurrent callers wait
for the Wayland locked event before returning, including swayidle before-sleep.

`make lock-preview` builds an offline PNG renderer using the same drawing code.
It is never installed and cannot authenticate or unlock anything. The
test-only authentication fixture is likewise linked only into a temporary
headless-test binary. Production has no test-password or unlock bypass option.
