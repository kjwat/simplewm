# Enter the quiet writing desk after login on the first physical console.
# Rescue consoles and SSH remain ordinary shells; XFCE is retained for live install.
if [ "$(id -u)" -ne 0 ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ] &&
   [ -z "${SSH_TTY:-}" ] && [ "${SIMPLEWM_NO_AUTOSTART:-0}" != 1 ] &&
   [ ! -d /run/live/medium ] && [ "$(tty 2>/dev/null)" = /dev/tty1 ]; then
    exec /usr/local/bin/simplewm-session
fi
