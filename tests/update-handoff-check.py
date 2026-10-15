#!/usr/bin/python3
"""Shipped 0.8 release-3 bootstrap -> real new engine -> ordinary transaction.

Only transport, system paths/credentials, APT and compilation are fixtures.
Release verification, activation handshake, argument handoff, orchestration,
local-build replacement, inventory and backups use production code.
"""
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
SHIPPED = '45128908060e3d18449d9540b71d5090ec7f3a65'
WRAPPER = r'''
import argparse, builtins, importlib.util, json, os, sys
from pathlib import Path
payload = Path(sys.argv.pop(1))
base = Path(sys.argv.pop(1))
sys.argv[0] = str(payload)
spec = importlib.util.spec_from_file_location('candidate', payload)
engine = importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
legacy = engine.load_legacy()
engine.load_legacy = lambda: legacy
engine.ordinary.STATE = base / 'ordinary.json'
engine.ordinary.REBOOT = base / 'reboot'
prefix = base / 'local'
legacy.PREFIX = prefix
legacy.MANIFEST = prefix / 'share/simplesuite/install-manifest'
legacy.WM_MANIFEST = prefix / 'share/simplewm/install-manifest'
legacy.PENDING_RELEASE = base / 'migration.json'
legacy.debian_release = lambda: (13, 'trixie')
legacy.stable_release = lambda: (13, 'trixie')
legacy.apt_source_changes = lambda *_: {}
legacy.validate_apt_release = lambda *_: None
legacy.build_identity = lambda: (os.getuid(), os.getgid())
legacy.as_user = lambda *_: None
paths = {'/var/log/simpleupdate': base / 'logs', '/run/lock/simpleupdate.lock': base / 'update.lock'}
legacy.Path = lambda name, *parts: Path(paths.get(str(name), name), *parts)
def private_open(name, *args, **kwargs):
    return builtins.open(paths.get(str(name), name), *args, **kwargs)
legacy.open = engine.open = private_open
real_parents = engine.transaction.parents
real_euid = os.geteuid
def parents(root, path):
    os.geteuid = real_euid
    try:
        return real_parents(root, path)
    finally:
        os.geteuid = lambda: 0
engine.transaction.parents = parents
os.geteuid = lambda: 0
def run(command, **kwargs):
    from subprocess import CompletedProcess
    assert command[0] in ('apt-get', 'dpkg'), command
    with (base / 'commands').open('a') as out:
        out.write(json.dumps(command) + '\n')
    return CompletedProcess(command, 0, stdout='')
legacy.run = run
def plan(update, args, work, env, demote, uid, gid, version):
    assert not any((args.os_only, args.wm_only, args.suite_only, args.rebuild))
    assert version == 4
    if legacy.installed_revision(legacy.MANIFEST) == '2' * 40:
        return []
    return [{'component': 'SimpleSuite', 'sha': '2' * 40, 'source': str(work / 'source'),
             'stage': str(work / 'stage'), 'env': env, 'verify': False}]
engine.ordinary.source_plan = plan
def build(update, plan, work, env, demote, uid, gid):
    local = Path(plan['stage']) / 'usr/local'
    (local / 'bin').mkdir(parents=True)
    (local / 'bin/simplepdf-mobi').write_text('new upstream program')
    data = local / 'share/simplesuite'; data.mkdir(parents=True)
    (data / 'install-manifest').write_text('simplesuite_source_sha=' + plan['sha'] + '\n')
    return local
engine.ordinary.build = build
engine.main()
'''

with tempfile.TemporaryDirectory(prefix='handoff-check-') as temp:
    base = Path(temp)
    archived = base / 'launcher.py'
    archived.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show', SHIPPED + ':updater/launcher.py']))
    spec = importlib.util.spec_from_file_location('old_bootstrap', archived)
    boot = importlib.util.module_from_spec(spec); spec.loader.exec_module(boot)
    versions = base / 'versions'; versions.mkdir()
    data = base / 'data'; data.mkdir()
    def release(version, old=False):
        target = base / f'release-{version}'; target.mkdir()
        for name, source in boot.FILES.items():
            content = (subprocess.check_output(['git', '-C', str(ROOT), 'show', SHIPPED + ':' + source])
                       if old else (ROOT / source).read_bytes())
            (target / name).write_bytes(content)
        metadata = {'format': 1, 'protocol': 1, 'version': version, 'revision': SHIPPED if old else '4' * 40,
                    'files': {name: {'size': (target / name).stat().st_size,
                                     'sha256': hashlib.sha256((target / name).read_bytes()).hexdigest()}
                              for name in boot.FILES}}
        (target / 'release.json').write_text(json.dumps(metadata))
        return target, boot.manifest(target)[1]
    old, old_name = release(3, old=True)
    new, new_name = release(4)
    shutil.copytree(old, versions / old_name)
    shutil.copyfile(old / 'release.json', data / 'release.json')
    sys.path.insert(0, str(ROOT / 'updater'))
    import transaction
    prefix = base / 'local'
    (prefix / 'bin').mkdir(parents=True)
    (prefix / 'share/simpleupdate').mkdir(parents=True)
    (prefix / 'share/simplesuite').mkdir()
    (prefix / 'bin/simplepdf-mobi').write_text('original packaged program')
    (prefix / 'share/simplesuite/install-manifest').write_text('simplesuite_source_sha=' + '1' * 40 + '\n')
    transaction.write_json(prefix / 'share/simpleupdate/owned.json', transaction.inventory(prefix))
    (prefix / 'bin/simplepdf-mobi').write_text('local rebuild')
    wrapper = base / 'fixture.py'; wrapper.write_text(WRAPPER)
    real_popen = subprocess.Popen
    def popen(command, **kwargs):
        command = list(command)
        if len(command) > 2 and command[2].endswith('/engine.py'):
            command = [*command[:2], str(wrapper), command[2], str(base), *command[3:]]
            for key in ('user', 'group', 'extra_groups'):
                kwargs.pop(key, None)
        return real_popen(command, **kwargs)
    downloads = []
    def download(path, limit):
        downloads.append(path)
        name = 'release.json' if path.endswith('/release.json') else next(
            name for name, source in boot.FILES.items() if path.endswith('/' + source))
        return (new / name).read_bytes()
    contexts = [patch.object(boot, 'DATA', data), patch.object(boot, 'VERSIONS', versions),
                patch.object(boot, 'STATE', base / 'bootstrap.json'), patch.object(boot, 'LOCK', base / 'bootstrap.lock'),
                patch.object(boot, 'MIGRATION', base / 'migration.json'),
                patch.object(boot, 'download', side_effect=download),
                patch.object(boot, 'trusted_file'),
                patch.object(boot, 'private_directory', side_effect=lambda p, **kw: p.mkdir(exist_ok=True, parents=True)),
                patch.object(boot.os, 'geteuid', return_value=0),
                patch.object(boot.subprocess, 'Popen', side_effect=popen),
                patch.object(sys, 'argv', ['simpleupdate'])]
    with contextlib.ExitStack() as stack:
        for context in contexts:
            stack.enter_context(context)
        assert boot.main() == 0
        state = json.loads((base / 'bootstrap.json').read_text())
        assert state['active'] == new_name and state['previous'] == old_name and not state['pending']
        assert json.loads((base / 'ordinary.json').read_text())['phase'] == 'completed'
        assert (prefix / 'bin/simplepdf-mobi').read_text() == 'new upstream program'
        assert (prefix / '.simpleupdate-previous/old/bin/simplepdf-mobi').read_text() == 'local rebuild'
        assert any('full-upgrade' in line for line in (base / 'commands').read_text().splitlines())
        downloads.clear()
        assert boot.main() == 0
        assert downloads == ['main/updater/release.json']
    print('OK shipped 0.8 release-3 bootstrap upgrades to the real new engine and completes ordinary updates in one command; repeat keeps the new updater')
