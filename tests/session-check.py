#!/usr/bin/python3
"""Real wlroots headless session, native GTK clients, and actual key input."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

source = Path(__file__).resolve().parent.parent
binary = Path(os.environ.get('SIMPLEWM_TEST_BINARY', str(source / 'build/simplewm')))
def wait_for(fn, description, timeout=45):
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
    base = base.replace('background /usr/local/share/backgrounds/simpleos/simpleos-background.png fill', 'background none')
    base = base.replace('set $terminal simpleterm', 'set $terminal simplewm-test-terminal')
    config.write_text(base)
    helpers = root / 'bin'
    helpers.mkdir()
    notifications = root / 'notifications.log'
    notify = helpers / 'notify-send'
    notify.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$SIMPLEWM_TEST_NOTIFICATION_LOG"\n')
    notify.chmod(0o755)
    terminal_log = root / 'terminal-launches'
    terminal = helpers / 'simplewm-test-terminal'
    terminal.write_text('#!/bin/sh\nprintf "launch\\n" >> "$SIMPLEWM_TEST_TERMINAL_LOG"\n')
    terminal.chmod(0o755)
    env = os.environ.copy()
    env.update(HOME=str(home), XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless',
               WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman', GDK_BACKEND='wayland',
               GSETTINGS_BACKEND='memory', NO_AT_BRIDGE='1', XDG_CONFIG_HOME=str(home / '.config'),
               PATH=str(helpers) + os.pathsep + env['PATH'],
               SIMPLEWM_TEST_NOTIFICATION_LOG=str(notifications),
               SIMPLEWM_TEST_TERMINAL_LOG=str(terminal_log))
    env.pop('SIMPLEWM_NO_NOTIFICATIONS', None)
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
        assert status()['appearance']['image'] == ''
        assert status()['appearance']['font'] == 'Ubuntu Sans Mono 12'
        request('workspace 1'); request('workspace prev')
        assert status()['outputs'][0]['workspace'] == 1
        request('workspace 9'); request('workspace next')
        assert sorted(o['workspace'] for o in status()['outputs']) == [1, 9]
        request('workspace 1')
        for command, expected in (('workspace 2', 2), ('workspace next', 3),
                                  ('workspace prev', 2), ('workspace previous', 3),
                                  ('workspace 3', 3), ('workspace 1', 1)):
            assert request(command)['ok']
            assert next(o['workspace'] for o in status()['outputs'] if o['active']) == expected
        for shortcut, expected in (('Page_Down', 2), ('Page_Up', 1), ('2', 2), ('Escape', 1)):
            key('-M', 'logo', '-k', shortcut, '-m', 'logo')
            assert next(o['workspace'] for o in status()['outputs'] if o['active']) == expected
        assert not notifications.exists(), 'Workspace switches must not send notifications'

        # GTK portal dialogs export a parent across process boundaries.
        probe = root / 'foreign-dialog'
        flags = subprocess.check_output(['pkg-config','--cflags','--libs','gtk+-3.0'],text=True).split()
        subprocess.run(['cc', str(source/'tests/foreign-dialog.c'), '-o', str(probe), *flags],check=True)
        handle = root / 'foreign-handle'
        parent = subprocess.Popen([str(probe),'parent',str(handle)],env=env,stdout=log,stderr=log)
        children.append(parent)
        wait_for(lambda: handle.exists() and handle.stat().st_size, 'exported parent handle')
        wait_for(lambda: any(c['title']=='Portal Parent' for c in status()['clients']), 'portal parent mapped')
        dialog = subprocess.Popen([str(probe),'child',str(handle)],env=env,stdout=log,stderr=log)
        children.append(dialog)
        wait_for(lambda: any(c['title']=='Portal Dialog' and c['floating'] for c in status()['clients']), 'foreign dialog floats with its parent')
        dialog.terminate(); parent.terminate()
        dialog.wait(timeout=5); parent.wait(timeout=5)
        wait_for(lambda: not status()['clients'], 'portal probes closed')
        # A page key can reach the kernel just before Super. Rescue that chord,
        # but preserve bare taps, held paging, and key ordering in applications.
        keylog = root / 'page-events'
        paging = subprocess.Popen(['python3', str(source / 'tests/probe.py'),
                                  'Paging probe', str(keylog), '--releases'],
                                 env=env, stdout=log, stderr=log)
        children.append(paging)
        wait_for(lambda: any(c['title'] == 'Paging probe' for c in status()['clients']),
                 'paging probe mapped')
        def workspace():
            return next(o['workspace'] for o in status()['outputs'] if o['active'])
        def page_events():
            lines = keylog.read_text().splitlines() if keylog.exists() else []
            return [line for line in lines if line.split()[0] in ('65365', '65366') or
                    (line.startswith('release ') and line.split()[1] in ('65365', '65366'))]
        for gap in ('0', '5', '15'):
            delay = ('-s', gap) if gap != '0' else ()
            for shortcut, initial, expected in (('Page_Down', 1, 2), ('Page_Up', 2, 1)):
                request(f'workspace {initial}')
                key('-P', shortcut, *delay, '-M', 'logo', '-p', shortcut, '-m', 'logo')
                assert workspace() == expected, f'late Super+{shortcut} after {gap}ms was missed'
                request('workspace 1')
        assert not page_events(), 'rescued page press/release leaked into application'
        key('-P', 'Page_Down', '-s', '10', '-M', 'logo', '-m', 'logo', '-p', 'Page_Down')
        assert workspace() == 2, 'early Super release cancelled the rescued chord'
        request('workspace 1')
        assert not page_events(), 'early Super release leaked the consumed page release'
        for shortcut in ('Page_Up', 'Page_Down'):
            before = len(page_events())
            key('-k', shortcut)
            assert len(page_events()) == before + 2, 'bare page tap lost press or release'
            before = len(page_events())
            key('-P', shortcut, '-s', '80', '-p', shortcut)
            assert len(page_events()) == before + 2, 'bare held page lost press or release'
        before = len(page_events())
        key('-P', 'Page_Down', '-s', '80', '-M', 'logo',
            '-p', 'Page_Down', '-m', 'logo')
        assert workspace() == 1, 'Super outside the grace period stole ordinary paging'
        assert len(page_events()) == before + 2
        keylog.write_text('')
        key('-P', 'Page_Down', '-P', 'a', '-p', 'a', '-p', 'Page_Down')
        pressed = [line.split()[0] for line in keylog.read_text().splitlines()
                   if not line.startswith('release ')]
        assert pressed == ['65366', '97'], f'pending page reordered with typing: {pressed}'
        def terminal_launches():
            return len(terminal_log.read_text().splitlines()) if terminal_log.exists() else 0
        def enter_events():
            lines = keylog.read_text().splitlines() if keylog.exists() else []
            return [line for line in lines if line.split()[0] == '65293' or
                    (line.startswith('release ') and line.split()[1] == '65293')]
        for gap in ('0', '5', '15'):
            before = terminal_launches()
            delay = ('-s', gap) if gap != '0' else ()
            key('-P', 'Return', *delay, '-M', 'logo', '-p', 'Return', '-m', 'logo')
            wait_for(lambda: terminal_launches() == before + 1, f'late Super+Enter after {gap}ms')
        assert not enter_events(), 'rescued Enter press/release leaked into application'
        before = terminal_launches()
        key('-P', 'Return', '-s', '10', '-M', 'logo', '-m', 'logo', '-p', 'Return')
        wait_for(lambda: terminal_launches() == before + 1, 'early Super release with Enter')
        assert not enter_events(), 'early Super release leaked consumed Enter'
        before = terminal_launches()
        key('-M', 'logo', '-k', 'Return', '-m', 'logo')
        wait_for(lambda: terminal_launches() == before + 1, 'normal Super+Enter')
        for args in (('-k', 'Return'), ('-P', 'Return', '-s', '80', '-p', 'Return'),
                     ('-P', 'Return', '-s', '80', '-M', 'logo', '-p', 'Return', '-m', 'logo'),
                     ('-M', 'ctrl', '-k', 'Return', '-m', 'ctrl')):
            before = len(enter_events())
            launches = terminal_launches()
            key(*args)
            assert len(enter_events()) == before + 2, 'ordinary Enter lost press or release'
            assert terminal_launches() == launches, 'ordinary Enter launched the terminal'
        keylog.write_text('')
        key('-P', 'Return', '-P', 'a', '-p', 'a', '-p', 'Return')
        pressed = [line.split()[0] for line in keylog.read_text().splitlines()
                   if not line.startswith('release ')]
        assert pressed == ['65293', '97'], f'pending Enter reordered with typing: {pressed}'
        paging.terminate(); paging.wait(timeout=5)
        wait_for(lambda: not status()['clients'], 'paging probe closed')
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
        locked_workspace = workspace()
        key('-P', 'Page_Down', '-s', '10', '-M', 'logo', '-p', 'Page_Down', '-m', 'logo')
        assert workspace() == locked_workspace, 'late Super bypassed the session lock'
        launches = terminal_launches()
        key('-P', 'Return', '-s', '10', '-M', 'logo', '-p', 'Return', '-m', 'logo')
        assert terminal_launches() == launches, 'late Super+Enter bypassed the session lock'
        assert not request('exec touch /tmp/simplewm-lock-bypass')['ok']
        lock.kill(); lock.wait()
        assert status()['locked'], 'locker crash must remain locked'
        assert not notifications.exists(), 'Workspace shortcuts must not send notifications'
        print('OK native/Xwayland windows, real shortcuts, late-Super paging/Enter grace, ordinary key delivery/order, quiet bounded workspaces, maximize/restore, shifted workspace move, focus, layouts, clipboard, reload failure, output guard, IPC, screenshot, and secure lock')
    except BaseException:
        log.flush()
        print((root / 'session.log').read_text(errors='replace'), file=sys.stderr)
        raise
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
