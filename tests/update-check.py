#!/usr/bin/python3
"""Failure injection proves an interrupted install restores real files."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import io
import argparse
import contextlib
import subprocess
from unittest.mock import patch

path = Path(__file__).resolve().parent.parent / 'scripts/simpleupdate'
loader = importlib.machinery.SourceFileLoader('simpleupdate', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
update = importlib.util.module_from_spec(spec)
loader.exec_module(update)
with patch.dict(update.os.environ, {'SUDO_UID': str(update.os.getuid())}):
    unprivileged = update.pwd.getpwnam('nobody')
    assert update.build_identity() == (unprivileged.pw_uid, unprivileged.pw_gid)
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    prefix = root / 'local'
    stage = root / 'stage'
    (prefix / 'bin').mkdir(parents=True)
    (stage / 'bin').mkdir(parents=True)
    (prefix / 'bin/simplewords').write_text('working old editor')
    (prefix / 'bin/simplenote').write_text('working old notes')
    (stage / 'bin/simplewords').write_text('tested new editor')
    (stage / 'bin/simplenote').write_text('tested new notes')
    config = root / 'home/.config/simplewords/config'
    config.parent.mkdir(parents=True)
    config.write_text('personal settings')
    data = root / 'home/writing/draft.txt'
    data.parent.mkdir(parents=True)
    data.write_text('irreplaceable prose')
    replace = update.os.replace
    def fail_after_first(source, target):
        if str(source).endswith('/new/bin/simplewords'):
            raise OSError('simulated disk failure after first binary')
        replace(source, target)
    with patch.object(update.os, 'replace', side_effect=fail_after_first):
        try:
            update.install_transaction(stage, prefix)
            raise AssertionError('failure was not injected')
        except OSError:
            pass
    assert (prefix / 'bin/simplewords').read_text() == 'working old editor'
    assert (prefix / 'bin/simplenote').read_text() == 'working old notes'
    update.install_transaction(stage, prefix)
    assert (prefix / 'bin/simplewords').read_text() == 'tested new editor'
    assert config.read_text() == 'personal settings'
    assert data.read_text() == 'irreplaceable prose'
    # A compiled source must not be installed if its tests fail.
    with patch.object(update, 'run', side_effect=[None, RuntimeError('test failed')]), \
         patch.object(update, 'install_transaction') as install:
        try:
            update.build_and_test(root, root, '0'*40, {}, None, verify=True)
            raise AssertionError('test failure did not stop staging')
        except RuntimeError:
            pass
        install.assert_not_called()
    (stage / 'bin/escape').symlink_to('/etc/shadow')
    try:
        update.validate_local(stage)
        raise AssertionError('escaped symlink was accepted')
    except RuntimeError:
        pass
    (stage / 'bin/escape').unlink()
    # SimpleWM's source snapshot and binaries are rolled back together.
    for base in (stage, prefix):
        (base / 'share/simplewm/source').mkdir(parents=True)
    (prefix / 'bin/simplewm').write_text('working compositor')
    (prefix / 'share/simplewm/source/config').write_text('old defaults')
    (stage / 'bin/simplewm').write_text('tested compositor')
    (stage / 'share/simplewm/source/config').write_text('new defaults')
    def fail_source(source, target):
        if str(source).endswith('/new/share/simplewm/source'):
            raise OSError('simulated source install failure')
        replace(source, target)
    with patch.object(update.os, 'replace', side_effect=fail_source):
        try:
            update.install_transaction(stage, prefix)
            raise AssertionError('SimpleWM failure was not injected')
        except OSError:
            pass
    assert (prefix / 'bin/simplewm').read_text() == 'working compositor'
    assert (prefix / 'share/simplewm/source/config').read_text() == 'old defaults'
    # A SimpleWM test failure cannot reach make install or the transaction.
    with patch.object(update, 'run', side_effect=[None, RuntimeError('config test failed')]), \
         patch.object(update, 'install_transaction') as install:
        try:
            update.build_and_test_wm(root, root, '0'*40, {}, None, verify=True)
            raise AssertionError('SimpleWM test failure was ignored')
        except RuntimeError:
            pass
        install.assert_not_called()
    opts = argparse.Namespace(wm_local=None, rebuild=False, check=False)
    with patch.object(update, 'installed_revision', return_value='local-' + '0'*64), \
         patch.object(update, 'wm_repository_exists', return_value=False), \
         patch.object(update, 'build_and_test_wm') as build:
        update.update_wm(opts, root, {}, None, 0, 0, io.StringIO())
        build.assert_not_called()
print('OK Suite/SimpleWM partial-install rollback, failed build/test containment, user preservation, staged paths, and unpublished-repository handling')

# The ordinary update path must never invoke the slow release gate.
for verify in (False, True):
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); source=root/'source'; source.mkdir()
        (source/'install-simpleplay.sh').write_text('#!/bin/sh\n')
        stage=root/'stage'; local=stage/'usr/local'
        (local/'bin').mkdir(parents=True)
        (local/'share/simplesuite').mkdir(parents=True)
        (local/'share/simplesuite/install-manifest').write_text('simplesuite_source_sha='+'0'*40+'\n')
        with patch.object(update, 'run') as runner:
            update.build_and_test(source, stage, '0'*40, {}, None, verify=verify)
        commands=[call.args[0] for call in runner.call_args_list]
        assert any('release-simplewords' in command for command in commands)==verify
        assert any(command[0] == 'make' and all(target in command for target in ('all', 'simpleterm', 'simpleplay'))
                   for command in commands), 'SimpleTerm and SimplePlay must build with every changed Suite release'
        terminal_install = next(call for call in runner.call_args_list
                                if str(source / 'install-simpleterm.sh') in call.args[0])
        assert terminal_install.args[0] == ['sh', str(source / 'install-simpleterm.sh'), '--no-deps']
        assert terminal_install.kwargs['env']['DESTDIR'] == str(stage)
        assert terminal_install.kwargs['env']['SIMPLETERM_NONINTERACTIVE'] == '1'
        player_install = next(call for call in runner.call_args_list
                              if str(source / 'install-simpleplay.sh') in call.args[0])
        assert player_install.args[0] == ['sh', str(source / 'install-simpleplay.sh'), '--no-deps']
        assert player_install.kwargs['env']['DESTDIR'] == str(stage)
        assert player_install.kwargs['env']['SIMPLEPLAY_NONINTERACTIVE'] == '1'
        assert player_install.kwargs['env']['SIMPLEPLAY_HEADLESS_ONLY'] == '0'
        for package in ('libavcodec-dev', 'libsdl2-dev', 'libass-dev', 'libfluidsynth-dev',
                        'libsidplayfp-dev', 'libjson-glib-dev', 'timgm6mb-soundfont'):
            assert package in update.BUILD_PACKAGES
print('OK normal updates stage SimpleTerm, SimplePlay and its core; --verify explicitly enables developer tests')

for verify in (False, True):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); source = root / 'source'; source.mkdir()
        (source / 'Makefile').write_text('full:\ninstall-full:\ntest-full:\n')
        stage = root / 'stage'; local = stage / 'usr/local'
        (local / 'bin').mkdir(parents=True)
        data = local / 'share/simplesuite'; data.mkdir(parents=True)
        (data / 'install-manifest').write_text('simplesuite_source_sha=' + '0' * 40 + '\n')
        with patch.object(update, 'run') as runner:
            update.build_and_test(source, stage, '0' * 40, {}, None, verify=verify)
        commands = [call.args[0] for call in runner.call_args_list]
        assert any(command[0] == 'make' and command[-1] == 'full' for command in commands)
        assert any(command[0] == 'make' and command[-1] == 'install-full' for command in commands)
        assert any('test-full' in command for command in commands) == verify
        assert not any(command[0] == 'sh' for command in commands), 'new sources own their complete installation'
print('OK current Suite owns full build/install/test packaging; updater needs no application-name changes')

# Exercise the real Git object check with a freshly initialized repository.
# Replace only the network transport with an isolated local upstream fixture.
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp); upstream = root / 'upstream'; home = root / 'home'; home.mkdir()
    env = update.safe_environment(home)
    def git(*args):
        return subprocess.run(['git', *map(str, args)], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init', '--quiet', '-b', 'main', upstream)
    (upstream / 'config').write_text('published source\n')
    git('-C', upstream, 'add', 'config')
    git('-C', upstream, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        'commit', '--quiet', '-m', 'published')
    published = git('-C', upstream, 'rev-parse', 'HEAD')
    runner = update.run
    def local_transport(args, **kwargs):
        args = list(args)
        if 'fetch' in args and args[-2] == 'origin':
            args = ['protocol.file.allow=always' if a == 'protocol.file.allow=never' else a for a in args]
            args[-2] = str(upstream)
        return runner(args, **kwargs)
    for index, origin in enumerate((update.OFFICIAL, update.OFFICIAL_WM)):
        source = root / f'source-{index}'
        output = io.StringIO()
        with patch.object(update, 'run', side_effect=local_transport), \
             patch.object(update, 'LOG_STREAM', output), contextlib.redirect_stdout(output):
            fetched = update.fetch_source(source, env, None, origin)
        assert fetched == published
        assert (source / 'config').read_text() == 'published source\n'
        assert git('-C', source, 'rev-parse', 'HEAD') == published
        assert not any(message in output.getvalue() for message in
                       ('unborn', 'No default references', 'dangling commit'))
    # An older published release is a successful no-update result, without a
    # rebuild or downgrade. Keep real bundle fetching and ancestry checking.
    (upstream / 'config').write_text('bundled source\n')
    git('-C', upstream, 'add', 'config')
    git('-C', upstream, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        'commit', '--quiet', '-m', 'bundled')
    installed = git('-C', upstream, 'rev-parse', 'HEAD')
    prefix = root / 'local'; data = prefix / 'share/simplewm'; data.mkdir(parents=True)
    git('-C', upstream, 'bundle', 'create', data / 'source.bundle', 'main')
    git('-C', upstream, 'update-ref', 'refs/heads/main', published)
    work = root / 'work'; work.mkdir()
    output = io.StringIO()
    with patch.object(update, 'run', side_effect=local_transport), \
         patch.object(update, 'LOG_STREAM', output), contextlib.redirect_stdout(output), \
         patch.object(update, 'PREFIX', prefix), \
         patch.object(update, 'installed_revision', return_value=installed), \
         patch.object(update, 'wm_repository_exists', return_value=True), \
         patch.object(update, 'build_and_test_wm') as build, \
         patch.object(update, 'install_transaction') as install:
        update.update_wm(argparse.Namespace(wm_local=None, rebuild=False, check=False),
                         work, env, None, 0, 0, output)
    build.assert_not_called(); install.assert_not_called()
    assert 'no newer published release; no update needed' in output.getvalue()
    assert not any(message in output.getvalue() for message in
                   ('unborn', 'No default references', 'dangling commit', 'Update failed'))
print('OK real Git fetch/object verification is quiet; older upstream preserves the bundled release')
