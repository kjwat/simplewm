#!/usr/bin/python3
"""Exercise real cursor listeners and verify every wlroots gesture send argument."""
import os
from pathlib import Path
import shlex
import re
import shutil
import time
import subprocess
import tempfile

source = Path(__file__).resolve().parent.parent
kinds = [('swipe', 'begin'), ('swipe', 'update'), ('swipe', 'end'),
         ('pinch', 'begin'), ('pinch', 'update'), ('pinch', 'end'),
         ('hold', 'begin'), ('hold', 'end')]
code = '''#define main simplewm_main
#include "simplewm.c"
#undef main
#include <assert.h>
static unsigned calls;
'''
cases = []
for index, (kind, phase) in enumerate(kinds):
    name = f'{kind}_{phase}'
    signature = 'struct wlr_pointer_gestures_v1 *manager, struct wlr_seat *target, uint32_t time'
    checks = f'assert(manager == pointer_gestures && target == seat && time == {0xfffffff0 + index}u);'
    fields = f'.time_msec = {0xfffffff0 + index}u'
    if phase == 'begin':
        signature += ', uint32_t fingers'
        checks += ' assert(fingers == 4);'
        fields += ', .fingers = 4'
    elif phase == 'update':
        signature += ', double dx, double dy'
        checks += ' assert(dx == -3.25 && dy == 8.5);'
        fields += ', .dx = -3.25, .dy = 8.5, .fingers = 4'
        if kind == 'pinch':
            signature += ', double scale, double rotation'
            checks += ' assert(scale == 1.75 && rotation == -12.5);'
            fields += ', .scale = 1.75, .rotation = -12.5'
    else:
        signature += ', bool cancelled'
        checks += ' assert(cancelled == expected_cancelled);'
    code += (f'static bool expected_cancelled;\n' if index == 0 else '')
    code += f'void __wrap_wlr_pointer_gestures_v1_send_{name}({signature}) {{ {checks} calls++; }}\n'
    cases.append(f'''{{ struct wlr_pointer_{name}_event event = {{ {fields} }};
        wl_signal_emit_mutable(&cursor->events.{name}, &event);'''
                 + (f''' expected_cancelled = true; event.cancelled = true;
        wl_signal_emit_mutable(&cursor->events.{name}, &event);
        expected_cancelled = false;''' if phase == 'end' else '') + ' }')
code += '''int main(void) {
    alarm(20);
    Config *loaded = read_config("config");
    assert(loaded); cfg = *loaded; free(loaded);
    setup();
    assert(pointer_gestures && pointer_gestures->global);
    double x = cursor->x, y = cursor->y;
''' + '\n'.join(cases) + '''
    assert(calls == 11);
    assert(cursor->x == x && cursor->y == y);
    puts("OK eight cursor gesture listeners, exact payloads, normal/cancelled ends, unchanged cursor");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='simplewm-gestures-') as temp:
    root = Path(temp)
    test = root / 'gestures.c'
    test.write_text(code)
    runtime = root / 'runtime'
    runtime.mkdir(mode=0o700)
    pkg = os.environ.get('WLROOTS_PKG', 'wlroots-0.18')
    flags = shlex.split(subprocess.check_output([
        'pkg-config', '--cflags', '--libs', pkg, 'wayland-server', 'xkbcommon',
        'libinput', 'xcb', 'xcb-icccm'], text=True))
    subprocess.run([os.environ.get('CC', 'cc'), '-I.', '-Ibuild', '-DWLR_USE_UNSTABLE',
                    '-DXWAYLAND', '-DVERSION="test"', '-std=c11', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-parameter', str(test), 'util.c', *flags, '-lm',
                    *[f'-Wl,--wrap=wlr_pointer_gestures_v1_send_{g}_{p}' for g, p in kinds],
                    '-o', str(root / 'gestures')], cwd=source, check=True)
    subprocess.run([str(root / 'gestures')], cwd=source, check=True, timeout=25,
                   env=os.environ | {'XDG_RUNTIME_DIR': str(runtime), 'WLR_BACKENDS': 'headless',
                                     'WLR_RENDERER': 'pixman', 'HOME': str(root)})

    # wayland-info is an optional developer tool, never a compositor dependency.
    if shutil.which('wayland-info'):
        config = root / 'config'
        config.write_text((source / 'config').read_text().replace(
            'exec simplewm-services', '# disabled for protocol check'))
        env = os.environ | {'XDG_RUNTIME_DIR': str(runtime), 'HOME': str(root),
                            'WLR_BACKENDS': 'headless', 'WLR_RENDERER': 'pixman'}
        with (root / 'protocol.log').open('w') as log:
            wm = subprocess.Popen([str(source / 'build/simplewm'), '-c', str(config)],
                                  env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 10
                while True:
                    sockets = [p for p in runtime.glob('wayland-*') if p.is_socket()]
                    if sockets:
                        break
                    assert wm.poll() is None, (root / 'protocol.log').read_text()
                    assert time.monotonic() < deadline, 'Wayland socket did not appear'
                    time.sleep(.05)
                result = subprocess.run(['wayland-info'], env=env | {
                    'WAYLAND_DISPLAY': sockets[0].name}, capture_output=True,
                    text=True, check=True, timeout=10)
                assert re.search(r"interface: 'zwp_pointer_gestures_v1',\s+version:\s+3,",
                                 result.stdout), result.stdout
                print('OK wayland-info: zwp_pointer_gestures_v1 version 3')
            finally:
                wm.terminate()
                wm.wait(timeout=10)
    else:
        print('SKIP optional wayland-info registry check (wayland-utils not installed)')
