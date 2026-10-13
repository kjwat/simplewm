#!/usr/bin/env python3
"""Run the shipped 0.8-r2 updater and today's updater with no CLI arguments.

Git histories, manifest decisions, locking, staging and transactions are real.
APT and compilation use fixtures; every system path points into a private root.
"""
import builtins
import contextlib
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

repo = Path(__file__).resolve().parent.parent
shipped_commit = '2781d08db503fd9d6db7ed46a8281ce7243d2b18'
shipped_source = subprocess.run(
    ['git', '-C', str(repo), 'show', shipped_commit + ':scripts/simpleupdate'],
    check=True, capture_output=True, text=True).stdout

with tempfile.TemporaryDirectory(prefix='simpleupdate-plain-') as temporary:
    root = Path(temporary)
    home = root / 'home'; home.mkdir()
    env = dict(PATH=os.environ['PATH'], HOME=str(home), LC_ALL='C.UTF-8',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid',
               GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid')
    def git(*args):
        return subprocess.run(['git', *map(str, args)], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()
    upstream = root / 'upstream'
    git('init', '--quiet', '-b', 'main', upstream)
    (upstream / 'release').write_text('ISO release')
    git('-C', upstream, 'add', 'release')
    git('-C', upstream, 'commit', '--quiet', '-m', 'published ISO release')
    installed = git('-C', upstream, 'rev-parse', 'HEAD')
    (upstream / 'release').write_text('latest published release')
    git('-C', upstream, 'commit', '--quiet', '-am', 'newer published release')
    latest = git('-C', upstream, 'rev-parse', 'HEAD')
    archived = root / 'simpleupdate-0.8-r2'
    archived.write_text(shipped_source)
    for name, script in (('original ISO', archived), ('current', repo / 'scripts/simpleupdate')):
        loader = importlib.machinery.SourceFileLoader('plain_update_' + script.name, str(script))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        update = importlib.util.module_from_spec(spec); loader.exec_module(update)
        base = root / (script.name + '-root'); base.mkdir()
        prefix = base / 'local'; (prefix / 'bin').mkdir(parents=True)
        for component in ('simplesuite', 'simplewm'):
            data = prefix / 'share' / component; data.mkdir(parents=True)
            (data / 'install-manifest').write_text(f'{component}_source_sha={installed}\n')
            git('-C', upstream, 'branch', '-f', 'iso', installed)
            # The updater reads the image's published main branch bundle.
            bundle_repo = base / (component + '-bundle')
            git('init', '--quiet', '--bare', bundle_repo)
            git('-C', bundle_repo, 'fetch', '--quiet', upstream, 'iso:main')
            git('-C', bundle_repo, 'bundle', 'create', data / 'source.bundle', 'main')
        personal = base / 'home/.config/simpleterm/settings.ini'
        personal.parent.mkdir(parents=True); personal.write_text('personal terminal colors')
        document = base / 'home/writing/draft.txt'
        document.parent.mkdir(parents=True); document.write_text('personal writing')
        (base / 'run').mkdir(); (base / 'tmp').mkdir()
        real_run, real_install = update.run, update.install_transaction
        real_recover, real_mkdtemp = update.recover_transaction, tempfile.mkdtemp
        commands, builds = [], []
        def transport(args, **kwargs):
            args = list(map(str, args)); commands.append(args)
            if args[0] == 'apt-get':
                return subprocess.CompletedProcess(args, 0, stdout='Debian|trixie|main\n' if 'indextargets' in args else '')
            if args[0] != 'git':
                raise AssertionError(f'unexpected non-fixture command: {args}')
            if 'fetch' in args and args[-2] == 'origin':
                args = ['protocol.file.allow=always' if arg == 'protocol.file.allow=never'
                        else arg for arg in args]
                args[-2] = str(upstream)
            return real_run(args, **kwargs)
        def payload(component):
            def compile_fixture(source, stage, sha, environment, demote, verify=False):
                builds.append((component, sha, verify))
                local = stage / 'usr/local'
                (local / 'bin').mkdir(parents=True)
                if component == 'simplesuite':
                    (local / 'bin/simpleterm').write_text('latest terminal with color fixes')
                    asset = local / 'share/simplesuite/simpleterm/bashrc'
                    asset.parent.mkdir(parents=True); asset.write_text('latest Bash prompt asset')
                else:
                    (local / 'bin/simplewm').write_text('latest compositor')
                    (local / 'bin/simpleupdate').write_text('latest updater')
                data = local / 'share' / component; data.mkdir(exist_ok=True, parents=True)
                (data / 'install-manifest').write_text(f'{component}_source_sha={sha}\n')
                git('-C', source, 'branch', '-f', 'main', sha)
                git('-C', source, 'bundle', 'create', data / 'source.bundle', 'main')
                return local
            return compile_fixture
        def private_path(value, *parts):
            relocated = {'/var/log/simpleupdate': base / 'logs',
                         '/run/reboot-required': base / 'run/reboot-required'}
            return Path(relocated.get(str(value), value), *parts)
        def private_open(value, *args, **kwargs):
            if str(value) == '/run/lock/simpleupdate.lock':
                value = base / 'run/simpleupdate.lock'
            return builtins.open(value, *args, **kwargs)
        def private_temp(*args, **kwargs):
            if kwargs.get('dir') == '/var/tmp': kwargs['dir'] = str(base / 'tmp')
            return real_mkdtemp(*args, **kwargs)
        for fresh in (True, False):
            commands.clear(); builds.clear()
            output = io.StringIO()
            contexts = [
                patch.dict(os.environ),
                patch.object(sys, 'argv', [str(script)]),
                patch.object(update, 'PREFIX', prefix),
                patch.object(update, 'MANIFEST', prefix / 'share/simplesuite/install-manifest'),
                patch.object(update, 'WM_MANIFEST', prefix / 'share/simplewm/install-manifest'),
                patch.object(update, 'WM_SOURCE', prefix / 'share/simplewm/source'),
                patch.object(update, 'Path', side_effect=private_path),
                patch.object(update, 'open', side_effect=private_open, create=True),
                patch.object(update.os, 'geteuid', return_value=0),
                patch.object(update, 'build_identity', return_value=(os.getuid(), os.getgid())),
                patch.object(update, 'as_user', return_value=None),
                patch.object(update.tempfile, 'mkdtemp', side_effect=private_temp),
                patch.object(update, 'run', side_effect=transport),
                patch.object(update, 'wm_repository_exists', return_value=True),
                patch.object(update, 'build_and_test', side_effect=payload('simplesuite')),
                patch.object(update, 'build_and_test_wm', side_effect=payload('simplewm')),
                patch.object(update, 'recover_transaction', side_effect=lambda p=prefix: real_recover(p)),
                patch.object(update, 'install_transaction', side_effect=lambda stage, p=prefix: real_install(stage, p)),
                contextlib.redirect_stdout(output),
            ]
            if name == 'current':
                # Release detection and APT source validation must also stay
                # inside this fixture; the archived updater has no such hooks.
                contexts += [patch.object(update, 'debian_release', return_value=(13, 'trixie')),
                             patch.object(update, 'PENDING_RELEASE', base / 'run/release-upgrade.json'),
                             patch.object(update, 'stable_release', return_value=(13, 'trixie')),
                             patch.object(update, 'apt_source_changes', return_value={})]
            with contextlib.ExitStack() as stack:
                for context in contexts: stack.enter_context(context)
                update.main()
            assert len(builds) == (2 if fresh else 0), (name, fresh, builds, output.getvalue())
            if fresh:
                assert {component for component, sha, verify in builds} == {'simplesuite', 'simplewm'}
                assert all(sha == latest and not verify for component, sha, verify in builds)
            assert sum(command[:2] == ['apt-get', 'update'] for command in commands) == 1
            assert sum(command[0] == 'apt-get' and 'full-upgrade' in command for command in commands) == 1
            assert not any('-s' in command for command in commands if command[0] == 'apt-get')
            for component in ('simplesuite', 'simplewm'):
                assert (prefix / f'share/{component}/install-manifest').read_text() == f'{component}_source_sha={latest}\n'
            assert (prefix / 'bin/simpleterm').read_text() == 'latest terminal with color fixes'
            assert (prefix / 'share/simplesuite/simpleterm/bashrc').read_text() == 'latest Bash prompt asset'
            assert (prefix / 'bin/simplewm').read_text() == 'latest compositor'
            assert (prefix / 'bin/simpleupdate').read_text() == 'latest updater'
            assert personal.read_text() == 'personal terminal colors'
            assert document.read_text() == 'personal writing'
            assert not any((base / 'tmp').iterdir())
        print(f'OK {name} updater: plain simpleupdate updates Debian, Suite, terminal/Bash asset and WM/updater in one invocation; repeat skips builds')
