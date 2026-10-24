#!/usr/bin/python3
"""Private regressions for fullscreen, monitor removal, stalled clients and resize geometry."""
import argparse
import json
import os
from pathlib import Path
import resource
import shlex
import signal
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parent.parent)
parser.add_argument('--measure', action='store_true', help='record old behavior without asserting fixes')
parser.add_argument('--renderer', choices=['pixman', 'gles2'], default='pixman')
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--output', type=Path)
parser.add_argument('--case', choices=['fullscreen', 'unplug_horizontal', 'unplug_vertical',
                                     'unplug_offset', 'limits', 'stalled', 'x11'])
args = parser.parse_args()
source = args.source.resolve()
fixture = Path(__file__).resolve().parent
results = []
with tempfile.TemporaryDirectory(prefix='simplewm-visual-run-') as temporary:
    root = Path(temporary)
    protocol = Path(subprocess.check_output([
        'pkg-config', '--variable=pkgdatadir', 'wayland-protocols'], text=True).strip()) / 'stable/xdg-shell/xdg-shell.xml'
    subprocess.run(['wayland-scanner', 'client-header', str(protocol), str(root / 'resize-client-protocol.h')], check=True)
    subprocess.run(['wayland-scanner', 'private-code', str(protocol), str(root / 'resize-client-protocol.c')], check=True)
    flags = shlex.split(subprocess.check_output([
        'pkg-config', '--cflags', '--libs', 'wlroots-0.18', 'wayland-server',
        'wayland-client', 'xkbcommon', 'libinput', 'xcb', 'xcb-icccm', 'pixman-1'], text=True))
    wrappers = ['waitid', 'wlr_scene_output_commit', 'wlr_xwayland_surface_configure']
    instrumentation = ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                       '-Wno-error=format-overflow'] if args.sanitize else []
    executable = root / 'visual-check'
    subprocess.run([
        'cc', '-O2', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror',
        '-Wno-unused-parameter', '-Wno-unused-function', '-DWLR_USE_UNSTABLE',
        '-DXWAYLAND', '-DVERSION="visual-test"', '-I' + str(source),
        '-I' + str(source / 'build'), '-I' + str(root), str(fixture / 'visual-check.c'),
        str(source / 'util.c'), str(root / 'resize-client-protocol.c'), *flags,
        *instrumentation, *['-Wl,--wrap=' + name for name in wrappers],
        '-lm', '-o', str(executable),
    ], check=True)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    for case in ([args.case] if args.case else [
            'fullscreen', 'unplug_horizontal', 'unplug_vertical', 'unplug_offset',
            'limits', 'stalled', 'x11']):
        private = root / case
        private.mkdir()
        runtime = private / 'runtime'
        runtime.mkdir(mode=0o700)
        env = os.environ | {
            'HOME': str(private), 'XDG_CONFIG_HOME': str(private / '.config'),
            'XDG_RUNTIME_DIR': str(runtime), 'WLR_BACKENDS': 'headless',
            'WLR_HEADLESS_OUTPUTS': '3', 'WLR_RENDERER': args.renderer,
            'GSETTINGS_BACKEND': 'memory', 'NO_AT_BRIDGE': '1',
        }
        env.pop('SIMPLEWM_SOCKET', None)
        if args.sanitize:
            env.update(ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        child = subprocess.Popen([str(executable), '--baseline' if args.measure else '--check', case],
                                 cwd=source, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            output, _ = child.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            output, _ = child.communicate(timeout=5)
            print(output, end='', flush=True)
            raise
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
        print(output, end='', flush=True)
        results.append({'case': case, 'returncode': child.returncode, 'log': output,
                        'measurements': [json.loads(line) for line in output.splitlines()
                                         if line.startswith('{')]})
        if child.returncode:
            break
if args.output:
    args.output.write_text(json.dumps({'source': str(source), 'renderer': args.renderer,
                                      'sanitized': args.sanitize, 'cases': results}, indent=2) + '\n')
raise SystemExit(next((case['returncode'] for case in results if case['returncode']), 0))
