#!/usr/bin/python3
"""Real versioned files and child processes; only transport/UIDs are fixtures."""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'updater/launcher.py')
boot = importlib.util.module_from_spec(spec); spec.loader.exec_module(boot)
real_run = subprocess.run


def child_run(*args, **kwargs):
    # Unit tests also run without administrator access. Integration exercises
    # actual root/nobody credentials; do not claim that from this test.
    for key in ('user', 'group', 'extra_groups'):
        kwargs.pop(key, None)
    return real_run(*args, **kwargs)


with tempfile.TemporaryDirectory(prefix='bootstrap-check-') as temp:
    root = Path(temp)
    versions = root / 'versions'; versions.mkdir()
    data = root / 'data'; data.mkdir()
    result = root / 'result'
    def release(version, broken=False):
        directory = root / f'release-{version}'; directory.mkdir()
        for name, source in boot.FILES.items():
            shutil.copyfile(ROOT / source, directory / name)
        # Simulate a future implementation while retaining the real stable
        # launcher's verification, installation, handoff and fallback machinery.
        (directory / 'engine.py').write_text('''import json,os,sys,socket
from pathlib import Path
version=json.loads(Path(__file__).with_name('release.json').read_text())['version']
if sys.argv[1:]==['--recover-sources']:sys.exit(0)
if sys.argv[1:]==['--bootstrap-probe']:
    print(json.dumps({'protocol':1,'version':version}));sys.exit(0)
''' + ('sys.exit(9)\n' if broken else '') + '''channel=socket.socket(fileno=int(sys.argv[2]));channel.sendall(b'READY 1\\n')
assert channel.recv(1)==b'G';channel.close()
assert sys.argv[3]=='--record'
Path(sys.argv[4]).write_text(str(version))
''')
        raw = json.dumps({'format': 1, 'version': version, 'protocol': 1, 'revision': f'{version:040x}',
                          'files': {name: {'size': (directory / name).stat().st_size,
                                          'sha256': hashlib.sha256((directory / name).read_bytes()).hexdigest()}
                                    for name in boot.FILES}}).encode()
        (directory / 'release.json').write_bytes(raw)
        return directory, boot.manifest(directory)
    initial, (metadata, name) = release(1)
    shutil.copytree(initial, versions / name)
    shutil.copyfile(initial / 'release.json', data / 'release.json')
    latest, _ = release(2)
    downloads = []
    def download(path, limit):
        downloads.append(path)
        file = Path(path).name
        if file != 'release.json':
            file = next(name for name, source in boot.FILES.items() if path.endswith('/' + source))
        return (latest / file).read_bytes()
    contexts = [patch.object(boot, 'DATA', data), patch.object(boot, 'VERSIONS', versions),
                patch.object(boot, 'STATE', root / 'state.json'), patch.object(boot, 'LOCK', root / 'lock'),
                patch.object(boot, 'download', side_effect=download),
                patch.object(boot, 'MIGRATION', root / 'migration.json'),
                patch.object(boot, 'trusted_file', return_value=None),
                patch.object(boot, 'private_directory', side_effect=lambda p, **kw: p.mkdir(exist_ok=True, parents=True)),
                patch.object(boot.os, 'geteuid', return_value=0),
                patch.object(boot.subprocess, 'run', side_effect=child_run),
                patch.object(sys, 'argv', ['simpleupdate', '--record', str(result)])]
    with contextlib.ExitStack() as stack:
        for context in contexts:
            stack.enter_context(context)
        assert boot.main() == 0 and result.read_text() == '2'
        state = json.loads((root / 'state.json').read_text())
        assert state['previous'] == name and not state['pending']
        downloads.clear()
        assert boot.main() == 0
        assert downloads == ['main/updater/release.json']
        print('OK updater-first replacement and original-argument handoff; equal version is not downloaded again')
        latest, _ = release(3, broken=True)
        assert boot.main() == 0 and result.read_text() == '2'
        assert json.loads((root / 'state.json').read_text())['rejected']
        downloads.clear()
        assert boot.main() == 0 and len(downloads) == 1
        print('OK replacement failing before readiness restores and runs the previous implementation; no recursive retry')
        latest, (_, bad_name) = release(4)
        (latest / 'engine.py').write_text('corrupt payload')
        try:
            boot.main(); raise AssertionError('corrupt payload executed')
        except RuntimeError as error:
            assert 'verification' in str(error)
        assert result.read_text() == '2'
        print('OK payload corruption stops before execution and preserves the working updater')
        # Model a power loss after activation's journal, before READY persisted.
        state = json.loads((root / 'state.json').read_text())
        old_active = state['active']
        state.update(active=bad_name, previous=old_active, pending=True)
        boot.save(root / 'state.json', state)
        latest = root / 'release-3'
        # Highest verified release is four: a replay must stop after recovery.
        try:
            boot.main(); raise AssertionError('metadata rollback accepted')
        except RuntimeError as error:
            assert 'older' in str(error)
        assert json.loads((root / 'state.json').read_text())['active'] == old_active
        print('OK interrupted activation restores a verified predecessor; verified version replay is refused')
