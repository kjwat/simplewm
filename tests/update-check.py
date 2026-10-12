#!/usr/bin/python3
"""Failure injection proves an interrupted install restores real files."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import io
import argparse
from unittest.mock import patch

path = Path(__file__).resolve().parent.parent / 'scripts/simpleupdate'
loader = importlib.machinery.SourceFileLoader('simpleupdate', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
update = importlib.util.module_from_spec(spec)
loader.exec_module(update)
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
            update.build_and_test(root, root, '0'*40, {}, None)
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
            update.build_and_test_wm(root, root, '0'*40, {}, None)
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
