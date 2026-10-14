#!/usr/bin/python3
"""Prepare committed test sources and exercise the actual installed entry point."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'updater/launcher.py')
boot = importlib.util.module_from_spec(spec); spec.loader.exec_module(boot)

def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True, text=True, **kwargs)

with tempfile.TemporaryDirectory(prefix='seed-check-') as temp:
    root = Path(temp); source = root / 'source'; source.mkdir()
    for name in {*boot.FILES.values(), 'updater/launcher.py', 'updater/install.py', 'updater/release.py'}:
        target = source / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    run('git', 'init', '--quiet', source)
    run('git', '-C', source, 'add', '.')
    run('git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', '-C', source,
        'commit', '--quiet', '-m', 'verified seed fixture')
    run('python3', source / 'updater/release.py', '--version', '1')
    stage = root / 'stage'
    run('python3', source / 'updater/install.py', '--destdir', stage, preexec_fn=lambda: os.umask(0o002))
    prefix = stage / 'usr/local'
    assert (prefix / 'share/simpleupdate').stat().st_mode & 0o777 == 0o755
    assert (prefix / 'libexec/simpleupdate/versions').stat().st_mode & 0o777 == 0o755
    metadata, name = boot.manifest(prefix / 'share/simpleupdate')
    payload = prefix / 'libexec/simpleupdate/versions' / name
    boot.verify_payload(payload)
    assert not list(stage.rglob('release.sig')) and not list(stage.rglob('release-key.pem'))
    engine = payload / 'engine.py'
    assert json.loads(run('python3', '-I', engine, '--bootstrap-probe').stdout) == {'protocol': 1, 'version': 1}
    help_text = run('python3', '-I', engine, '--help').stdout
    assert '--release-upgrade' in help_text and '--rollback-sources' in help_text
    assert not list(payload.rglob('*.pyc')), 'installed diagnostics created bytecode caches'
    parent, child = socket.socketpair()
    process = subprocess.Popen(['python3', '-I', str(engine), '--bootstrap-ready-fd', str(child.fileno()), '--help'],
                               pass_fds=(child.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child.close(); parent.settimeout(5)
    assert parent.recv(64) == b'READY 1\n'
    assert process.poll() is None
    parent.sendall(b'G'); parent.close()
    out, err = process.communicate(timeout=5)
    assert process.returncode == 0 and '--release-upgrade' in out, err
    parent, child = socket.socketpair()
    process = subprocess.Popen(['python3', '-I', str(engine), '--bootstrap-ready-fd', str(child.fileno()), '--help'],
                               pass_fds=(child.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child.close(); parent.settimeout(5)
    assert parent.recv(64) == b'READY 1\n'; parent.close()
    out, err = process.communicate(timeout=5)
    assert process.returncode != 0 and 'not acknowledged' in err and '--release-upgrade' not in out
    print('OK versioned seed installer, real module imports, preserved migration CLI, activation gate and supervisor-loss containment')
    before = hashlib.sha256((prefix / 'bin/simpleupdate').read_bytes()).hexdigest()
    (source / 'updater/ordinary.py').write_text('mismatched replacement')
    failed = subprocess.run(['python3', str(source / 'updater/install.py'), '--destdir', str(stage)], capture_output=True)
    assert failed.returncode and hashlib.sha256((prefix / 'bin/simpleupdate').read_bytes()).hexdigest() == before
    print('OK installer refuses working-tree code that differs from release metadata before touching its installed seed')
