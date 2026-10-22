#!/usr/bin/python3
"""Run real motion listeners with mapped GTK surfaces in a private headless session."""
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile

source = Path(__file__).resolve().parent.parent
wrapped = [
    'wlr_seat_pointer_notify_enter', 'wlr_seat_pointer_notify_motion',
    'wlr_relative_pointer_manager_v1_send_relative_motion',
    'wlr_idle_notifier_v1_notify_activity', 'wlr_cursor_set_xcursor',
    'wlr_cursor_set_surface', 'wlr_pointer_constraint_v1_send_activated',
]
with tempfile.TemporaryDirectory(prefix='simplewm-motion-') as temp:
    root = Path(temp)
    runtime = root / 'runtime'
    runtime.mkdir(mode=0o700)
    probe = root / 'probe.py'
    probe.write_text('''import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
window = Gtk.Window(title=sys.argv[1])
window.set_decorated(False)
window.set_default_size(280, 180)
text = Gtk.TextView()
text.get_buffer().set_text('Screenshot drags must not select this text.\\n' * 12)
scroll = Gtk.ScrolledWindow()
scroll.add(text)
window.add(scroll)
window.show_all()
Gtk.main()
''')
    pkg = os.environ.get('WLROOTS_PKG', 'wlroots-0.18')
    flags = shlex.split(subprocess.check_output([
        'pkg-config', '--cflags', '--libs', pkg, 'wayland-server', 'xkbcommon',
        'libinput', 'xcb', 'xcb-icccm', 'pixman-1'], text=True))
    subprocess.run([
        os.environ.get('CC', 'cc'), '-I.', '-Ibuild', '-DWLR_USE_UNSTABLE',
        '-DXWAYLAND', '-DVERSION="test"', '-std=c11', '-Wall', '-Wextra',
        '-Werror', '-Wno-unused-parameter', *shlex.split(os.environ.get('CFLAGS', '')),
        'tests/motion-check.c', 'util.c', *flags, '-lm',
        *[f'-Wl,--wrap={name}' for name in wrapped],
        *shlex.split(os.environ.get('LDFLAGS', '')), '-o', str(root / 'motion'),
    ], cwd=source, check=True)
    env = os.environ | {
        'XDG_RUNTIME_DIR': str(runtime), 'WLR_BACKENDS': 'headless',
        'WLR_HEADLESS_OUTPUTS': '2', 'WLR_RENDERER': 'pixman', 'HOME': str(root),
        'XDG_CONFIG_HOME': str(root / '.config'), 'GDK_BACKEND': 'wayland',
        'GSETTINGS_BACKEND': 'memory', 'NO_AT_BRIDGE': '1', 'GDK_SCALE': '1',
    }
    with (root / 'motion.log').open('w+') as log:
        process = subprocess.Popen([str(root / 'motion'), str(probe)], cwd=source, env=env,
                                   stdout=log, stderr=log, start_new_session=True)
        try:
            assert process.wait(timeout=50) == 0, 'motion regression failed'
        finally:
            # Also reap the GTK/Xwayland children after assertions or timeouts.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            log.seek(0)
            print(log.read(), end='')
