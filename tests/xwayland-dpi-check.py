#!/usr/bin/python3
"""Verify Xwayland's screen DPI and resources in private headless sessions."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import tempfile
import time

source = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resources', type=Path, help='test with an existing xrdb -query snapshot')
args = parser.parse_args()
resources = args.resources.read_text() if args.resources else '''Xft.dpi: 104
Xft.antialias: 1
Xft.hinting: 1
Xft.hintstyle: hintslight
Xft.rgba: rgb
Xft.lcdfilter: lcddefault
XTerm*faceName: Ubuntu Sans Mono
XTerm*faceSize: 12
'''


def wait_for(predicate, description):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError(description)


def check_session(override, dpi):
    with tempfile.TemporaryDirectory(prefix='simplewm-xwayland-dpi-') as temp:
        root = Path(temp)
        runtime = root / 'runtime'
        runtime.mkdir(mode=0o700)
        helpers = root / 'bin'
        helpers.mkdir()
        # No desktop services or toolkit writes are needed to test X11 metadata.
        style = helpers / 'simplewm-style'
        style.write_text('#!/bin/sh\nexit 0\n')
        style.chmod(0o755)
        config = root / 'config'
        config.write_text('background none\noutput * mode=1920x1200 scale=1\n')
        env = os.environ | {
            'HOME': str(root), 'XDG_CONFIG_HOME': str(root / '.config'),
            'XDG_RUNTIME_DIR': str(runtime), 'WLR_BACKENDS': 'headless',
            'WLR_HEADLESS_OUTPUTS': '1', 'WLR_RENDERER': 'pixman',
            'GSETTINGS_BACKEND': 'memory',
            'PATH': os.pathsep.join((str(helpers), str(source / 'scripts'), os.environ['PATH'])),
        }
        for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'SIMPLEWM_SOCKET', 'WLR_XWAYLAND'):
            env.pop(name, None)
        if override:
            env['WLR_XWAYLAND'] = override
        with (root / 'session.log').open('w+') as log:
            wm = subprocess.Popen([str(source / 'build/simplewm'), '-c', str(config)],
                                  env=env, stdout=log, stderr=log)
            try:
                endpoint = wait_for(lambda: next(runtime.glob('simplewm-*.ctl'), None),
                                    'private compositor did not start')

                def request(command):
                    with socket.socket(socket.AF_UNIX) as peer:
                        peer.settimeout(5)
                        peer.connect(str(endpoint))
                        peer.sendall((command + '\n').encode())
                        data = b''
                        while chunk := peer.recv(65536):
                            data += chunk
                    return json.loads(data)

                display = root / 'display'
                assert request('exec printenv DISPLAY > ' + shlex.quote(str(display)))['ok']
                wait_for(lambda: display.exists() and display.stat().st_size, 'X11 display export')
                env['DISPLAY'] = display.read_text().strip()

                def run(*command, **kwargs):
                    return subprocess.check_output(command, env=env, text=True, timeout=15, **kwargs)

                def check_dimensions(width, height):
                    info = run('xdpyinfo')
                    assert re.search(rf'dimensions:\s+{width}x{height} pixels', info), info
                    assert re.search(rf'resolution:\s+{dpi}x{dpi} dots per inch', info), info
                    print('\n'.join(line.strip() for line in info.splitlines()
                                    if 'dimensions:' in line or 'resolution:' in line))
                    output, = request('status')['outputs']
                    assert (output['width'], output['height'], output['scale']) == (width, height, 1)

                check_dimensions(1920, 1200)
                # The launcher must not set any resources itself.
                assert run('xrdb', '-query') == ''
                run('xrdb', '-nocpp', '-retain', '-load', input=resources)
                expected = run('xrdb', '-query')
                assert re.search(r'^Xft\.dpi:\s+104$', expected, re.MULTILINE), expected
                print(expected, end='')
                # Both RandR attempts previously returned success without fixing DPI.
                run('xrandr', '--dpi', '104')
                run('xrandr', '--fb', '1920x1200', '--dpi', '104')
                check_dimensions(1920, 1200)
                for width, height in ((1280, 800), (1920, 1200)):
                    config.write_text(f'background none\noutput * mode={width}x{height} scale=1\n')
                    assert request('reload')['ok']
                    wait_for(lambda: request('status')['outputs'][0]['width'] == width,
                             'Wayland output mode change')
                    # Synchronize the Xwayland connection with Wayland output events.
                    wait_for(lambda: f'{width}x{height} pixels' in run('xdpyinfo'),
                             'Xwayland output mode change')
                    check_dimensions(width, height)
                    assert run('xrdb', '-query') == expected, 'X resources changed'
                print(f'OK {override or "default launcher"}: {dpi}x{dpi} DPI, unchanged resources and Wayland scale')
            except BaseException:
                log.flush()
                log.seek(0)
                print(log.read(), end='')
                raise
            finally:
                wm.send_signal(signal.SIGTERM)
                wm.wait(timeout=5)


check_session(None, 104)
check_session('Xwayland', 96)
