#!/usr/bin/python3
"""Exercise the complete ordinary orchestrator with real histories and transactions.

Only APT, builds and UID transitions are fixtures. Production source selection,
requirements, grouping, inventories, recovery state and repeat decisions run.
"""
import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'updater'))
import ordinary
import transaction
loader = importlib.machinery.SourceFileLoader('ordinary_legacy', str(ROOT / 'scripts/simpleupdate'))
spec = importlib.util.spec_from_loader(loader.name, loader)
legacy = importlib.util.module_from_spec(spec); loader.exec_module(legacy)

with tempfile.TemporaryDirectory(prefix='ordinary-check-') as temp:
    base = Path(temp); prefix = base / 'local'; upstream = base / 'upstream'
    def git(*args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                                        *map(str, args)], text=True).strip()
    git('init', '--quiet', '-b', 'main', upstream)
    (upstream / 'release').write_text('original')
    git('-C', upstream, 'add', '.'); git('-C', upstream, 'commit', '--quiet', '-m', 'original')
    original = git('-C', upstream, 'rev-parse', 'HEAD')
    (upstream / 'release').write_text('new')
    git('-C', upstream, 'commit', '--quiet', '-am', 'new')
    latest = git('-C', upstream, 'rev-parse', 'HEAD')
    for component in ('simplesuite', 'simplewm'):
        data = prefix / 'share' / component; data.mkdir(parents=True)
        (data / 'install-manifest').write_text(component + '_source_sha=' + original + '\n')
    (prefix / 'share/simpleupdate').mkdir()
    (prefix / 'bin').mkdir()
    for name in ('simpleterm', 'simplewm'):
        (prefix / 'bin' / name).write_text('old ' + name)
    (prefix / 'bin/simpleupdate').write_text('stable launcher')
    transaction.write_json(prefix / 'share/simpleupdate/owned.json', transaction.inventory(prefix))
    (prefix / 'share/simplewm/config').write_text('personal system settings')
    personal = base / 'home/writing'; personal.mkdir(parents=True)
    (personal / 'book').write_text('manuscript')
    args = argparse.Namespace(verbose=False, os_only=False, suite_only=False, wm_only=False,
                              wm_local=None, rebuild=False, verify=False, check=False)
    commands, builds = [], []
    real_run = legacy.run
    audit = ''
    def run(command, **kwargs):
        command = list(map(str, command)); commands.append(command)
        if command[0] == 'dpkg':
            return subprocess.CompletedProcess(command, 0, stdout=audit)
        if command[0] == 'apt-get':
            return subprocess.CompletedProcess(command, 0, stdout='')
        if command[0] == 'git' and 'fetch' in command and 'origin' in command:
            command = ['protocol.file.allow=always' if item == 'protocol.file.allow=never' else item
                       for item in command]
            command[command.index('origin')] = str(upstream)
        return real_run(command, **kwargs)
    fail_wm = False
    def build(update, plan, work, env, demote, uid, gid):
        builds.append(plan['component'])
        if fail_wm and plan['component'] == 'SimpleWM':
            raise RuntimeError('injected WM compiler failure')
        local = Path(plan['stage']) / 'usr/local'
        (local / 'bin').mkdir(parents=True)
        name = 'simplewm' if plan['component'] == 'SimpleWM' else 'simpleterm'
        (local / 'bin' / name).write_text('new ' + name)
        component = plan['component'].lower()
        data = local / 'share' / component; data.mkdir(parents=True)
        (data / 'install-manifest').write_text(component + '_source_sha=' + plan['sha'] + '\n')
        if component == 'simplewm':
            (local / 'bin/simpleupdate').write_text('must never replace stable launcher')
            (data / 'config').write_text('new defaults')
        return local
    contexts = [patch.object(ordinary, 'STATE', base / 'ordinary.json'),
        patch.object(ordinary, 'REBOOT', base / 'reboot'), patch.object(ordinary, 'build', side_effect=build),
        patch.object(legacy, 'PREFIX', prefix),
        patch.object(legacy, 'MANIFEST', prefix / 'share/simplesuite/install-manifest'),
        patch.object(legacy, 'WM_MANIFEST', prefix / 'share/simplewm/install-manifest'),
        patch.object(legacy, 'debian_release', return_value=(13, 'trixie')),
        patch.object(legacy, 'apt_source_changes', return_value={}),
        patch.object(legacy, 'write_apt_sources'), patch.object(legacy, 'refresh_apt'),
        patch.object(legacy, 'validate_apt_release'), patch.object(legacy, 'wm_repository_exists', return_value=True),
        patch.object(legacy, 'discover_wm_dependencies', return_value=(['libwlroots-0.18-dev'], ['wayland-server'])),
        patch.object(legacy, 'wm_pkg_config', return_value=['wlroots-0.18', 'wayland-server']),
        patch.object(legacy, 'build_identity', return_value=(os.getuid(), os.getgid())),
        patch.object(legacy, 'as_user', return_value=None), patch.object(legacy, 'run', side_effect=run)]
    with contextlib.ExitStack() as stack:
        for context in contexts: stack.enter_context(context)
        fail_wm = True
        try:
            ordinary.run(legacy, args, io.StringIO(), 1)
            raise AssertionError('failed WM build was ignored')
        except RuntimeError as error:
            assert 'compiler' in str(error)
        assert (prefix / 'bin/simpleterm').read_text() == 'old simpleterm'
        assert (prefix / 'bin/simplewm').read_text() == 'old simplewm'
        assert ordinary.read_state()['phase'] == 'failed-recoverable'
        fail_wm = False
        builds.clear(); commands.clear()
        ordinary.run(legacy, args, io.StringIO(), 1)
        assert builds == ['SimpleSuite', 'SimpleWM']
        assert (prefix / 'bin/simpleterm').read_text() == 'new simpleterm'
        assert (prefix / 'bin/simplewm').read_text() == 'new simplewm'
        assert (prefix / 'bin/simpleupdate').read_text() == 'stable launcher'
        assert (prefix / 'share/simplewm/config').read_text() == 'personal system settings'
        assert (personal / 'book').read_text() == 'manuscript'
        assert ordinary.read_state()['phase'] == 'completed'
        apt = [c for c in commands if c[0] == 'apt-get']
        assert all('--download-only' in c for c in apt[:2]) and all('--download-only' not in c for c in apt[2:])
        builds.clear(); commands.clear()
        ordinary.run(legacy, args, io.StringIO(), 1)
        assert not builds and not any(c[0] == 'apt-get' and 'install' in c for c in commands)
        print('OK complete ordinary flow: both builds precede grouped install, failed WM keeps Suite, repeat skips builds, bootstrap/personal files preserved')
        transaction.Transaction(prefix).rollback()
        assert (prefix / 'bin/simpleterm').read_text() == 'old simpleterm'
        assert (prefix / 'bin/simplewm').read_text() == 'old simplewm'
        state = ordinary.read_state()
        ordinary.persist(state, 'installing', component='APT')
        audit = 'a package has not been configured'
        try:
            ordinary.recover(legacy); raise AssertionError('interrupted APT was ignored')
        except ordinary.RecoveryRequired:
            pass
        assert ordinary.read_state()['phase'] == 'manual-recovery-required'
        audit = ''
        ordinary.recover(legacy)
        (upstream / 'simpleupdate-requirements.json').write_text(json.dumps({'format': 1, 'protocol': 1, 'minimum_updater': 2}))
        git('-C', upstream, 'add', '.'); git('-C', upstream, 'commit', '--quiet', '-m', 'requires new updater')
        commands.clear(); builds.clear()
        try:
            ordinary.run(legacy, args, io.StringIO(), 1); raise AssertionError('minimum updater was ignored')
        except RuntimeError as error:
            assert 'newer authenticated updater' in str(error)
        assert not builds and not any(c[0] == 'apt-get' for c in commands)
        print('OK retained grouped rollback, interrupted APT repair state, and minimum-updater rejection before package installation')
