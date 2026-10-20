#!/usr/bin/python3
"""Every shipped application shortcut is present in a fresh image's Bash config."""
from pathlib import Path
import runpy
import shlex
import subprocess
import tempfile

prepare = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'image/prepare-rootfs.py'))
suite = dict(pair.split(':') for pair in '''
browse:simplebrowse burn:simpleburn cal:simplecal clock:simpleclock
files:simplefiles flac:simpleflac game:simplegame mail:simplemail
news:simplenews note:simplenote pdf:simplepdf pod:simplepod
radio:simpleradio save:simplesave stats:simplestats
suite-uninstall:simplesuite-uninstall ver:simplever vis:simplevis words:simplewords
net:simplenet blue:simpleblue vol:simplevol serve:simpleserve
'''.split())
expected = suite | dict(term='simpleterm', check='simplecheck', trident='simpletrident')
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp); binary = root / 'usr/local/bin'; binary.mkdir(parents=True)
    manifest = root / 'usr/local/share/simplesuite/command-abbreviations'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(''.join(f'{short} {full}\n' for short, full in suite.items()))
    for full in expected.values():
        executable = binary / full
        executable.write_text('#!/bin/sh\nexit 0\n'); executable.chmod(0o755)
    bashrc = root / 'etc/skel/.bashrc'; bashrc.parent.mkdir(parents=True)
    bashrc.write_text("export PERSONAL_SETTING=preserved\n"
                      "alias mine='printf personal'\n"
                      "# BEGIN SimpleOS application aliases\n"
                      "alias vol='wrong-old-program'\n"
                      "# END SimpleOS application aliases\n")
    prepare['prepare_shell_aliases'](root)
    def shell_aliases():
        result = subprocess.run(['bash', '--noprofile', '--norc', '-c',
                                 '. "$1"; test "$PERSONAL_SETTING" = preserved; alias',
                                 'test', str(bashrc)], check=True, capture_output=True, text=True)
        return {line[6:].split('=', 1)[0]: shlex.split(line.split('=', 1)[1])[0]
                for line in result.stdout.splitlines()}
    actual = shell_aliases()
    assert actual.pop('mine') == 'printf personal'
    assert actual == {short: '/usr/local/bin/' + full for short, full in expected.items()}
    content = bashrc.read_text()
    prepare['prepare_shell_aliases'](root)
    assert bashrc.read_text() == content
    # The next build picks up a newly added Suite application without editing
    # a second alias list in the image builder.
    with manifest.open('a') as out:
        out.write('extra simpleextra\n')
    executable = binary / 'simpleextra'; executable.write_text('#!/bin/sh\nexit 0\n'); executable.chmod(0o755)
    prepare['prepare_shell_aliases'](root)
    assert shell_aliases()['extra'] == '/usr/local/bin/simpleextra'
    # Fail the image build rather than silently shipping a broken shortcut.
    content = bashrc.read_text(); (binary / 'simplevol').unlink()
    try:
        prepare['prepare_shell_aliases'](root)
        raise AssertionError('missing application was accepted')
    except RuntimeError as error:
        assert 'vol' in str(error)
    assert bashrc.read_text() == content
print('OK all 26 shipped aliases, manifest additions, repeated builds, personal shell settings and missing-target rejection')

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source, payload = root / 'source', root / 'payload'
    source.mkdir()
    # Historical snapshots still load; current sources must include the engine.
    prepare['verify_desktop_payload'](payload, source)
    (source / 'install-simpleplay.sh').write_text('#!/bin/sh\n')
    binary = payload / 'usr/local/bin'
    binary.mkdir(parents=True)
    for name in ('simpleplay', 'simpleterm'):
        path = binary / name
        path.write_text('#!/bin/sh\n'); path.chmod(0o755)
    try:
        prepare['verify_desktop_payload'](payload, source)
        raise AssertionError('image without the shared audio engine was accepted')
    except RuntimeError as error:
        assert 'simpleplay-core' in str(error)
    core = binary / 'simpleplay-core'
    core.write_text('#!/bin/sh\n'); core.chmod(0o755)
    for relative in ('applications/org.simplesuite.Simpleplay.desktop',
                     'applications/org.simplesuite.Simpleterm.desktop',
                     'simplesuite/simpleplay/simpleplay.svg', 'simplesuite/simpleplay/SIMPLEPLAY.md',
                     'simplesuite/simpleterm/simpleterm.png', 'simplesuite/simpleterm/bashrc',
                     'simplesuite/simpleterm/SIMPLETERM.md'):
        path = payload / 'usr/local/share' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('staged asset\n')
    prepare['verify_desktop_payload'](payload, source)
    (payload / 'usr/local/share/simplesuite/simpleterm/bashrc').unlink()
    try:
        prepare['verify_desktop_payload'](payload, source)
        raise AssertionError('image without terminal assets was accepted')
    except RuntimeError as error:
        assert 'bashrc' in str(error)
print('OK fresh images require SimplePlay, its core, SimpleTerm and their desktop assets')

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source, payload = root / 'source', root / 'payload'
    source.mkdir()
    (source / 'Makefile').write_text('install-full:\n')
    local = payload / 'usr/local'
    data = local / 'share/simplesuite'; data.mkdir(parents=True)
    (data / 'install-manifest').write_text('payload_scope=full\ninstalled_programs=simplearcade\n')
    (local / 'bin').mkdir()
    try:
        prepare['verify_desktop_payload'](payload, source)
        raise AssertionError('a newly included application was not checked')
    except RuntimeError as error:
        assert 'simplearcade' in str(error)
    (local / 'bin/simplearcade').write_text('#!/bin/sh\n')
    (local / 'bin/simplearcade').chmod(0o755)
    prepare['verify_desktop_payload'](payload, source)
print('OK complete Suite images verify new applications from generated installation output')
