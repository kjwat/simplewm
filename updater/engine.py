#!/usr/bin/python3
"""Versioned entry point. Bootstrap protocol 1; Debian migration stays in legacy.py."""
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys

# Isolated Python ignores PYTHONDONTWRITEBYTECODE from the launcher environment.
# Diagnostics and probes must not populate caches in an installed version.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import ordinary
import transaction


def load_legacy():
    spec = importlib.util.spec_from_file_location('simpleupdate_legacy', ROOT / 'legacy.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    metadata = json.loads((ROOT / 'release.json').read_text())
    version = metadata['version']
    legacy = load_legacy()
    if sys.argv[1:] == ['--bootstrap-probe']:
        if not callable(ordinary.run) or not callable(transaction.Transaction.recover):
            raise RuntimeError('incomplete updater implementation')
        print(json.dumps({'protocol': 1, 'version': version}))
        return
    if sys.argv[1:2] == ['--build-plan']:
        if os.geteuid() == 0:
            raise RuntimeError('source builds must run without root privileges')
        plan = json.loads(Path(sys.argv[2]).read_text())
        function = legacy.build_and_test if plan['component'] == 'SimpleSuite' else legacy.build_and_test_wm
        function(Path(plan['source']), Path(plan['stage']), plan['sha'], plan['env'], None, plan['verify'])
        if plan['component'] == 'SimpleWM':
            ordinary.healthcheck(Path(plan['stage']) / 'usr/local/bin/simplewm',
                                 Path(plan['source']) / 'config', Path(plan['stage']), plan['env'], None)
        return
    if sys.argv[1:2] == ['--bootstrap-ready-fd']:
        descriptor = int(sys.argv[2])
        del sys.argv[1:3]
        with socket.socket(fileno=descriptor) as channel:
            channel.sendall(b'READY 1\n')
            # EOF means the supervisor died before durable activation. Never
            # start APT or source installation without its acknowledgement.
            if channel.recv(1) != b'G':
                raise RuntimeError('updater activation was not acknowledged')
    if sys.argv[1:] == ['--status']:
        legacy.say(ordinary.STATE.read_text().strip() if ordinary.STATE.exists() else 'No ordinary update has started')
        return
    if sys.argv[1:] in (['--recover-sources'], ['--rollback-sources']):
        if os.geteuid() != 0:
            raise RuntimeError('source recovery requires administrator privileges')
        if legacy.pending_release():
            raise RuntimeError('complete the pending Debian migration before ordinary source recovery')
        with open('/run/lock/simpleupdate.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            ordinary.recover(legacy)
            if sys.argv[1:] == ['--rollback-sources']:
                transaction.Transaction(legacy.PREFIX).rollback()
                legacy.say('Previous Suite/WM files restored; Debian packages were not rolled back')
        return
    def interrupted(signum, frame):
        raise KeyboardInterrupt('update interrupted by signal ' + str(signum))
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    legacy.ORDINARY_UPDATE = lambda update, args, log: ordinary.run(update, args, log, version)
    legacy.main()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        sys.exit('simpleupdate: ' + str(error))
