#!/usr/bin/python3
"""Theme/blur, real renderer, input, staged install and isolated session locking."""
import contextlib
import json
import os
from pathlib import Path
import runpy
import shlex
import signal
import socket
import subprocess
import tempfile
import time
from unittest.mock import patch
from PIL import Image, ImageChops

repo = Path(__file__).resolve().parent.parent
lock = runpy.run_path(str(repo / 'scripts/simplewm-lock'))


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, timeout=60, **kwargs)


def wait_for(fn, message, timeout=12):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        value = fn()
        if value:
            return value
        time.sleep(.04)
    raise AssertionError(message)


def compile_program(target, sources):
    modules = ['wayland-client', 'xkbcommon', 'cairo']
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', *modules], text=True))
    run(['cc', '-std=c11', '-D_POSIX_C_SOURCE=200809L', '-Wall', '-Wextra', '-Werror',
         '-Wno-unused-parameter', '-I' + str(repo / 'lock/include'), '-I' + str(repo / 'build'),
         *sources, *flags, *shlex.split(os.environ.get('LDFLAGS', '')), '-lm', '-o', target])


with tempfile.TemporaryDirectory(prefix='simplewm-lock-check-') as temporary:
    root = Path(temporary)
    # Includes, variables, spaces, wallpaper-only changes and the active IPC
    # settings must all select the wallpaper currently used by the compositor.
    home = root / 'home'; home.mkdir()
    confdir = home / '.config/simplewm'; confdir.mkdir(parents=True)
    conf = confdir / 'config'
    conf.write_text('set $wall "a wallpaper.png"\nbackground $wall fill\n'
                    'monospace_font "DejaVu Sans Mono 12"\ninclude palette*.conf\n')
    (confdir / 'palette-a.conf').write_text('background "another image.png" fit\ncolor background #f0e8db\n')
    (confdir / 'palette-b.conf').write_text('color focused #c9171d\n')
    palette = confdir / 'palette.json'
    palette.write_text(json.dumps({'background': '#050303', 'surface': '#161414'}))
    with patch.dict(os.environ, {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config')}):
        old = lock['appearance'](current={'config': str(conf)})
        assert old['image'] == str(confdir / 'another image.png') and old['mode'] == 'fit'
        assert old['font'] == 'DejaVu Sans Mono' and old['foreground'] == '#000000'
        active = lock['appearance'](current={'config': str(conf), 'appearance': {
            'image': '/active/wallpaper.png', 'mode': 'tile', 'font': 'monospace 15',
            'background': '#050303', 'accent': '#ff0000'}})
        assert active['image'] == '/active/wallpaper.png' and active['mode'] == 'tile'
        assert active['foreground'] == '#ffffff' and active['font'] == 'monospace'
    for base in ('#000000', '#ffffff', '#808080', '#ff0000', '#00ff00', '#0000ff', '#f0e8db'):
        colors = lock['readable_colors'](lock['DEFAULTS'] | {'background': base, 'surface': base})
        fg = lock['rgb'](colors['foreground']); bg = lock['rgb'](colors['background'])
        for extreme in ((0, 0, 0), (255, 255, 255)):
            tinted = lock['mix'](extreme, bg, lock['TINT'])
            assert lock['contrast'](fg, tinted) >= 7, (base, colors)
            for key, minimum in (('muted', 4.5), ('accent', 3), ('error', 4.5)):
                assert lock['contrast'](lock['rgb'](colors[key]), tinted) >= minimum, (base, key, colors)
        assert lock['contrast'](lock['rgb'](colors['surface']), fg) >= 7
    wallpaper = root / 'wallpaper with $(literal) and spaces.png'
    original = Image.new('RGB', (800, 450), 'white')
    for x in range(400):
        for y in range(450): original.putpixel((x, y), (0, 0, 0))
    original.save(wallpaper)
    cache = root / 'cache'
    blur = lock['blurred_wallpaper'](str(wallpaper), cache)
    assert blur and (blur.stat().st_mode & 0o777) == 0o600
    assert (cache.stat().st_mode & 0o777) == 0o700
    assert lock['blurred_wallpaper'](str(wallpaper), cache) == blur
    blurred = Image.open(blur)
    assert blurred.size == original.size and 20 < blurred.getpixel((400, 225))[0] < 235
    original.paste('red', (0, 0, 800, 450)); original.save(wallpaper)
    assert lock['blurred_wallpaper'](str(wallpaper), cache) != blur
    assert lock['blurred_wallpaper'](str(root / 'missing.png'), cache) is None
    conf.write_text('background none\n')
    assert lock['config_appearance'](conf)['image'] == ''
    print('OK effective theme/old compositor compatibility, wallpaper modes, contrast extremes, and private blur cache')

    run(['make', '-C', repo, 'lock-preview'], stdout=subprocess.DEVNULL)
    for mode in ('fill', 'fit', 'center', 'stretch', 'tile'):
        for state in ('idle', 'typing', 'wrong', 'checking'):
            path = root / f'{mode}-{state}.png'
            run([repo / 'build/simplewm-lock-preview', '--image', blur, '--mode', mode,
                 '--state', state, '--count', '1023', '--width', '320', '--height', '240', path])
            assert Image.open(path).size == (320, 240)
    input_test = root / 'input-check'
    compile_program(input_test, [repo / ('lock/' + file) for file in ('password.c', 'unicode.c', 'loop.c', 'log.c')]
                    + [repo / 'tests/lock-input-check.c'])
    run([input_test])

    stage = root / 'stage'
    run(['make', '-C', repo, 'DESTDIR=' + str(stage), 'PREFIX=/usr/local', 'install'], stdout=subprocess.DEVNULL)
    installed = stage / 'usr/local'
    assert os.access(installed / 'bin/simplewm-lock', os.X_OK)
    assert os.access(installed / 'bin/simplewm-lock-client', os.X_OK)
    assert not (installed / 'bin/simplewm-lock-preview').exists()
    run([installed / 'bin/simplewm-lock-client', '--version'])
    # The installed versioned updater validates the complete current payload,
    # including its libexec engine. The historical r2 validator predates that
    # payload format; bootstrap handoff is covered by update-handoff-check.py.
    updater = runpy.run_path(str(repo / 'scripts/simpleupdate'))
    updater['validate_local'](installed)
    for program in ('bin/simplewm', 'bin/simplewm-lock-client'):
        linkage = run(['ldd', installed / program], capture_output=True, text=True)
        assert 'not found' not in linkage.stdout
    print('OK native renderer on small outputs, input, staged install and runtime linkage')

    # Exercise the full production lock lifecycle without using a real password.
    # Success and rejection then run through a separately linked fixture backend.
    fixture = root / 'fixture-lock-client'
    sources = [p for p in sorted((repo / 'lock').glob('*.c')) if p.name not in ('pam.c', 'preview.c')]
    compile_program(fixture, sources + [repo / 'tests/lock-auth-fixture.c', repo / 'build/ext-session-lock-v1-protocol.c'])
    runtime = root / 'runtime'; runtime.mkdir(mode=0o700)
    config = root / 'session.conf'
    config.write_text('background none\nmonospace_font "DejaVu Sans Mono 13"\n'
                      'output HEADLESS-2 scale=2 position=auto mode=preferred enabled=yes\n')
    env = os.environ | {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config'),
        'XDG_CACHE_HOME': str(root / 'desktop-cache'), 'XDG_RUNTIME_DIR': str(runtime),
        'WLR_BACKENDS': 'headless', 'WLR_HEADLESS_OUTPUTS': '2', 'WLR_RENDERER': 'pixman',
        'GSETTINGS_BACKEND': 'memory', 'SIMPLEWM_NO_NOTIFICATIONS': '1'}
    for name in ('WAYLAND_DISPLAY', 'SIMPLEWM_SOCKET', 'DISPLAY'): env.pop(name, None)
    children = []
    transcript = root / 'session.log'
    with transcript.open('w') as output:
        wm = subprocess.Popen([repo / 'build/simplewm', '-c', config], env=env, stdout=output, stderr=output)
        try:
            endpoint = wait_for(lambda: next(runtime.glob('simplewm-*.ctl'), None), 'headless compositor did not start')
            env['SIMPLEWM_SOCKET'] = str(endpoint)
            env['WAYLAND_DISPLAY'] = endpoint.name[len('simplewm-'):-len('.ctl')]

            def request(command):
                with socket.socket(socket.AF_UNIX) as peer:
                    peer.settimeout(3); peer.connect(str(endpoint)); peer.sendall((command + '\n').encode())
                    data = bytearray()
                    while True:
                        part = peer.recv(65536)
                        if not part: break
                        data.extend(part)
                return json.loads(data)

            def status(): return request('status')

            def key(*args): run(['wtype', *args], env=env)

            def screenshot(name, monitor='HEADLESS-1'):
                path = repo / 'build' / ('lock-session-' + name + '.png')
                run(['grim', '-o', monitor, path], env=env)
                return Image.open(path).convert('RGB')

            assert status()['appearance']['image'] == ''
            assert status()['appearance']['font'] == 'DejaVu Sans Mono 13'
            assert len(status()['outputs']) == 2
            key('-s', '100')  # Establish the headless seat's keyboard capability.
            production = subprocess.Popen([installed / 'bin/simplewm-lock', '--foreground'],
                env=env, stdout=output, stderr=output, start_new_session=True)
            children.append(production)
            wait_for(lambda: status()['locked'], 'production client did not acquire session lock')
            idle = wait_for(lambda: (picture if picture.getextrema()[0][1] > 230 else None)
                if (picture := screenshot('idle')) else None, 'initial clock was not rendered')
            screenshot('scaled', 'HEADLESS-2')
            assert not request('exec touch ' + str(root / 'bypass'))['ok']
            assert not (root / 'bypass').exists()
            # Duplicate idle/suspend requests must return after the established lock.
            run([installed / 'bin/simplewm-lock'], env=env, stdout=output, stderr=output)
            key('x'); time.sleep(.1)
            typed = screenshot('typed')
            assert ImageChops.difference(idle, typed).getbbox(), 'first character must reveal the field'
            key('-k', 'Escape'); time.sleep(.1)
            escaped = screenshot('escaped')
            # Compare the entry's edge, avoiding the clock changing minute.
            w, h = idle.size
            edge = (w // 2 - 182, h // 2 - 28, w // 2 - 176, h // 2 + 28)
            assert ImageChops.difference(idle.crop(edge), escaped.crop(edge)).getbbox() is None
            os.killpg(production.pid, signal.SIGTERM); production.wait(timeout=5)
            wait_for(lambda: status()['locked'], 'a crashed client must leave the session locked')
            wait_for(lambda: not status()['lock_client'], 'crashed client was not released')
            assert not request('workspace 2')['ok']

            ready_r, ready_w = os.pipe()
            client = subprocess.Popen([fixture, '--font', 'DejaVu Sans Mono', '--ready-fd', str(ready_w)],
                env=env, pass_fds=(ready_w,), stdout=output, stderr=output, start_new_session=True)
            children.append(client); os.close(ready_w)
            with os.fdopen(ready_r, 'rb') as ready: assert ready.read(1) == b'\n'
            time.sleep(.15)
            baseline = screenshot('fixture-idle')
            key('wrong'); key('-k', 'Return'); time.sleep(.1)
            screenshot('checking')
            time.sleep(.5)
            rejected = screenshot('wrong')
            assert client.poll() is None and status()['locked']
            assert ImageChops.difference(baseline, rejected).getbbox()
            key('headless-café'); key('-k', 'Return')
            client.wait(timeout=6)
            assert client.returncode == 0
            wait_for(lambda: not status()['locked'], 'successful UTF-8 authentication did not unlock')
            assert request('workspace 2')['ok']
            # The next lock can replace a client that died while locked, securely.
            client = subprocess.Popen([fixture], env=env, stdout=output, stderr=output, start_new_session=True)
            children.append(client)
            wait_for(lambda: status()['locked'], 'relocking failed')
            os.killpg(client.pid, signal.SIGKILL); client.wait(timeout=5)
            assert status()['locked'] and not request('workspace 1')['ok']
            print('OK production readiness/duplicate lock, first input, Escape, scaled outputs, crash containment, rejection and UTF-8 unlock')
        except BaseException:
            output.flush(); print(transcript.read_text(), flush=True)
            raise
        finally:
            for child in children:
                with contextlib.suppress(ProcessLookupError): os.killpg(child.pid, signal.SIGTERM)
            wm.terminate()
            try: wm.wait(timeout=5)
            except subprocess.TimeoutExpired: wm.kill(); wm.wait()
            output.flush()
            (repo / 'build/lock-session-check.log').write_text(transcript.read_text())
            for child in children:
                with contextlib.suppress(subprocess.TimeoutExpired): child.wait(timeout=3)
print('OK lock-screen regression suite')
