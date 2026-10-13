#!/usr/bin/python3
"""Target environment contracts and real fixture compilation; no host APT mutations."""
import argparse
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

script = Path(__file__).resolve().parent.parent / 'scripts/simpleupdate'
loader = importlib.machinery.SourceFileLoader('target_update_check', str(script))
spec = importlib.util.spec_from_loader(loader.name, loader)
update = importlib.util.module_from_spec(spec); loader.exec_module(update)

def rejected(action, message):
    try:
        action()
    except RuntimeError as error:
        assert message in str(error), error
    else:
        raise AssertionError(f'expected rejection: {message}')

with tempfile.TemporaryDirectory(prefix='simpleupdate-target-check-') as temporary:
    base = Path(temporary)
    source = base / 'source'; source.mkdir()
    (source / 'Makefile').write_text('PKGS = wlroots-0.18 wayland-server xkbcommon\n')
    commands = []
    def metadata(command, **kwargs):
        commands.append(command)
        if command[:2] == ['apt-cache', 'search']:
            output = 'libwlroots-0.18-dev - old\nlibwlroots-8.42-dev - future\nlibwlroots-9.0-dev - unavailable\n'
        elif command[:2] == ['apt-cache', 'policy']:
            output = '  Candidate: ' + {'libwlroots-0.18-dev': '0.18.2-3',
                'libwlroots-8.42-dev': '8.42.1-1', 'libwlroots-9.0-dev': '(none)'}[command[-1]] + '\n'
        elif command[:2] == ['dpkg-query', '-L']:
            assert command[-1] == 'libwlroots-8.42-dev'
            output = '/usr/lib/native/pkgconfig/wlroots-8.42.pc\n'
        elif command[:2] == ['pkg-config', '--exists']:
            assert command[2:] == ['wlroots-8.42', 'wayland-server', 'xkbcommon']
            output = ''
        elif command[:2] == ['pkg-config', '--modversion']:
            output = '8.42.1\n'
        else:
            raise AssertionError(f'non-metadata command: {command}')
        return subprocess.CompletedProcess(command, 0, stdout=output)
    with patch.object(update, 'run', side_effect=metadata), contextlib.redirect_stdout(io.StringIO()):
        packages, modules = update.discover_wm_dependencies(source)
        assert 'libwlroots-8.42-dev' in packages and 'libwlroots-0.18-dev' not in packages
        assert update.wm_pkg_config(packages, modules) == ['wlroots-8.42', 'wayland-server', 'xkbcommon']
        # Future compatible Git sources can declare additional stable-named
        # dependencies without rewriting the updater's Python logic.
        (source / 'build-dependencies.json').write_text(json.dumps({
            'packages': ['build-essential', 'future-library-dev', 'libwlroots-0.18-dev'],
            'pkg_config': ['wlroots-0.18', 'wayland-server', 'xkbcommon']}))
        packages, modules = update.discover_wm_dependencies(source)
        assert packages == ['build-essential', 'future-library-dev', 'libwlroots-8.42-dev']
        assert modules == ['wayland-server', 'xkbcommon']
    with patch.object(update, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='')):
        rejected(lambda: update.discover_wm_dependencies(source), 'no installable wlroots')
    (source / 'build-dependencies.json').write_text('{"packages":["bad;command"],"pkg_config":["x"]}')
    rejected(lambda: update.discover_wm_dependencies(source), 'source must declare')
    (source / 'build-dependencies.json').unlink()
    installed = base / 'installed-wm-manifest'
    installed.write_text('simplewm_source_sha=' + '1' * 40 + '\nwlroots_pkg_config=wlroots-8.42\n')
    def subsequent_update(command, **kwargs):
        if command[0] == 'apt-get':
            assert 'install' in command and 'libwlroots-8.42-dev' in command
            assert 'libwlroots-0.18-dev' not in command
            return subprocess.CompletedProcess(command, 0)
        return metadata(command, **kwargs)
    def verified_payload(source, stage, sha, environment, demote, verify=False):
        assert environment['SIMPLEUPDATE_WM_PKGS'] == 'wlroots-8.42 wayland-server xkbcommon'
        return base / 'fixture-stage'
    options = argparse.Namespace(wm_local=None, check=False, rebuild=True, verify=False)
    following = base / 'following-update'; following.mkdir()
    with patch.object(update, 'WM_MANIFEST', installed), \
         patch.object(update, 'run', side_effect=subsequent_update), \
         patch.object(update, 'build_and_test_wm', side_effect=verified_payload), \
         patch.object(update, 'install_transaction') as install, contextlib.redirect_stdout(io.StringIO()):
        assert update.update_wm(options, following, {}, None, os.getuid(), os.getgid(), io.StringIO(),
                                prepared=(source, '1' * 40))
        install.assert_called_once()
    print('OK newest installable target wlroots ABI, actual pkg-config identity, source dependency declarations and fail-closed discovery')
    print('OK subsequent WM updates retain the target ABI instead of requesting obsolete development packages')
    with patch.object(update, 'run', side_effect=[
            subprocess.CompletedProcess([], 0, stdout='-lwlroots-8.42 -lother\n'),
            subprocess.CompletedProcess([], 0, stdout='libwlroots-0.18.so => old library\n')]):
        rejected(lambda: update.verify_wm_abi(base / 'binary', 'wlroots-8.42'), 'not linked against')
    with patch.object(update, 'run', side_effect=[
            subprocess.CompletedProcess([], 0, stdout='-lwlroots-8.42\n'),
            subprocess.CompletedProcess([], 0, stdout='libwlroots-8.42.so => target library\n')]):
        update.verify_wm_abi(base / 'binary', 'wlroots-8.42')

    for corrupt in (False, True):
        bootstrap = base / ('bootstrap-invalid' if corrupt else 'bootstrap-valid'); bootstrap.mkdir()
        def download(command, **kwargs):
            if command[:2] == ['apt-get', 'download']:
                assert command == ['apt-get', 'download', 'mmdebstrap'] and kwargs['cwd'] == bootstrap / 'bootstrap'
                (kwargs['cwd'] / 'mmdebstrap_1_all.deb').write_bytes(b'fixture authenticated package')
                return subprocess.CompletedProcess(command, 0)
            if command[:2] == ['apt-cache', 'show']:
                digest = hashlib.sha256(b'fixture authenticated package').hexdigest()
                if corrupt: digest = '0' * 64
                return subprocess.CompletedProcess(command, 0, stdout=
                    f'Filename: pool/mmdebstrap_1_all.deb\nSHA256: {digest}\n')
            if command[:2] == ['dpkg-deb', '--extract']:
                assert not corrupt
                executable = Path(command[-1]) / 'usr/bin/mmdebstrap'
                executable.parent.mkdir(parents=True); executable.write_text('fixture tool')
                return subprocess.CompletedProcess(command, 0)
            raise AssertionError(f'host package mutation: {command}')
        with patch.object(update.shutil, 'which', return_value=None), \
             patch.object(update.os, 'chown'), patch.object(update, 'run', side_effect=download):
            action = lambda: update.bootstrap_tool(bootstrap, {}, None, os.getuid(), os.getgid())
            if corrupt:
                rejected(action, 'does not match signed APT')
            else:
                assert Path(action()).is_file()
    print('OK absent bootstrap tool downloads/extracts privately with signed-index checksum verification; no host package installation')

    # Exercise environment creation, isolation command, result validation and
    # payload checks with a real C compiler and a deliberately incompatible API.
    for outcome in ('success', 'compiler', 'environment', 'forged-result', 'corrupt-payload'):
        work = base / outcome; work.mkdir()
        root = work / 'target-root'
        trace = []
        def environment(command, **kwargs):
            trace.append(command)
            if command == ['dpkg', '--print-architecture']:
                return subprocess.CompletedProcess(command, 0, stdout='amd64\n')
            if command[0] == '/fixture/mmdebstrap':
                assert '--mode=unshare' in command and '--architectures=amd64' in command
                assert 'future' in command and str(root) in command
                assert command[-3:] == ['deb https://deb.debian.org/debian future main',
                    'deb https://deb.debian.org/debian future-updates main',
                    'deb https://security.debian.org/debian-security future-security main']
                if outcome == 'environment':
                    raise RuntimeError('fixture environment creation failed')
                (root / 'usr/sbin').mkdir(parents=True); (root / 'proc').mkdir()
            elif command[0] == 'unshare':
                assert '--kill-child' in command and '--mount-proc=' + str(root / 'proc') in command
                assert command[command.index('chroot') + 1] == str(root)
                assert '/usr/bin/env' in command and '-i' in command
                assert not any('bind' in str(word) for word in command)
                plan = json.loads((root / 'simpleupdate-preflight/plan.json').read_text())
                assert plan['target'] == [99, 'future'] and plan['wm_sha'] == '1' * 40
                include = root / 'target-headers'; include.mkdir()
                (include / 'wlroots.h').write_text('struct target_api { int new_field; };\n')
                program = root / 'source.c'
                program.write_text('#include "wlroots.h"\nint main(void) { struct target_api api = {0}; '
                                   'return api.' + ('old_field' if outcome == 'compiler' else 'new_field') + '; }\n')
                local = root / 'work/wm-stage/usr/local'; (local / 'bin').mkdir(parents=True)
                result = subprocess.run(['cc', '-Werror', '-I', str(include), str(program),
                                         '-o', str(local / 'bin/simplewm')], capture_output=True, text=True)
                if result.returncode:
                    assert 'old_field' in result.stderr
                    raise RuntimeError(result.stderr)
                subprocess.run([str(local / 'bin/simplewm')], check=True)
                (local / 'share/simplewm').mkdir(parents=True)
                (local / 'share/simplewm/config').write_text('verified config')
                proof = {'target': [99, 'future'], 'wm_sha': '1' * 40, 'digest': update.payload_digest(local),
                         'wm_packages': ['libwlroots-8.42-dev=8.42.1-1'], 'suite_packages': ['suite-dev=1']}
                if outcome == 'forged-result':
                    proof['target'] = [13, 'trixie']
                if outcome == 'corrupt-payload':
                    (local / 'share/simplewm/config').write_text('altered after validation')
                (root / 'simpleupdate-preflight/result.json').write_text(json.dumps(proof))
            else:
                raise AssertionError(f'host mutation or unexpected command: {command}')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(update, 'run', side_effect=environment), \
             patch.object(update, 'bootstrap_tool', return_value='/fixture/mmdebstrap'), \
             patch.object(update.os, 'chown'), contextlib.redirect_stdout(io.StringIO()):
            action = lambda: update.target_preflight(argparse.Namespace(verify=False), (99, 'future'),
                {'SimpleWM': (source, '1' * 40)}, work, {}, None, os.getuid(), os.getgid())
            if outcome == 'success':
                local, proof = action()
                with patch.object(update, 'PENDING_RELEASE', base / 'state/release-upgrade.json'):
                    saved = update.persist_preflight(local, proof)
                    update.remember_release((99, 'future'), base / 'backup', saved)
                    restored, restored_proof = update.saved_preflight(update.pending_release())
                    assert restored_proof == proof
                    (restored / 'bin/simplewm').write_bytes(b'corrupt')
                    rejected(lambda: update.saved_preflight(update.pending_release()), 'incomplete or corrupt')
                    update.complete_release()
                    assert not saved.exists() and not update.PENDING_RELEASE.exists()
            else:
                messages = {'compiler': 'old_field', 'environment': 'creation failed',
                            'forged-result': 'does not match', 'corrupt-payload': 'integrity verification'}
                rejected(action, messages[outcome])
        assert not any(command[0] in ('apt-get', 'btrfs', 'mount', 'grub-install', 'update-grub') for command in trace)
    print('OK isolated bootstrap contract, real compiler API failure, successful build, result integrity and durable payload recovery')
