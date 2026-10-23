#!/usr/bin/python3
import argparse
import json
import os
from pathlib import Path
import resource
import shlex
import signal
import subprocess
import tempfile

parser = argparse.ArgumentParser(description='Private wlroots interactive-resize regression and measurement fixture.')
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parent.parent,
                    help='compositor source tree (allows comparison with an unmodified checkout)')
parser.add_argument('--measure', action='store_true', help='record baseline behavior without asserting the resize fixes')
parser.add_argument('--output', type=Path)
parser.add_argument('--renderer', default='pixman', choices=['pixman', 'gles2'])
parser.add_argument('--application', choices=['gtk', 'simpleterm', 'firefox', 'x11'],
                    help='exercise a real application and a second GTK window')
parser.add_argument('--sanitize', action='store_true', help='enable AddressSanitizer and UndefinedBehaviorSanitizer')
args = parser.parse_args()
fixture = Path(__file__).resolve().parent
source = args.source.resolve()
with tempfile.TemporaryDirectory(prefix='simplewm-resize-run-') as temp:
    root = Path(temp)
    runtime = root / 'runtime'
    runtime.mkdir(mode=0o700)
    protocol = Path(subprocess.check_output([
        'pkg-config', '--variable=pkgdatadir', 'wayland-protocols'], text=True).strip()) / 'stable/xdg-shell/xdg-shell.xml'
    subprocess.run(['wayland-scanner', 'client-header', str(protocol), str(root / 'resize-client-protocol.h')], check=True)
    subprocess.run(['wayland-scanner', 'private-code', str(protocol), str(root / 'resize-client-protocol.c')], check=True)
    flags = shlex.split(subprocess.check_output([
        'pkg-config', '--cflags', '--libs', 'wlroots-0.18', 'wayland-server',
        'wayland-client', 'xkbcommon', 'libinput', 'xcb', 'xcb-icccm'], text=True))
    # UBSan makes GCC warn about the pre-existing die(fmt) wrapper in util.c.
    # Keep that warning visible without disabling any sanitizer checks.
    instrumentation = ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                       '-Wno-error=format-overflow'] if args.sanitize else []
    subprocess.run([
        'cc', '-O2', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
        '-DWLR_USE_UNSTABLE', '-DXWAYLAND', '-DVERSION="resize-test"',
        '-I' + str(source), '-I' + str(source / 'build'), '-I' + str(root),
        str(fixture / 'resize-check.c'), str(source / 'util.c'),
        str(root / 'resize-client-protocol.c'), *flags, *instrumentation, '-lm', '-o', str(root / 'resize-check'),
    ], check=True)
    env = os.environ | {
        'XDG_RUNTIME_DIR': str(runtime), 'WLR_BACKENDS': 'headless',
        'WLR_HEADLESS_OUTPUTS': '1', 'WLR_RENDERER': args.renderer, 'HOME': str(root),
        'XDG_CONFIG_HOME': str(root / '.config'), 'GSETTINGS_BACKEND': 'memory',
        'NO_AT_BRIDGE': '1',
        'GDK_BACKEND': 'wayland', 'MOZ_ENABLE_WAYLAND': '1',
    }
    env.pop('SIMPLEWM_SOCKET', None)
    if args.sanitize:
        env['ASAN_OPTIONS'] = 'detect_leaks=0:abort_on_error=1'
        env['UBSAN_OPTIONS'] = 'halt_on_error=1'
    command = [str(root / 'resize-check'), '--baseline' if args.measure else '--check']
    if args.application:
        profile = root / 'firefox-profile'
        profile.mkdir()
        document = root / 'resize.html'
        document.write_text('<title>Resize browser</title><style>p{font:20px sans-serif;max-width:90%}</style>'
                            '<p>A local document for live layout. This paragraph wraps as its window changes size.</p>')
        (profile / 'user.js').write_text(
            'user_pref("browser.shell.checkDefaultBrowser", false);\n'
            'user_pref("browser.startup.homepage_override.mstone", "ignore");\n'
            'user_pref("browser.aboutwelcome.enabled", false);\n'
            'user_pref("browser.startup.homepage", "about:blank");\n')
        env['SIMPLEWM_RESIZE_TEST_PROFILE'] = str(profile)
        env['SIMPLEWM_RESIZE_TEST_DOCUMENT'] = document.as_uri()
        command = ['dbus-run-session', '--', *command, args.application,
                   str(fixture / 'probe.py')]
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    proc = subprocess.Popen(command,
        cwd=source, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = proc.communicate(timeout=55)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        output, _ = proc.communicate(timeout=5)
        print(output, end='')
        raise
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)
    print(output, end='')
    if args.output:
        args.output.write_text(json.dumps({'source': str(source), 'renderer': args.renderer,
            'application': args.application, 'sanitized': args.sanitize, 'returncode': proc.returncode,
            'measurements': [json.loads(line) for line in output.splitlines() if line.startswith('{')],
            'log': output}, indent=2) + '\n')
    raise SystemExit(proc.returncode)
