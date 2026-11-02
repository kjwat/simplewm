#!/usr/bin/python3
"""Exercise both update decisions with real Git histories and file transactions.

Only HTTPS transport, package installation and compilation are substituted.
Commit comparison, object verification, bundles and installation are real.
"""
import argparse
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

path = Path(__file__).resolve().parent.parent / 'scripts/simpleupdate'
loader = importlib.machinery.SourceFileLoader('simpleupdate_logic', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
update = importlib.util.module_from_spec(spec)
loader.exec_module(update)

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    home = root / 'home'; home.mkdir()
    env = update.safe_environment(home)
    env |= {'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
            'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid'}
    def git(*args):
        return subprocess.run(['git', *map(str, args)], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()
    upstream = root / 'upstream'
    git('init', '--quiet', '-b', 'main', upstream)
    (upstream / 'build-fixture.c').write_text('{}\n')
    git('-C', upstream, 'add', 'build-fixture.c')
    def commit(text):
        (upstream / 'config').write_text(text)
        git('-C', upstream, 'add', 'config')
        git('-C', upstream, 'commit', '--quiet', '-m', text)
        return git('-C', upstream, 'rev-parse', 'HEAD')
    old = commit('old release')
    installed = commit('installed release')
    newer = commit('new release')
    git('-C', upstream, 'checkout', '--quiet', '-B', 'divergent', old)
    divergent = commit('different branch')
    git('-C', upstream, 'checkout', '--quiet', 'main')
    runner = update.run
    def local_transport(args, **kwargs):
        args = list(map(str, args))
        if args[0] == 'apt-get':
            return subprocess.CompletedProcess(args, 0)
        if 'fetch' in args and args[-2] == 'origin':
            args = ['protocol.file.allow=always' if a == 'protocol.file.allow=never' else a for a in args]
            args[-2] = str(upstream)
        return runner(args, **kwargs)
    build_calls = []
    def compiled_payload(source, stage, sha, environment, demote, verify=False):
        build_calls.append((sha, verify))
        local = stage / 'usr/local'
        (local / 'bin').mkdir(parents=True)
        (local / 'bin/program').write_text((source / 'config').read_text())
        for component, key in (('simplesuite', 'simplesuite_source_sha'),
                               ('simplewm', 'simplewm_source_sha')):
            data = local / 'share' / component; data.mkdir(parents=True)
            (data / 'install-manifest').write_text(f'{key}={sha}\n')
            git('-C', source, 'branch', '-f', 'main', sha)
            git('-C', source, 'bundle', 'create', data / 'source.bundle', 'main')
        return local
    def invoke(component, prefix, work, transport=None, **options):
        args = argparse.Namespace(wm_local=None, check=False, rebuild=False, verify=False)
        vars(args).update(options)
        output = io.StringIO()
        with patch.object(update, 'PREFIX', prefix), \
             patch.object(update, 'MANIFEST', prefix / 'share/simplesuite/install-manifest'), \
             patch.object(update, 'WM_MANIFEST', prefix / 'share/simplewm/install-manifest'), \
             patch.object(update, 'run', side_effect=transport or local_transport), \
             patch.object(update, 'build_and_test', side_effect=compiled_payload), \
             patch.object(update, 'build_and_test_wm', side_effect=compiled_payload), \
             patch.object(update, 'wm_repository_exists', return_value=True), \
             patch.object(update, 'LOG_STREAM', output), contextlib.redirect_stdout(output):
            function = update.update_suite if component == 'simplesuite' else update.update_wm
            function(args, work, env, None, os.getuid(), os.getgid(), output)
        return output.getvalue()
    def prepare(name, current=installed, bundle=True):
        base = root / name; base.mkdir()
        prefix = base / 'local'; (prefix / 'bin').mkdir(parents=True)
        (prefix / 'bin/program').write_text('working installed release')
        for component, key in (('simplesuite', 'simplesuite_source_sha'),
                               ('simplewm', 'simplewm_source_sha')):
            data = prefix / 'share' / component; data.mkdir(parents=True)
            (data / 'install-manifest').write_text(f'{key}={current}\n')
            if bundle:
                git('-C', upstream, 'update-ref', 'refs/heads/bundled', installed)
                # A separate bare repository provides the exact shipped main ref.
                bundled = base / (component + '-bundle.git')
                git('init', '--quiet', '--bare', bundled)
                git('-C', bundled, 'fetch', '--quiet', upstream, 'bundled:main')
                git('-C', bundled, 'bundle', 'create', data / 'source.bundle', 'main')
        work = base / 'work'; work.mkdir()
        return prefix, work
    count = 0
    for component in ('simplesuite', 'simplewm'):
        for case, published, changed, options in (
                ('unchanged', installed, False, {}),
                ('newer', newer, True, {}),
                ('older', old, False, {}),
                ('divergent', divergent, False, {}),
                ('check-newer', newer, False, {'check': True}),
                ('rebuild-current', installed, True, {'rebuild': True}),
                ('rebuild-older', old, False, {'rebuild': True})):
            prefix, work = prepare(component + '-' + case)
            git('-C', upstream, 'update-ref', 'refs/heads/main', published)
            build_calls.clear()
            output = invoke(component, prefix, work, **options)
            assert len(build_calls) == int(changed), (component, case, output)
            key = component + '_source_sha'
            revision = update.installed_revision(prefix / f'share/{component}/install-manifest', key)
            assert revision == (published if changed else installed), (component, case)
            assert (prefix / 'bin/program').read_text() == (
                git('-C', upstream, 'show', published + ':config') if changed else 'working installed release')
            assert not any(text in output for text in ('unborn', 'dangling commit', 'Update failed'))
            count += 1
        # Older ISO snapshots without Git history must not be overwritten just
        # because the published SHA differs. Nor may explicit local builds be.
        for current in ('07942663f959637275b891461f2e7eed38b65b90', 'local-' + '1' * 64):
            prefix, work = prepare(component + '-' + current[:8], current, bundle=False)
            build_calls.clear()
            output = invoke(component, prefix, work)
            assert not build_calls
            assert (prefix / 'bin/program').read_text() == 'working installed release'
            assert update.installed_revision(prefix / f'share/{component}/install-manifest',
                                             component + '_source_sha') == current
            count += 1
        # A fetch failure and damaged installed history are errors, never a
        # fabricated successful no-update result or a partial installation.
        for failure in ('network', 'bundle', 'provenance'):
            prefix, work = prepare(component + '-failed-' + failure)
            git('-C', upstream, 'update-ref', 'refs/heads/main', newer)
            build_calls.clear()
            if failure == 'bundle':
                (prefix / f'share/{component}/source.bundle').write_bytes(b'not a git bundle')
                failing_transport = local_transport
            elif failure == 'provenance':
                (prefix / f'share/{component}/install-manifest').write_text(
                    component + '_source_sha=' + 'd' * 40 + '\n')
                failing_transport = local_transport
            else:
                def failing_transport(args, **kwargs):
                    if 'fetch' in args and args[-2] == 'origin':
                        raise OSError('fixture network failure')
                    return local_transport(args, **kwargs)
            try:
                invoke(component, prefix, work, transport=failing_transport)
                raise AssertionError('update failure was treated as success')
            except (OSError, RuntimeError, subprocess.CalledProcessError):
                pass
            assert not build_calls
            assert (prefix / 'bin/program').read_text() == 'working installed release'
            count += 1
    # The known 0.8 snapshot can receive the published successor without
    # treating unknown or edited local releases as automatically older.
    legacy = '07942663f959637275b891461f2e7eed38b65b90'
    for case, published, modified, changed in (
            ('matching', newer, False, True),
            ('modified', newer, True, False),
            ('divergent', divergent, False, False)):
        prefix, work = prepare('legacy-suite-' + case, legacy, bundle=False)
        snapshot = prefix / 'share/simplesuite/source'; snapshot.mkdir()
        (snapshot / 'config').write_text('original 0.8 terminal fixes')
        expected = update.source_digest(snapshot)
        if modified:
            (snapshot / 'config').write_text('personal local terminal changes')
        git('-C', upstream, 'update-ref', 'refs/heads/main', published)
        build_calls.clear()
        with patch.object(update, 'LEGACY_SUITE_RELEASES', {legacy: (expected, installed)}):
            output = invoke('simplesuite', prefix, work)
        assert len(build_calls) == int(changed), (case, output)
        assert update.installed_revision(prefix / 'share/simplesuite/install-manifest') == (
            newer if changed else legacy)
        if changed:
            assert 'verified the original 0.8 source snapshot' in output
        count += 1
    # The 1.0 ISO's exact local WM snapshot may advance to its published
    # successor. An edited, unknown, absent or linked snapshot is still local;
    # neither an older nor a divergent published history may replace it.
    for case, published, changed in (
            ('matching', newer, True),
            ('modified', newer, False),
            ('unknown', newer, False),
            ('missing', newer, False),
            ('symlink', newer, False),
            ('missing-ancestor', newer, False),
            ('older', old, False),
            ('divergent', divergent, False)):
        prefix, work = prepare('legacy-wm-' + case, bundle=False)
        snapshot = prefix / 'share/simplewm/source'; snapshot.mkdir()
        (snapshot / 'config').write_text('original 1.0 session fixes')
        expected = update.source_digest(snapshot)
        current = 'local-' + '0' * 64 if case == 'unknown' else expected
        manifest = prefix / 'share/simplewm/install-manifest'
        manifest.write_text('simplewm_source_sha=' + current + '\n')
        if case == 'modified':
            (snapshot / 'config').write_text('personal local session changes')
        elif case == 'missing':
            (snapshot / 'config').unlink(); snapshot.rmdir()
        elif case == 'symlink':
            target = prefix / 'linked-source'
            snapshot.rename(target); snapshot.symlink_to(target, target_is_directory=True)
        git('-C', upstream, 'update-ref', 'refs/heads/main', published)
        build_calls.clear()
        base = 'd' * 40 if case == 'missing-ancestor' else installed
        with patch.object(update, 'LEGACY_WM_RELEASES', {expected: base}):
            output = invoke('simplewm', prefix, work)
        assert len(build_calls) == int(changed), (case, output)
        assert update.installed_revision(manifest, 'simplewm_source_sha') == (newer if changed else current)
        assert (prefix / 'bin/program').read_text() == (
            git('-C', upstream, 'show', newer + ':config') if changed else 'working installed release')
        if changed:
            assert 'verified the original 1.0 ISO source snapshot' in output
        count += 1
    # Source snapshots must preserve tracked build-* files, not build outputs.
    source_files = root / 'source-files'; source_files.mkdir()
    (source_files / 'build-dependencies.json').write_text('{}')
    (source_files / 'build-temp').mkdir(); (source_files / 'build-temp/output').write_text('binary')
    (source_files / 'build').mkdir()
    __import__('shutil').copytree(source_files, root / 'copied-source', ignore=update.source_build_ignores)
    assert (root / 'copied-source/build-dependencies.json').read_text() == '{}'
    assert not (root / 'copied-source/build-temp').exists() and not (root / 'copied-source/build').exists()
    # An explicit resume verifies the actual snapshot against a published base,
    # including when rollback provenance contains an obsolete local digest.
    for case, published, allowed, follow in (
            ('exact', newer, True, True), ('stale-digest', newer, True, True),
            ('no-opt-in', newer, False, False), ('modified', newer, False, True),
            ('extra-file', newer, False, True), ('missing-file', newer, False, True),
            ('symlink', newer, False, True), ('snapshot-link', newer, False, True),
            ('executable-bit', newer, False, True), ('missing-base', newer, False, True),
            ('unknown-base', newer, False, True), ('older', old, False, True),
            ('divergent', divergent, False, True)):
        prefix, work = prepare('resume-wm-' + case, bundle=False)
        snapshot = prefix / 'share/simplewm/source'; snapshot.mkdir()
        (snapshot / 'config').write_text('installed release')
        (snapshot / 'build-fixture.c').write_text('{}\n')
        digest = update.source_digest(snapshot)
        if case == 'stale-digest': digest = 'local-' + 'e' * 64
        manifest = prefix / 'share/simplewm/install-manifest'
        base = '' if case == 'missing-base' else 'd' * 40 if case == 'unknown-base' else installed
        manifest.write_text(f'simplewm_source_sha={digest}\nbase_source_sha={base}\nrollback_pinned=yes\n')
        if case == 'modified': (snapshot / 'config').write_text('personal edits')
        if case == 'extra-file': (snapshot / 'extra').write_text('custom source')
        if case == 'missing-file': (snapshot / 'config').unlink()
        if case == 'executable-bit': (snapshot / 'config').chmod(0o755)
        if case == 'symlink':
            (snapshot / 'config').unlink(); (snapshot / 'config').symlink_to(upstream / 'config')
        if case == 'snapshot-link':
            target = snapshot.with_name('linked'); snapshot.rename(target); snapshot.symlink_to(target)
        git('-C', upstream, 'update-ref', 'refs/heads/main', published)
        build_calls.clear()
        output = invoke('simplewm', prefix, work, follow_upstream=follow)
        assert len(build_calls) == int(allowed), (case, output)
        assert update.installed_revision(manifest, 'simplewm_source_sha') == (newer if allowed else digest)
        if allowed:
            assert 'rollback_pinned' not in manifest.read_text()
            assert 'resuming upstream updates' in output
        if case == 'stale-digest':
            # After the one-time adoption, a subsequent commit advances normally
            # without --follow-upstream; the new commit is not another pin.
            future = commit('future upstream release')
            next_work = work.with_name('next-work'); next_work.mkdir()
            build_calls.clear()
            invoke('simplewm', prefix, next_work)
            assert len(build_calls) == 1 and build_calls[0][0] == future
            assert update.installed_revision(manifest, 'simplewm_source_sha') == future
        count += 1
    # A corrupted fetched commit must fail the actual fsck before checkout.
    source = root / 'damaged-fetch'
    def damage_after_fetch(args, **kwargs):
        if 'fsck' in args:
            sha = git('-C', source, 'rev-parse', 'FETCH_HEAD')
            obj = source / '.git/objects' / sha[:2] / sha[2:]
            obj.parent.mkdir(exist_ok=True)
            if obj.exists():
                obj.chmod(0o644)
            obj.write_bytes(b'damaged object')
        return local_transport(args, **kwargs)
    output = io.StringIO()
    with patch.object(update, 'run', side_effect=damage_after_fetch), \
         patch.object(update, 'LOG_STREAM', output), contextlib.redirect_stdout(output):
        try:
            update.fetch_source(source, env, None)
            raise AssertionError('corrupt source was accepted')
        except subprocess.CalledProcessError:
            pass
    assert not (source / 'config').exists()
    # Leave a real journal behind by exiting the installer process abruptly.
    # The next invocation must recover the old payload and provenance together.
    prefix = root / 'crash-local'; stage = root / 'crash-stage'
    for base, text in ((prefix, 'old'), (stage, 'new')):
        (base / 'bin').mkdir(parents=True)
        for name in ('first', 'second'):
            (base / 'bin' / name).write_text(text)
        data = base / 'share/simplewm'; data.mkdir(parents=True)
        (data / 'install-manifest').write_text(text)
    child = '''
import importlib.machinery, importlib.util, os, sys
from pathlib import Path
loader = importlib.machinery.SourceFileLoader('crash_update', sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec); loader.exec_module(module)
replace = module.os.replace
def crash(source, target):
    if str(source).endswith('/new/bin/second'):
        os._exit(75)
    return replace(source, target)
module.os.replace = crash
module.install_transaction(Path(sys.argv[2]), Path(sys.argv[3]))
'''
    result = subprocess.run([sys.executable, '-c', child, str(path), str(stage), str(prefix)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 75, result.stderr
    assert (prefix / 'bin/first').read_text() == 'new'
    assert (prefix / 'share/simplewm/install-manifest').read_text() == 'old'
    update.recover_transaction(prefix)
    assert all((prefix / 'bin' / name).read_text() == 'old' for name in ('first', 'second'))
    assert (prefix / 'share/simplewm/install-manifest').read_text() == 'old'
    assert not (prefix / '.simpleupdate-transaction').exists()
    update.install_transaction(stage, prefix)
    assert all((prefix / 'bin' / name).read_text() == 'new' for name in ('first', 'second'))
    assert (prefix / 'share/simplewm/install-manifest').read_text() == 'new'
print(f'OK {count} Suite/WM decisions and failures, corrupt-source rejection, and recovery after abrupt process exit')
