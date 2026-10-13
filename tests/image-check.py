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
