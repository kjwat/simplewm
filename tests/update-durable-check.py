#!/usr/bin/python3
"""Real source files and abrupt process exits, including interrupted recovery."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'updater'))
import transaction as tx


with tempfile.TemporaryDirectory(prefix='durable-update-') as temp:
    base = Path(temp); prefix = base / 'local'; stage = base / 'stage'
    for root in (prefix, stage):
        (root / 'bin').mkdir(parents=True)
        (root / 'share/simplewm').mkdir(parents=True)
        (root / 'bin/a').write_text('old' if root == prefix else 'new')
        (root / 'bin/b').write_text('old' if root == prefix else 'new')
        (root / 'share/simplewm/config').write_text('packaged')
    (prefix / 'share/simpleupdate').mkdir()
    tx.write_json(prefix / 'share/simpleupdate/owned.json', tx.inventory(prefix))
    (prefix / 'share/simplewm/config').write_text('personal settings')
    (stage / 'share/simplewm/config').write_text('new packaged defaults')
    (prefix / 'bin/personal-tool').write_text('my script')
    home = base / 'home/writing'; home.mkdir(parents=True)
    (home / 'book').write_text('manuscript')
    transaction = tx.Transaction(prefix)
    replace = os.replace
    def failing(source, destination):
        if str(source).endswith('/new/bin/b'):
            raise OSError('injected installation failure')
        return replace(source, destination)
    with patch.object(tx.os, 'replace', side_effect=failing):
        try:
            transaction.install([stage], lambda: None)
            raise AssertionError('failure did not stop installation')
        except OSError:
            pass
    assert (prefix / 'bin/a').read_text() == (prefix / 'bin/b').read_text() == 'old'
    script = base / 'interrupt.py'
    script.write_text('''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import transaction as tx
prefix,stage=map(Path,sys.argv[2:4])
real=os.replace
def cut(source,target):
    real(source,target)
    if '/new/bin/a' in str(source) or '.simpleupdate-restore-' in str(source):os._exit(91)
os.replace=cut
t=tx.Transaction(prefix)
if sys.argv[4]=='install':t.install([stage],lambda:None)
else:t.recover()
''')
    command = [sys.executable, str(script), str(ROOT / 'updater'), str(prefix), str(stage)]
    assert subprocess.run(command + ['install']).returncode == 91
    assert (prefix / 'bin/a').read_text() == 'new'
    assert subprocess.run(command + ['recover']).returncode == 91
    transaction.recover()
    assert (prefix / 'bin/a').read_text() == (prefix / 'bin/b').read_text() == 'old'
    transaction.install([stage], lambda: None)
    assert (prefix / 'bin/a').read_text() == 'new'
    assert transaction.retained.exists()
    transaction.rollback()
    assert (prefix / 'bin/a').read_text() == 'old'
    assert (prefix / 'share/simplewm/config').read_text() == 'personal settings'
    assert (prefix / 'bin/personal-tool').read_text() == 'my script'
    assert (home / 'book').read_text() == 'manuscript'
    print('OK partial install, abrupt termination, repeated recovery, retained rollback and personal-file preservation')
    (stage / 'bin/escape').symlink_to('/etc/shadow')
    try:
        transaction.install([stage], lambda: None)
        raise AssertionError('external symlink accepted')
    except RuntimeError as error:
        assert 'link' in str(error)
    assert (prefix / 'bin/a').read_text() == 'old'
    print('OK escaping staging link rejected without changing installed programs')

with tempfile.TemporaryDirectory(prefix='rebuilt-update-') as temp:
    base = Path(temp); prefix = base / 'local'; stage = base / 'stage'
    for root in (prefix, stage):
        (root / 'bin').mkdir(parents=True)
        (root / 'bin/simplepdf-mobi').write_text('packaged build')
    (prefix / 'share/simpleupdate').mkdir(parents=True)
    record = prefix / 'share/simpleupdate/owned.json'
    tx.write_json(record, tx.inventory(prefix))
    original_inventory = record.read_bytes()
    (prefix / 'bin/simplepdf-mobi').write_text('local rebuild')
    (stage / 'bin/simplepdf-mobi').write_text('new upstream build')
    transaction = tx.Transaction(prefix)
    def failed_verification():
        raise RuntimeError('injected verification failure')
    try:
        transaction.install([stage], failed_verification)
        raise AssertionError('verification failure was ignored')
    except RuntimeError as error:
        assert 'verification failure' in str(error)
    assert (prefix / 'bin/simplepdf-mobi').read_text() == 'local rebuild'
    assert record.read_bytes() == original_inventory
    transaction.install([stage], lambda: None)
    assert (prefix / 'bin/simplepdf-mobi').read_text() == 'new upstream build'
    assert (transaction.retained / 'old/bin/simplepdf-mobi').read_text() == 'local rebuild'
    assert json.loads(record.read_text())['bin/simplepdf-mobi'] == tx.fingerprint(prefix / 'bin/simplepdf-mobi')
    transaction.rollback()
    assert (prefix / 'bin/simplepdf-mobi').read_text() == 'local rebuild'
    assert record.read_bytes() == original_inventory
    # Unknown personal programs still cannot be adopted just because an update
    # happens to ship the same filename.
    (prefix / 'bin/personal-tool').write_text('personal')
    (stage / 'bin/personal-tool').write_text('upstream')
    try:
        transaction.install([stage], lambda: None)
        raise AssertionError('unmanaged program was overwritten')
    except RuntimeError as error:
        assert 'unmanaged program' in str(error)
    assert (prefix / 'bin/personal-tool').read_text() == 'personal'
    assert (prefix / 'bin/simplepdf-mobi').read_text() == 'local rebuild'
    print('OK local rebuilds update with backups, failed verification/rollback restore their exact bytes, unknown programs stay protected')

with tempfile.TemporaryDirectory(prefix='standalone-update-') as temp:
    base = Path(temp); prefix = base / 'local'; stage = base / 'stage'
    for root in (prefix, stage):
        (root / 'bin').mkdir(parents=True)
        for name, data in (
                ('share/applications/org.simplesuite.Simpleplay.desktop', 'SimplePlay desktop'),
                ('share/simplesuite/simpleplay/simpleplay.svg', 'SimplePlay icon'),
                ('share/simplesuite/simpleplay/SIMPLEPLAY.md', 'SimplePlay manual')):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data); path.chmod(0o644)
        for name in ('simpleplay', 'simpleplay-core'):
            program = root / 'bin' / name
            program.write_text('standalone build' if root == prefix else 'updated build')
            program.chmod(0o755)
        for directory in (root, *(p for p in root.rglob('*') if p.is_dir())):
            directory.chmod(0o755)
    (prefix / 'share/simpleupdate').mkdir(mode=0o755)
    record = prefix / 'share/simpleupdate/owned.json'
    tx.write_json(record, {})  # The original ISO predates the optional player.
    original_inventory = record.read_bytes()
    transaction = tx.Transaction(prefix)
    managed_paths = tx.inventory(stage)
    def failed_verification():
        raise RuntimeError('injected standalone verification failure')
    try:
        transaction.install([stage], failed_verification, managed_paths=managed_paths)
        raise AssertionError('verification failure was ignored')
    except RuntimeError as error:
        assert 'verification failure' in str(error), str(error)
    assert record.read_bytes() == original_inventory
    assert (prefix / 'bin/simpleplay').read_text() == 'standalone build'
    transaction.install([stage], lambda: None, managed_paths=managed_paths)
    for name in ('simpleplay', 'simpleplay-core'):
        assert (prefix / 'bin' / name).read_text() == 'updated build'
        assert (transaction.retained / 'old/bin' / name).read_text() == 'standalone build'
        assert json.loads(record.read_text())['bin/' + name] == tx.fingerprint(prefix / 'bin' / name)
    transaction.rollback()
    assert record.read_bytes() == original_inventory
    assert all((prefix / 'bin' / name).read_text() == 'standalone build'
               for name in ('simpleplay', 'simpleplay-core'))

    # Unverified callers cannot enroll paths merely because a file is staged.
    try:
        transaction.install([stage], lambda: None)
        raise AssertionError('an unrecognized program was adopted')
    except RuntimeError as error:
        assert 'unmanaged program' in str(error)
    assert (prefix / 'bin/simpleplay').read_text() == 'standalone build'
    assert record.read_bytes() == original_inventory
    print('OK verified payload enrolls new component files, retains backups, and restores ownership on failure/rollback')
