#!/usr/bin/python3
"""Real wlroots headless session, native GTK clients, and actual key input."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

source = Path(__file__).resolve().parent.parent
binary = Path(os.environ.get('SIMPLEWM_TEST_BINARY', str(source / 'build/simplewm')))
def wait_for(fn, description, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = fn()
        if result:
            return result
        time.sleep(.08)
    raise AssertionError(description)

with tempfile.TemporaryDirectory(prefix='simplewm-session-') as temp:
    root = Path(temp)
    runtime = root / 'runtime'
    runtime.mkdir(mode=0o700)
    home = root / 'home'
    home.mkdir()
    config = root / 'config'
    base = (source / 'config').read_text().replace('exec simplewm-services', '# services disabled in isolated tests')
    base = base.replace('background /usr/local/share/backgrounds/simpleos/simpleos-background.png fit', 'background none')
    config.write_text(base)
    env = os.environ.copy()
    env.update(HOME=str(home), XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless',
               WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman', GDK_BACKEND='wayland',
               GSETTINGS_BACKEND='memory', NO_AT_BRIDGE='1', XDG_CONFIG_HOME=str(home / '.config'))
    env.pop('DISPLAY', None)
    env.pop('WAYLAND_DISPLAY', None)
    log = (root / 'session.log').open('w')
    wm = subprocess.Popen([str(binary), '-c', str(config)], env=env, stdout=log, stderr=log)
    children = []
    try:
        endpoint = wait_for(lambda: next(runtime.glob('simplewm-*.ctl'), None), 'compositor did not start')
        display = endpoint.name[len('simplewm-'):-len('.ctl')]
        env['WAYLAND_DISPLAY'] = display
        env['SIMPLEWM_SOCKET'] = str(endpoint)
        def request(command):
            with socket.socket(socket.AF_UNIX) as peer:
                peer.settimeout(4)
                peer.connect(str(endpoint))
                peer.sendall((command + '\n').encode())
                parts = []
                while True:
                    chunk = peer.recv(65536)
                    if not chunk:
                        break
                    parts.append(chunk)
            return json.loads(b''.join(parts))
        def status(): return request('status')
        def key(*args):
            subprocess.run(['wtype', *args], env=env, check=True, timeout=5)
            time.sleep(.15)
        def launch(title, backend='wayland'):
            appenv = env | {'GDK_BACKEND': backend}
            if backend == 'x11':
                # Xwayland display was exported inside the compositor; a test
                # command launched through IPC receives that environment.
                request(f'exec GDK_BACKEND=x11 python3 {source}/tests/probe.py {title}')
                return
            child = subprocess.Popen(['python3', str(source / 'tests/probe.py'), title], env=appenv, stdout=log, stderr=log)
            children.append(child)
        def active(): return next(c for c in status()['clients'] if c['active'])
        assert len(status()['outputs']) == 2
        launch('Writer')
        wait_for(lambda: len(status()['clients']) == 1, 'first native window')
        one = active()
        assert (one['width'], one['height']) == (1280, 720), one
        launch('Reference')
        wait_for(lambda: len(status()['clients']) == 2, 'second native window')
        two = status()['clients']
        assert all(c['width'] < 640 for c in two), two
        assert len({c['x'] for c in two}) == 2
        before = active()
        key('-M', 'ctrl', '-k', 'Up', '-m', 'ctrl')
        assert active()['maximized'] and active()['width'] == 1280
        key('-M', 'ctrl', '-k', 'Down', '-m', 'ctrl')
        restored = active()
        assert not restored['maximized'] and restored['width'] == before['width'], restored
        key('-M', 'alt', '-k', 'Tab', '-m', 'alt')
        assert active()['id'] != before['id']
        key('-M', 'logo', '-M', 'shift', '-k', '2', '-m', 'shift', '-m', 'logo')
        assert sum(c['visible'] for c in status()['clients']) == 1
        key('-M', 'logo', '-k', '2', '-m', 'logo')
        assert active()['workspace'] == 2 and active()['visible']
        key('-M', 'logo', '-k', 'f', '-m', 'logo')
        assert active()['fullscreen']
        key('-M', 'ctrl', '-k', 'Down', '-m', 'ctrl')
        assert not active()['fullscreen']
        request('floating')
        assert active()['floating']
        floating = active()
        request('maximize'); request('restore')
        assert active()['floating'] and active()['width'] == floating['width']
        request('floating')
        text = 'Prose — naïve, café.\nA second line.\n'
        subprocess.run(['wl-copy'], input=text.encode(), env=env, check=True)
        assert subprocess.check_output(['wl-paste', '--no-newline'], env=env).decode() == text
        subprocess.run(['wl-copy', '--primary'], input=text.encode(), env=env, check=True)
        assert subprocess.check_output(['wl-paste', '--primary', '--no-newline'], env=env).decode() == text
        request('workspace 1')
        launch('XWindow', 'x11')
        wait_for(lambda: any(c['title'] == 'XWindow' for c in status()['clients']), 'Xwayland client')
        request('layout stack')
        assert next(o for o in status()['outputs'] if o['active'])['layout'] == 'stack'
        request('layout paper')
        assert next(o for o in status()['outputs'] if o['active'])['layout'] == 'paper'
        config.write_text(base + '\ngaps inner 18\n')
        assert request('reload')['ok']
        old = [(c['id'], c['x'], c['width']) for c in status()['clients']]
        config.write_text(base + '\ngaps inner -2\n')
        assert not request('reload')['ok']
        assert old == [(c['id'], c['x'], c['width']) for c in status()['clients']]
        config.write_text(base + '\noutput * enabled=no\n')
        assert not request('reload')['ok']
        config.write_text(base)
        assert request('reload')['ok']
        # A malformed/incomplete IPC client must never block typing or rendering.
        slow = socket.socket(socket.AF_UNIX); slow.connect(str(endpoint)); slow.sendall(b'sta')
        assert status()['ok']; slow.close()
        subprocess.run(['grim', str(root / 'desktop.png')], env=env, check=True)
        assert (root / 'desktop.png').stat().st_size > 1000
        key('-M', 'logo', '-k', 'z', '-m', 'logo')
        wait_for(lambda: len(status()['clients']) == 2, 'close shortcut')
        lock = subprocess.Popen(['swaylock', '--color', '101313'], env=env, stdout=log, stderr=log)
        children.append(lock)
        wait_for(lambda: status()['locked'], 'secure session lock')
        assert not request('exec touch /tmp/simplewm-lock-bypass')['ok']
        lock.kill(); lock.wait()
        assert status()['locked'], 'locker crash must remain locked'
        print('OK native/Xwayland windows, real shortcuts, maximize/restore, shifted workspace move, focus, layouts, clipboard, reload failure, output guard, IPC, screenshot, and secure lock')
    finally:
        log.flush()
        (source / 'build/session-check.log').write_text((root / 'session.log').read_text())
        if (root / 'desktop.png').exists():
            import shutil
            shutil.copy2(root / 'desktop.png', source / 'build/session-check.png')
        for child in children:
            if child.poll() is None:
                child.terminate()
        wm.terminate()
        try: wm.wait(timeout=5)
        except subprocess.TimeoutExpired: wm.kill(); wm.wait()
        log.close()
        if wm.returncode not in (0, -signal.SIGTERM):
            print((root / 'session.log').read_text())
            raise AssertionError(f'compositor exited {wm.returncode}')
