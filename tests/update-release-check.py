#!/usr/bin/env python3
"""Exercise release upgrades entirely in private roots; never run real APT.

Git fetching, source edits, configuration backups and install transactions are
real. Network transport, compilation and package mutations use fixtures. APT's
read-only index inspection runs against a separate, locally generated cache.
"""
import argparse
import builtins
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

script = Path(__file__).resolve().parent.parent / 'scripts/simpleupdate'
loader = importlib.machinery.SourceFileLoader('release_update', str(script))
spec = importlib.util.spec_from_loader(loader.name, loader)
update = importlib.util.module_from_spec(spec)
loader.exec_module(update)

def options(**values):
    args = argparse.Namespace(release_upgrade=False, dry_run=False, check=False,
                              os_only=False, suite_only=False, wm_only=False,
                              wm_local=None, rebuild=False, verify=False)
    vars(args).update(values)
    return args

def fails(action, message):
    try:
        action()
    except RuntimeError as error:
        assert message in str(error), error
    else:
        raise AssertionError(f'expected rejection: {message}')

class Metadata(io.BytesIO):
    def geturl(self):
        return update.STABLE_RELEASE

with tempfile.TemporaryDirectory(prefix='simpleupdate-release-check-') as temporary:
    root = Path(temporary)
    apt = root / 'sources'; (apt / 'sources.list.d').mkdir(parents=True)
    legacy = apt / 'sources.list'
    legacy.write_text('# Debian\ndeb https://deb.debian.org/debian stable main\n'
                      'deb-src https://security.debian.org/debian-security oldstable-security main\n'
                      'deb https://deb.debian.org/debian bookworm-backports main\n'
                      'deb https://vendor.example/packages stable main\n')
    modern = apt / 'sources.list.d/debian.sources'
    modern.write_text('Types: deb deb-src\nURIs: https://mirror.example/debian\n'
                      'Suites: stable\n oldstable-updates bookworm-backports\nComponents: main\n'
                      'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\n'
                      'Types: deb\nURIs: https://deb.debian.org/debian\n'
                      'Suites: testing\nComponents: main\nEnabled: no\n')
    liquorix = apt / 'sources.list.d/liquorix.sources'
    liquorix.write_text('Types: deb\nURIs: https://liquorix.net/debian\nSuites: stable\nComponents: main\n')
    original = {path: path.read_text() for path in (legacy, modern, liquorix)}
    with patch.object(update, 'APT_ROOT', apt), contextlib.redirect_stdout(io.StringIO()):
        ordinary = update.apt_source_changes('bookworm')
        assert 'bookworm main' in ordinary[legacy]
        assert 'bookworm-security' in ordinary[legacy]
        assert 'https://vendor.example/packages stable main' in ordinary[legacy]
        assert 'Suites: bookworm bookworm-updates' in ordinary[modern]
        assert 'Suites: testing' in ordinary[modern]  # Disabled stanza preserved.
        assert 'Suites: bookworm' in ordinary[liquorix]
        assert all(path.read_text() == text for path, text in original.items())
        upgrade = update.apt_source_changes('bookworm', 'trixie')
        assert 'trixie main' in upgrade[legacy] and 'trixie-security' in upgrade[legacy]
        assert '# simpleupdate release upgrade: deb https://vendor.example' in upgrade[legacy]
        assert '# simpleupdate release upgrade: deb https://deb.debian.org/debian bookworm-backports' in upgrade[legacy]
        assert 'Suites: trixie trixie-updates' in upgrade[modern]
        assert 'Suites: trixie trixie-updates\n' in upgrade[modern]  # Keep main suites when dropping backports.
        assert 'Enabled: no' in upgrade[liquorix]
        legacy.write_text(original[legacy] + 'deb https://deb.debian.org/debian trixie main\n')
        fails(lambda: update.apt_source_changes('bookworm'), 'does not match installed Debian')
        assert modern.read_text() == original[modern]
        legacy.write_text(original[legacy])
        update.write_apt_sources(ordinary)
        assert not update.apt_source_changes('bookworm')
        for path in original:
            assert path.with_name(path.name + '.simpleupdate-backup').read_text() == original[path]
        # An unidentified rolling Debian mirror cannot escape the codename guard.
        legacy.write_text('deb https://mirror.example/debian stable main\n')
        fails(lambda: update.apt_source_changes('bookworm'), 'Signed-By')
        legacy.write_text(original[legacy])

    isolated = root / 'no-base'; isolated.mkdir()
    with patch.object(update, 'APT_ROOT', isolated):
        for entry in ('deb-src https://deb.debian.org/debian bookworm main\n',
                      'deb https://security.debian.org/debian-security bookworm-security main\n',
                      'deb https://deb.debian.org/debian bookworm contrib\n'):
            (isolated / 'sources.list').write_text(entry)
            fails(lambda: update.apt_source_changes('bookworm'), 'base binary repository')

    # Replace a linked source atomically without destroying the link. A failed
    # replacement leaves the complete previous configuration in place.
    target = root / 'linked-source'; target.write_text('before\n'); target.chmod(0o640)
    link = root / 'source-link'; link.symlink_to(target)
    update.write_text_atomic(link, 'after\n')
    assert link.is_symlink() and target.read_text() == 'after\n'
    assert target.stat().st_mode & 0o777 == 0o640
    with patch.object(update.os, 'replace', side_effect=OSError('fixture failed replace')):
        try:
            update.write_text_atomic(link, 'incomplete\n')
        except OSError:
            pass
        else:
            raise AssertionError('failed replacement was ignored')
    assert target.read_text() == 'after\n' and not list(root.glob('.simpleupdate-*'))

    # Exercise real apt-get indextargets without touching the system cache or
    # contacting a mirror. The unknown URI deliberately evades hostname checks.
    indexes = root / 'indexes'; indexes.mkdir(); (indexes / 'partial').mkdir()
    index_sources = root / 'index-sources.list'
    index_sources.write_text('deb [trusted=yes] https://mirror.example/archive stable main\n')
    packages = b'Package: fixture\nVersion: 1\nArchitecture: amd64\n\n'
    (indexes / 'mirror.example_archive_dists_stable_main_binary-amd64_Packages').write_bytes(packages)
    release_file = indexes / 'mirror.example_archive_dists_stable_Release'
    def inspect_indexes(command, **kwargs):
        assert command[:2] == ['apt-get', 'indextargets']
        return subprocess.run([command[0], '-o', 'Dir::Etc::sourcelist=' + str(index_sources),
                               '-o', 'Dir::Etc::sourceparts=-', '-o', 'Dir::State::lists=' + str(indexes),
                               '-o', 'APT::Architecture=amd64', *command[1:]], check=True, **kwargs)
    with patch.object(update, 'run', side_effect=inspect_indexes):
        for codename in ('trixie', 'forky', 'stable'):
            release_file.write_text('Origin: Debian\nLabel: Debian\nSuite: stable\n'
                f'Codename: {codename}\nVersion: 13\nArchitectures: amd64\nComponents: main\n'
                f'SHA256:\n {hashlib.sha256(packages).hexdigest()} {len(packages)} main/binary-amd64/Packages\n')
            if codename == 'trixie':
                update.validate_apt_release('trixie')
            else:
                fails(lambda: update.validate_apt_release('trixie'),
                      'rolling codename' if codename == 'stable' else 'does not match installed Debian')
        index_sources.write_text('')
        fails(lambda: update.validate_apt_release('trixie'), 'no Debian trixie base package index')
    for data in ('Debian|trixie|contrib\n', 'Debian|trixie-security|main\n',
                 'Debian|trixie|main\nliquorix|forky|main\n'):
        with patch.object(update, 'run', return_value=SimpleNamespace(stdout=data)):
            fails(lambda: update.validate_apt_release('trixie'),
                  'does not match' if 'forky' in data else 'base package index')

    for metadata, valid in (
            ('Origin: Debian\nSuite: stable\nVersion: 13.7\nCodename: trixie\n', True),
            ('Origin: Debian\nSuite: testing\nVersion: 14\nCodename: forky\n', False),
            ('Origin: Other\nSuite: stable\nVersion: 13\nCodename: trixie\n', False)):
        with patch.object(update.urllib.request, 'urlopen', return_value=Metadata(metadata.encode())):
            if valid:
                assert update.stable_release() == (13, 'trixie')
            else:
                fails(update.stable_release, 'unexpected Debian')
    with patch.object(update, 'stable_release', side_effect=OSError('offline')), contextlib.redirect_stdout(io.StringIO()):
        assert update.check_stable() is None
        fails(lambda: update.check_stable(required=True), 'cannot check Debian stable')

    # Approval must be explicit; unattended runs and point releases never approve.
    interactive = SimpleNamespace(isatty=lambda: True, fileno=lambda: 0)
    with patch.object(update.sys, 'stdin', interactive), patch('builtins.input', return_value='') as prompt, \
         patch.object(update, 'require_console') as console, contextlib.redirect_stdout(io.StringIO()):
        assert not update.offer_release(options(), (12, 'bookworm'), (13, 'trixie'))
        prompt.assert_called_once(); console.assert_not_called()
    with patch.object(update.sys, 'stdin', interactive), patch('builtins.input', return_value='trixie'), \
         patch.object(update, 'require_console') as console, contextlib.redirect_stdout(io.StringIO()):
        assert update.offer_release(options(release_upgrade=True), (12, 'bookworm'), (13, 'trixie'))
        assert console.called
    with patch.object(update.sys, 'stdin', SimpleNamespace(isatty=lambda: False)), \
         patch('builtins.input', side_effect=AssertionError('unattended prompt')), contextlib.redirect_stdout(io.StringIO()):
        assert not update.offer_release(options(), (12, 'bookworm'), (13, 'trixie'))
        fails(lambda: update.offer_release(options(release_upgrade=True), (12, 'bookworm'), (13, 'trixie')), 'interactive approval')
        assert not update.offer_release(options(), (13, 'trixie'), (13, 'trixie'))
        fails(lambda: update.offer_release(options(release_upgrade=True), (11, 'bullseye'), (13, 'trixie')), 'previous release')

    # A sudo-stripped environment cannot turn a graphical pseudo-terminal into a console.
    proc = root / 'proc'; (proc / '123').mkdir(parents=True)
    (proc / '123/comm').write_text('simplewm\n')
    with patch.object(update.sys, 'stdin', interactive), patch.object(update.sys, 'stdout', interactive), \
         patch.dict(os.environ, {}, clear=True), \
         patch.object(update.os, 'ttyname', return_value='/dev/pts/2'):
        fails(update.require_console, 'text console')
    with patch.object(update.sys, 'stdin', interactive), patch.object(update.sys, 'stdout', interactive), \
         patch.dict(os.environ, {}, clear=True), patch.object(update.os, 'ttyname', return_value='/dev/tty2'), \
         patch.object(update, 'Path', side_effect=lambda path: proc if path == '/proc' else Path(path)):
        fails(update.require_console, 'still running')
        (proc / '123/comm').write_text('bash\n')
        update.require_console()
        # sudo's use_pty setting must not reject a real text-console caller.
        with patch.object(update.os, 'ttyname', return_value='/dev/pts/4'), \
             patch.dict(os.environ, {'SUDO_UID': '1000', 'SUDO_TTY': '/dev/tty2'}):
            update.require_console()
        with patch.dict(os.environ, {'SUDO_UID': '1000', 'SUDO_TTY': '/dev/pts/2'}):
            fails(update.require_console, 'text console')

    # Every dry-run scope must return before privilege escalation, locks, logs,
    # temporary Git fetches, recovery, package commands or writes.
    for flags in (['--dry-run'], ['--dry-run', '--release-upgrade'],
                  ['--dry-run', '--suite-only'], ['--dry-run', '--wm-only'], ['--dry-run', '--os-only'],
                  ['--dry-run', '--check']):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(update.sys, 'argv', [str(script), *flags]))
            stack.enter_context(patch.object(update, 'APT_ROOT', apt))
            stack.enter_context(patch.object(update, 'PENDING_RELEASE', root / 'unused-state'))
            stack.enter_context(patch.object(update, 'debian_release', return_value=(12, 'bookworm')))
            stack.enter_context(patch.object(update, 'stable_release', return_value=(13, 'trixie')))
            for name in ('run', 'write_apt_sources', 'recover_transaction', 'backup_release_configuration'):
                stack.enter_context(patch.object(update, name, side_effect=AssertionError(f'dry run called {name}')))
            stack.enter_context(patch.object(update.os, 'geteuid', side_effect=AssertionError('dry run checked privileges')))
            stack.enter_context(patch.object(update.tempfile, 'mkdtemp', side_effect=AssertionError('dry run created files')))
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            update.main()
            assert 'Dry run' in output.getvalue()
            if '--check' in flags:
                assert 'simulate (-s)' in output.getvalue()
                assert 'without building or installing' in output.getvalue()
    assert legacy.read_text() == original[legacy]
    print('OK codename pinning, both source formats, stable detection, explicit approval, console guards and mutation-free dry runs')

    # Preserve terminal input/output for prompts, even when transcript logging is enabled.
    log = io.StringIO()
    with patch.object(update, 'LOG_STREAM', log), patch.object(update.subprocess, 'run') as direct, \
         patch.object(update.subprocess, 'Popen', side_effect=AssertionError('piped interactive prompt')):
        update.run(['apt-get', 'full-upgrade'], interactive=True)
        assert direct.call_args.kwargs == {'check': True}
        assert '/var/log/apt/term.log' in log.getvalue()

    git_home = root / 'git-home'; git_home.mkdir()
    env = update.safe_environment(git_home) | {
        'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
        'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid'}
    def git(*args):
        return subprocess.run(['git', *map(str, args)], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()
    upstream = root / 'upstream'
    git('init', '--quiet', '-b', 'main', upstream)
    (upstream / 'config').write_text('source shared with the installed revision')
    git('-C', upstream, 'add', 'config')
    git('-C', upstream, 'commit', '--quiet', '-m', 'installed revision')
    sha = git('-C', upstream, 'rev-parse', 'HEAD')
    real_run = update.run

    for failure in (None, 'fetch', 'wm-fetch', 'local-source', 'tools', 'audit', 'holds',
                    'preflight-env', 'preflight-build', 'final-decline', 'switch', 'apt', 'wm-build'):
        base = root / ('upgrade-' + str(failure)); base.mkdir()
        config = base / 'etc'; config.mkdir()
        apt = config / 'apt'; (apt / 'sources.list.d').mkdir(parents=True)
        sources = apt / 'sources.list'
        original_sources = ('deb https://deb.debian.org/debian stable main\n'
                            'deb https://vendor.example/packages stable main\n')
        sources.write_text(original_sources)
        vendor = apt / 'sources.list.d/vendor.sources'
        vendor.write_text('Types: deb\nURIs: https://vendor.example/archive\nSuites: stable\nComponents: main\n')
        prefix = base / 'usr/local'; (prefix / 'bin').mkdir(parents=True)
        home = base / 'home'; (home / '.config/simplewm').mkdir(parents=True)
        personal = home / '.config/simplewm/config'; personal.write_text('personal colors')
        package_state = base / 'dpkg-status'; package_state.write_text('saved package database')
        external = base / 'dotfiles'; external.mkdir()
        (external / 'config').write_text('linked settings')
        (home / '.config/simplefiles').symlink_to(external, target_is_directory=True)
        (home / '.profile').symlink_to(external / 'config')
        identity = base / 'usr/lib'; identity.mkdir(parents=True)
        debian = identity / 'os-release.debian'
        debian.write_text('ID=debian\nVERSION_ID="12"\nVERSION_CODENAME=bookworm\n')
        brand = identity / 'os-release'
        brand.write_text('ID=simpleos\nVERSION_ID="0.8"\nPRETTY_NAME="SimpleOS 0.8 (Debian 12)"\n'
                         'VERSION="0.8 (Debian 12 bookworm)"\nVERSION_CODENAME=bookworm\n')
        os_release = config / 'os-release'; os_release.symlink_to('../usr/lib/os-release')
        for component in ('simplewm', 'simplesuite'):
            data = prefix / 'share' / component; data.mkdir(parents=True)
            (data / 'install-manifest').write_text(f'{component}_source_sha={sha}\n')
            (prefix / 'bin' / component).write_text('old binaries')
        if failure == 'local-source':
            (prefix / 'share/simplewm/install-manifest').write_text('simplewm_source_sha=local-' + '0' * 64 + '\n')
        work = base / 'work'; work.mkdir()
        pending = base / 'state/release-upgrade.json'
        commands, builds = [], []
        def transport(args, **kwargs):
            args = list(map(str, args)); commands.append(args)
            if args[0] == 'dpkg':
                text = 'unfinished package' if '--audit' in args and failure == 'audit' else ''
                if '--get-selections' in args:
                    text = 'base-files\tinstall\n'
                return subprocess.CompletedProcess(args, 0, stdout=text)
            if args[0] == 'apt-mark':
                return subprocess.CompletedProcess(args, 0, stdout='held-package' if failure == 'holds' else '')
            if args[0] == 'apt-get':
                assert 'simplewm-preflight' in builds, 'host APT started before the target build'
                if 'indextargets' in args:
                    codename = 'trixie' if 'trixie main' in sources.read_text() else 'bookworm'
                    return subprocess.CompletedProcess(args, 0, stdout=f'Debian|{codename}|main\n')
                if 'update' in args:
                    assert '-o' in args and 'APT::Update::Error-Mode=any' in args
                    assert '--allow-releaseinfo-change-suite' in args
                    assert '--allow-releaseinfo-change' not in args
                    assert '--allow-releaseinfo-change-codename' not in args
                if 'full-upgrade' in args:
                    counter[0] += 1
                    assert kwargs['interactive'] and '-y' not in args
                    if counter[0] == 2:
                        if failure == 'apt':
                            raise subprocess.CalledProcessError(100, args)
                        debian.write_text('ID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\n')
                if 'upgrade' in args or 'install' in args:
                    assert kwargs['interactive'] and '-y' not in args
                if 'install' in args:
                    assert counter[0] >= 2
                return subprocess.CompletedProcess(args, 0)
            if args[0] == 'ldd' or args[0].endswith('/bin/simplewm'):
                assert counter[0] >= 2
                if build_failure[0]:
                    raise RuntimeError('fixture upgraded runtime library missing')
                return subprocess.CompletedProcess(args, 0, stdout='libwlroots-fixture.so => all target libraries resolved\n')
            if args[:2] == ['pkg-config', '--libs-only-l']:
                return subprocess.CompletedProcess(args, 0, stdout='-lwlroots-fixture\n')
            if args[0] != 'git':
                raise AssertionError(f'unexpected command: {args}')
            if 'fetch' in args and args[-2] == 'origin':
                if failure == 'fetch' or (failure == 'wm-fetch' and args[args.index('-C') + 1].endswith('/simplewm')):
                    raise OSError('fixture Git unreachable')
                args = ['protocol.file.allow=always' if arg == 'protocol.file.allow=never' else arg for arg in args]
                args[-2] = str(upstream)
            return real_run(args, **kwargs)
        counter = [0]
        build_failure = [failure == 'wm-build']
        def preflight(args, target, prepared, work, environment, demote, uid, gid):
            assert counter[0] == 0 and update.debian_release() == (12, 'bookworm')
            assert sources.read_text() == original_sources and not pending.exists()
            if failure == 'preflight-env':
                raise RuntimeError('fixture target environment creation failed')
            builds.append('simplewm-preflight')
            if failure == 'preflight-build':
                raise RuntimeError('fixture compiler: incompatible wlroots API')
            local = work / 'prebuilt'; (local / 'bin').mkdir(parents=True)
            (local / 'bin/simplewm').write_text('rebuilt against trixie')
            data = local / 'share/simplewm'; data.mkdir(parents=True)
            (data / 'config').write_text('verified target defaults')
            (data / 'install-manifest').write_text(f'simplewm_source_sha={sha}\n')
            proof = {'target': list(target), 'wm_sha': sha, 'wm_packages': ['libwlroots-fixture-dev=1'],
                     'suite_packages': ['fixture-suite-dev=1'], 'pkg_config': ['wlroots-fixture'],
                     'digest': update.payload_digest(local)}
            return local, proof
        def payload(component):
            def compile_fixture(source, stage, revision, environment, demote, verify=False):
                assert update.debian_release() == (13, 'trixie')
                builds.append(component)
                if build_failure[0] and component == 'simplewm':
                    raise RuntimeError('fixture rebuild needs source changes')
                local = stage / 'usr/local'; (local / 'bin').mkdir(parents=True)
                (local / 'bin' / component).write_text('rebuilt against trixie')
                data = local / 'share' / component; data.mkdir(parents=True)
                (data / 'install-manifest').write_text(f'{component}_source_sha={revision}\n')
                return local
            return compile_fixture
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            for name, value in (('APT_ROOT', apt), ('SYSTEM_CONFIG', config), ('PREFIX', prefix),
                                ('OS_RELEASE', os_release), ('DEBIAN_OS_RELEASE', debian),
                                ('BACKUPS', base / 'backups'), ('LOG_STREAM', output),
                                ('PENDING_RELEASE', pending),
                                ('PACKAGE_STATE', (package_state,)),
                                ('MANIFEST', prefix / 'share/simplesuite/install-manifest'),
                                ('WM_MANIFEST', prefix / 'share/simplewm/install-manifest')):
                stack.enter_context(patch.object(update, name, value))
            stack.enter_context(patch.object(update, 'require_console'))
            stack.enter_context(patch.object(update, 'target_preflight', side_effect=preflight))
            stack.enter_context(patch('builtins.input', return_value='' if failure == 'final-decline' else 'trixie'))
            if failure == 'switch':
                real_write = update.write_apt_sources
                def interrupted_write(changes, **kwargs):
                    if any('trixie main' in text for text in changes.values()):
                        first = next(iter(changes))
                        real_write({first: changes[first]}, **kwargs)
                        raise KeyboardInterrupt('fixture interruption during source changes')
                    real_write(changes, **kwargs)
                stack.enter_context(patch.object(update, 'write_apt_sources', side_effect=interrupted_write))
            stack.enter_context(patch.object(update, 'run', side_effect=transport))
            stack.enter_context(patch.object(update.shutil, 'which', return_value=None if failure == 'tools' else '/fixture/tool'))
            stack.enter_context(patch.object(update.pwd, 'getpwuid', return_value=update.pwd.struct_passwd(
                ('fixture', 'x', os.getuid(), os.getgid(), '', str(home), '/bin/sh'))))
            stack.enter_context(patch.object(update, 'build_and_test', side_effect=payload('simplesuite')))
            stack.enter_context(patch.object(update, 'build_and_test_wm', side_effect=payload('simplewm')))
            stack.enter_context(contextlib.redirect_stdout(output))
            args = options(release_upgrade=True)
            try:
                update.upgrade_release(args, (12, 'bookworm'), (13, 'trixie'), work, env, None,
                                       os.getuid(), os.getgid(), output)
                assert failure in (None, 'final-decline')
            except (OSError, RuntimeError, subprocess.CalledProcessError, KeyboardInterrupt):
                assert failure is not None, output.getvalue()
            if failure in ('fetch', 'wm-fetch', 'local-source', 'tools', 'audit', 'holds',
                           'preflight-env', 'preflight-build', 'final-decline'):
                assert not any(command[0] == 'apt-get' for command in commands)
                assert sources.read_text() == original_sources
                assert builds == (['simplewm-preflight'] if failure in ('preflight-build', 'final-decline') else [])
                assert not (base / 'backups').exists()
                assert not pending.exists()
            else:
                backup, = (base / 'backups').iterdir()
                assert backup.stat().st_mode & 0o777 == 0o700
                assert (backup / sources.relative_to('/')).read_text() == original_sources
                assert (backup / personal.relative_to('/')).read_text() == 'personal colors'
                assert (backup / package_state.relative_to('/')).read_text() == 'saved package database'
                with tarfile.open(backup / 'linked-configuration.tar.gz') as archive:
                    assert archive.extractfile(str((home / '.config/simplefiles/config').relative_to('/'))).read() == b'linked settings'
                    assert archive.extractfile(str((home / '.profile').relative_to('/'))).read() == b'linked settings'
                assert (external / 'config').read_text() == 'linked settings'
                assert (backup / 'package-selections').read_text() == 'base-files\tinstall\n'
                assert 'trixie main' in sources.read_text()
                assert ('Enabled: no' in vendor.read_text()) == (failure != 'switch')
                assert personal.read_text() == 'personal colors'
                if failure in ('switch', 'apt'):
                    assert builds == ['simplewm-preflight']
                    before = len(commands)
                    fails(lambda: update.require_release_recovery(
                        options(rebuild=True), update.pending_release(), update.debian_release()),
                        'has not reached the approved release')
                    assert len(commands) == before
                else:
                    assert commands.index(['apt-get', 'upgrade', '--without-new-pkgs']) < next(
                        i for i, command in enumerate(commands) if command[0] == 'apt-get' and 'install' in command)
                    assert update.debian_release() == (13, 'trixie')
                    assert 'VERSION_CODENAME=trixie' in brand.read_text()
                    assert 'VERSION_ID="0.8"' in brand.read_text()
                    assert builds == ['simplewm-preflight', 'simplesuite']  # Unchanged SHAs still rebuild.
                    assert (prefix / 'bin/simplesuite').read_text() == 'rebuilt against trixie'
                    assert (prefix / 'bin/simplewm').read_text() == ('old binaries' if failure == 'wm-build' else 'rebuilt against trixie')
                if failure:
                    assert 'has not been rolled back' in output.getvalue()
                    assert update.pending_release()['target'] == [13, 'trixie']
                else:
                    assert not pending.exists()

            if failure == 'wm-build':
                # Restart through the real command entrypoint after APT finished
                # but the compositor rebuild failed. No host paths are writable.
                (base / 'run').mkdir(); (base / 'tmp').mkdir()
                real_mkdtemp = tempfile.mkdtemp
                def private_path(value, *parts):
                    relocated = {'/var/log/simpleupdate': base / 'logs',
                                 '/run/reboot-required': base / 'run/reboot-required'}
                    return Path(relocated.get(str(value), value), *parts)
                def private_open(value, *positional, **kwargs):
                    if str(value) == '/run/lock/simpleupdate.lock':
                        value = base / 'run/simpleupdate.lock'
                    return builtins.open(value, *positional, **kwargs)
                def private_temp(*positional, **kwargs):
                    if kwargs.get('dir') == '/var/tmp':
                        kwargs['dir'] = str(base / 'tmp')
                    return real_mkdtemp(*positional, **kwargs)
                for context in (
                        patch.dict(os.environ),
                        patch.object(update, 'Path', side_effect=private_path),
                        patch.object(update, 'open', side_effect=private_open, create=True),
                        patch.object(update.tempfile, 'mkdtemp', side_effect=private_temp),
                        patch.object(update.os, 'geteuid', return_value=0),
                        patch.object(update, 'build_identity', return_value=(os.getuid(), os.getgid())),
                        patch.object(update, 'as_user', return_value=None),
                        patch.object(update, 'wm_repository_exists', return_value=True)):
                    stack.enter_context(context)
                for flags in ([], ['--rebuild', '--wm-only']):
                    before = len(commands)
                    with patch.object(update.sys, 'argv', [str(script), *flags]):
                        fails(update.main, 'ordinary updates stay blocked')
                    assert len(commands) == before and pending.exists()
                    # The real RuntimeError must survive closing the transcript;
                    # previously the exception handler masked it with ValueError.
                    assert 'ordinary updates stay blocked' in output.getvalue()
                before = len(commands)
                with patch.object(update.sys, 'argv', [str(script), '--dry-run']), \
                     patch.object(update.os, 'geteuid', side_effect=AssertionError('dry run privilege check')):
                    update.main()
                assert pending.exists() and len(commands) == before
                with patch.object(update.sys, 'argv', [str(script), '--rebuild']), \
                     patch.object(update, 'require_console', side_effect=RuntimeError('fixture text console required')):
                    fails(update.main, 'text console required')
                assert pending.exists() and len(commands) == before
                with patch.object(update.sys, 'argv', [str(script), '--rebuild']), \
                     patch.object(update, 'install_preflight_wm', return_value=None):
                    fails(update.main, 'both components must rebuild')
                assert pending.exists()
                build_failure[0] = False
                with patch.object(update.sys, 'argv', [str(script), '--rebuild']):
                    update.main()
                assert not pending.exists()
                assert all((prefix / 'bin' / component).read_text() == 'rebuilt against trixie'
                           for component in ('simplewm', 'simplesuite'))
                assert 'Both release-recovery rebuilds completed' in output.getvalue()
                assert not any((base / 'tmp').iterdir())
    print('OK target build failures and declined final approval leave installed APT untouched; successful target compilation precedes all host APT')
    print('OK interactive APT prompts, two-part upgrade ordering, SimpleOS identity and honest recovery after package/build failures')
    print('OK actual APT index metadata, atomic symlink edits, linked backups and restart recovery requiring both rebuilds')
