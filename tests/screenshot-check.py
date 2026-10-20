#!/usr/bin/python3
"""Exercise concurrent screenshot requests without touching the desktop."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

source = Path(__file__).resolve().parent.parent
script = source / 'scripts/simplewm-screenshot'


def wait_for(predicate, description):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError(description)


with tempfile.TemporaryDirectory(prefix='simplewm-screenshot-') as temp:
    root = Path(temp)
    runtime = root / 'runtime'
    runtime.mkdir(mode=0o700)
    helpers = root / 'bin'
    helpers.mkdir()
    pictures = root / 'Pictures with spaces'
    events = root / 'events'
    release = root / 'release'
    clipboard = root / 'clipboard.pid'
    helper = '''#!/usr/bin/python3
import os
from pathlib import Path
import signal
import sys
import time
root = Path(os.environ['SIMPLEWM_SCREENSHOT_TEST'])
name = Path(sys.argv[0]).name
with (root / 'events').open('a') as events:
    events.write(name + '\\n')
if name == 'slurp':
    while not (root / 'release').exists():
        time.sleep(.02)
    action = (root / 'release').read_text()
    if action == 'cancel':
        sys.exit(1)
    print('0,0 10x10')
elif name == 'xdg-user-dir':
    print(root / 'Pictures with spaces')
elif name == 'grim':
    Path(sys.argv[-1]).write_bytes(b'test PNG')
elif name == 'wl-copy':
    assert sys.stdin.buffer.read() == b'test PNG'
    # Like wl-copy, leave a clipboard owner alive after this command returns.
    # It deliberately inherits every open descriptor from the shell helper.
    if os.fork() == 0:
        (root / 'clipboard.pid').write_text(str(os.getpid()))
        while True:
            signal.pause()
'''
    for name in ('slurp', 'xdg-user-dir', 'grim', 'wl-copy', 'notify-send'):
        path = helpers / name
        path.write_text(helper)
        path.chmod(0o755)
    env = os.environ | {
        'PATH': str(helpers) + os.pathsep + os.environ['PATH'],
        'HOME': str(root), 'XDG_RUNTIME_DIR': str(runtime),
        'WAYLAND_DISPLAY': 'wayland-test', 'SIMPLEWM_SCREENSHOT_TEST': str(root),
    }
    children = []
    clipboard_pids = []

    def launches(name):
        return events.read_text().splitlines().count(name) if events.exists() else 0

    def start(mode='region'):
        child = subprocess.Popen([str(script), mode], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        children.append(child)
        return child

    def finish(child):
        assert child.wait(timeout=5) == 0

    try:
        first = start()
        wait_for(lambda: launches('slurp') == 1, 'first selector did not start')
        repeated = [start() for _ in range(12)] + [start('full')]
        wait_for(lambda: all(child.poll() is not None for child in repeated),
                 'duplicate requests waited instead of returning immediately')
        assert all(child.returncode == 0 for child in repeated)
        assert launches('slurp') == 1, 'Print Screen stacked multiple selectors'
        assert launches('grim') == 0, 'duplicate request captured the active overlay'

        release.write_text('cancel')
        finish(first)
        assert launches('grim') == 0, 'canceling the selector captured an image'
        release.unlink()

        # Cancellation must release the guard, with no stale lockfile cleanup.
        second = start()
        wait_for(lambda: launches('slurp') == 2, 'selector stayed locked after cancellation')
        release.write_text('capture')
        finish(second)
        wait_for(clipboard.exists, 'clipboard owner did not start')
        clipboard_pids.append(int(clipboard.read_text()))
        os.kill(clipboard_pids[-1], 0)
        assert launches('grim') == 1

        # The background clipboard owner must not retain the screenshot lock.
        clipboard.unlink()
        finish(start('full'))
        wait_for(clipboard.exists, 'full capture stayed locked by clipboard owner')
        clipboard_pids.append(int(clipboard.read_text()))
        assert launches('slurp') == 2, 'full screenshot started a selector'
        assert launches('grim') == 2
        assert len(list((pictures / 'Screenshots').glob('*.png'))) == 2

        invalid = subprocess.run([str(script), 'invalid'], env=env,
                                 capture_output=True, timeout=5)
        assert invalid.returncode == 2 and b'Usage:' in invalid.stderr
        print('OK one selector for repeated presses, cancellation, capture, and clipboard lock release')
    finally:
        release.write_text('cancel')
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
