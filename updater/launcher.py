#!/usr/bin/python3 -I
"""Stable SimpleUpdate bootstrap, protocol 1. No component installation here."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import urllib.request

PROTOCOL = 1
BASE = 'https://raw.githubusercontent.com/kjwat/simplewm/'
PREFIX = Path('/usr/local')
DATA = PREFIX / 'share/simpleupdate'
VERSIONS = PREFIX / 'libexec/simpleupdate/versions'
STATE = Path('/var/lib/simpleupdate/updater.json')
LOCK = Path('/run/simpleupdate-bootstrap.lock')
MIGRATION = Path('/var/lib/simpleupdate/release-upgrade.json')
FILES = {'engine.py': 'updater/engine.py', 'legacy.py': 'scripts/simpleupdate',
         'simpleupdate-target': 'scripts/simpleupdate-target',
         'ordinary.py': 'updater/ordinary.py', 'transaction.py': 'updater/transaction.py'}
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8',
       'PYTHONDONTWRITEBYTECODE': '1'}


def say(message):
    print('simpleupdate: ' + message, flush=True)


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path, create=True):
    # Check every existing parent, including ownership, before creating state.
    for parent in reversed([path, *path.parents][:-1]):
        if not parent.exists():
            if not create:
                raise RuntimeError('missing updater directory: ' + str(parent))
            parent.mkdir(mode=0o755); sync(parent.parent)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError(f'unsafe updater directory: {parent}')


def trusted_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError('unsafe updater file: ' + str(path))


def save(path, value):
    fd, name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out, sort_keys=True)
            out.write('\n'); out.flush(); os.fchmod(out.fileno(), 0o644); os.fsync(out.fileno())
        os.replace(name, path)
        sync(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def read_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate metadata key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def manifest(directory):
    raw = (directory / 'release.json').read_bytes()
    if len(raw) > 16384:
        raise RuntimeError('updater metadata is too large')
    data = read_json(raw)
    if (not isinstance(data, dict) or set(data) != {'format', 'version', 'protocol', 'revision', 'files'}
            or data['format'] != 1 or type(data['version']) is not int or data['version'] < 1
            or data['protocol'] != PROTOCOL
            or not isinstance(data['revision'], str) or not re.fullmatch('[0-9a-f]{40}', data['revision'])
            or not isinstance(data['files'], dict) or set(data['files']) != set(FILES)):
        raise RuntimeError('unsupported updater metadata or bootstrap protocol')
    for item in data['files'].values():
        if (not isinstance(item, dict) or set(item) != {'size', 'sha256'}
                or type(item['size']) is not int or not 1 <= item['size'] <= 2 * 1024 * 1024
                or not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256'])):
            raise RuntimeError('invalid updater file metadata')
    return data, f'{data["version"]}-{hashlib.sha256(raw).hexdigest()}'


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[1-9][0-9]*-[0-9a-f]{64}', value):
        raise RuntimeError('invalid updater version record; inspect /var/lib/simpleupdate/updater.json')
    return value


def verify_payload(directory):
    metadata, name = manifest(directory)
    for file, expected in metadata['files'].items():
        path = directory / file
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_size != expected['size']
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected['sha256']):
            raise RuntimeError(f'updater payload verification failed: {file}')
    return metadata, name


def installed_payload(name):
    directory = VERSIONS / identifier(name)
    private_directory(directory, create=False)
    for file in ('release.json', *FILES):
        trusted_file(directory / file)
    metadata, actual = verify_payload(directory)
    if actual != name:
        raise RuntimeError('updater version directory does not match its metadata')
    return metadata, actual


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('updater download redirected away from its trusted origin')


def fetch_child(relative, limit):
    if os.geteuid() == 0:
        raise RuntimeError('updater downloads must run without root privileges')
    if not re.fullmatch(r'(main/updater/release\.json|[0-9a-f]{40}/(updater/[a-z]+\.py|scripts/simpleupdate(-target)?))', relative):
        raise RuntimeError('invalid updater download path')
    request = urllib.request.Request(BASE + relative, headers={'User-Agent': 'SimpleOS-simpleupdate/1'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=25) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError('updater download exceeds its declared size')
    sys.stdout.buffer.write(data)


def download(relative, limit):
    nobody = pwd.getpwnam('nobody')
    result = subprocess.run(['/usr/bin/python3', '-I', str(Path(__file__).resolve()),
                             '--bootstrap-fetch', relative, str(limit)],
                            user=nobody.pw_uid, group=nobody.pw_gid, extra_groups=[],
                            env=ENV, capture_output=True, timeout=40)
    if result.returncode:
        raise RuntimeError('cannot download updater; the working installation is unchanged. '
                           'Check the connection and retry simpleupdate')
    if len(result.stdout) > limit:
        raise RuntimeError('updater download is too large')
    return result.stdout


def stage(metadata_dir, metadata, name):
    final = VERSIONS / name
    if final.exists():
        installed_payload(name)
        return final
    required = sum(item['size'] for item in metadata['files'].values()) + 16 * 1024 * 1024
    if shutil.disk_usage(VERSIONS).free < required:
        raise RuntimeError('not enough disk space to stage the updater; free space and retry')
    with tempfile.TemporaryDirectory(prefix='.staging-', dir=VERSIONS) as temp:
        incoming = Path(temp) / 'payload'; incoming.mkdir(mode=0o755)
        shutil.copyfile(metadata_dir / 'release.json', incoming / 'release.json')
        for file, source in FILES.items():
            (incoming / file).write_bytes(download(metadata['revision'] + '/' + source,
                                                  metadata['files'][file]['size']))
        verify_payload(incoming)
        for path in incoming.iterdir():
            path.chmod(0o755 if path.name == 'simpleupdate-target' else 0o644)
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
        sync(incoming)
        os.rename(incoming, final)
        sync(VERSIONS)
    return final


def probe(directory, version):
    nobody = pwd.getpwnam('nobody')
    result = subprocess.run(['/usr/bin/python3', '-I', str(directory / 'engine.py'), '--bootstrap-probe'],
                            capture_output=True, env=ENV, timeout=20,
                            user=nobody.pw_uid, group=nobody.pw_gid, extra_groups=[])
    if result.returncode or read_json(result.stdout) != {'protocol': PROTOCOL, 'version': version}:
        raise RuntimeError('replacement updater failed its initialization check')


def invoke(directory, arguments, lock, state, initializing):
    parent, child = socket.socketpair()
    process = None
    previous_handlers = {}
    interrupted = []
    try:
        process = subprocess.Popen(['/usr/bin/python3', '-I', str(directory / 'engine.py'),
                                    '--bootstrap-ready-fd', str(child.fileno()), *arguments],
                                   env=ENV | {k: v for k, v in os.environ.items() if k in ('SUDO_UID', 'SUDO_TTY')},
                                   pass_fds=(child.fileno(), lock.fileno()), start_new_session=True)
        child.close()
        def forward(signum, frame):
            interrupted.append(signum)
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous_handlers[signum] = signal.signal(signum, forward)
        ready, _, _ = select.select([parent], [], [], 20)
        if interrupted:
            process.wait()
            raise KeyboardInterrupt('update cancelled')
        if not ready or parent.recv(64) != b'READY 1\n':
            return None
        if initializing:
            state['pending'] = False
            save(STATE, state)
            say('Updater ready')
        parent.sendall(b'G')
        return process.wait()
    finally:
        parent.close(); child.close()
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main():
    args = sys.argv[1:]
    if args[:1] == ['--bootstrap-fetch']:
        fetch_child(args[1], min(int(args[2]), 2 * 1024 * 1024))
        return 0
    diagnostics = any(arg in args for arg in ('--help', '-h', '--dry-run', '--status'))
    if diagnostics:
        private_directory(DATA, create=False)
        trusted_file(DATA / 'release.json')
        _, seed_name = manifest(DATA)
        state = read_json(STATE.read_bytes()) if STATE.exists() else {'active': seed_name}
        selected = None
        for name in (state.get('active'), state.get('previous'), seed_name):
            if name is None:
                continue
            candidate = VERSIONS / identifier(name)
            try:
                _, actual = installed_payload(name)
                if actual != name:
                    raise RuntimeError('updater version directory mismatch')
            except (OSError, ValueError, RuntimeError):
                continue
            selected = candidate
            break
        if selected is None:
            raise RuntimeError('no verified updater is available for diagnostics')
        os.execv('/usr/bin/python3', ['python3', '-I', str(selected / 'engine.py'), *args])
    if os.geteuid() != 0:
        os.execv('/usr/bin/sudo', ['sudo', '--', str(Path(__file__).resolve()), *args])
    os.umask(0o022)
    for directory in (DATA, VERSIONS, STATE.parent, LOCK.parent):
        private_directory(directory)
    trusted_file(DATA / 'release.json')
    seed, seed_name = manifest(DATA)
    lock_fd = os.open(LOCK, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
    with os.fdopen(lock_fd, 'a') as lock:
        trusted_file(LOCK)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('another update is already running')
        if STATE.exists():
            trusted_file(STATE)
            state = read_json(STATE.read_bytes())
            if (not isinstance(state, dict) or set(state) != {'active', 'previous', 'pending', 'highest', 'rejected'}
                    or type(state['pending']) is not bool or type(state['highest']) is not int
                    or state['highest'] < seed['version']
                    or not isinstance(state['rejected'], list)):
                raise RuntimeError('invalid updater state; inspect ' + str(STATE))
            identifier(state['active'])
            if state['previous'] is not None:
                identifier(state['previous'])
            for rejected in state['rejected']:
                identifier(rejected)
        else:
            state = dict(active=seed_name, previous=None, pending=False,
                         highest=seed['version'], rejected=[])
        def restore(reason):
            fallback = state['previous'] or (seed_name if state['active'] != seed_name else None)
            if not fallback:
                raise RuntimeError(reason + '; no previous updater exists. Recovery media may be needed')
            installed_payload(fallback)
            state['rejected'] = list(dict.fromkeys([*state['rejected'], state['active']]))
            state.update(active=fallback, previous=None, pending=False)
            save(STATE, state)
            say(reason + '; restored the previous updater')
        if state['pending']:
            restore('Updater activation was interrupted')
        try:
            installed, _ = installed_payload(state['active'])
        except (OSError, ValueError, RuntimeError):
            restore('The active updater is damaged')
            installed, _ = installed_payload(state['active'])
        previous_requested = '--previous-updater' in args
        if previous_requested:
            args.remove('--previous-updater')
            restore('Previous updater requested')
            installed, _ = installed_payload(state['active'])
        # Keep the installed Debian migration authority and its recovery path.
        migration = '--release-upgrade' in args or MIGRATION.exists()
        rollback = '--rollback-sources' in args
        if rollback and args != ['--rollback-sources']:
            raise RuntimeError('--rollback-sources must be used alone')
        if not migration:
            subprocess.run(['/usr/bin/python3', '-I',
                            str(VERSIONS / state['active'] / 'engine.py'), '--recover-sources'],
                           env=ENV, pass_fds=(lock.fileno(),), check=True)
        # Diagnostics must be available offline; ordinary requests fail closed
        # when the trusted update service is unavailable.
        if not migration and not rollback and not previous_requested:
            say('Checking for updater improvements')
            with tempfile.TemporaryDirectory(prefix='.metadata-', dir=STATE.parent) as temp:
                metadata_dir = Path(temp)
                (metadata_dir / 'release.json').write_bytes(download('main/updater/release.json', 16384))
                metadata, name = manifest(metadata_dir)
                if metadata['version'] < state['highest']:
                    raise RuntimeError('updater metadata is older than the newest verified release')
                # A release number identifies exactly one verified payload,
                # including a previously rejected candidate.
                known = [state['active'], state['previous'], *state['rejected']]
                if any(value and int(value.split('-', 1)[0]) == metadata['version'] and value != name
                       for value in known):
                    raise RuntimeError('the published updater reused a version number with different contents')
                if metadata['version'] == installed['version'] and name != state['active']:
                    raise RuntimeError('the published updater reused a version number with different contents')
                state['highest'] = max(state['highest'], metadata['version'])
                save(STATE, state)
                if '--check' in args:
                    say('Updater version ' + str(metadata['version']) + ' is available' if name != state['active'] else 'Updater is current')
                elif name != state['active'] and name not in state['rejected']:
                    say(f'Installing updater version {metadata["version"]}')
                    candidate = stage(metadata_dir, metadata, name)
                    try:
                        probe(candidate, metadata['version'])
                    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                        state['rejected'].append(name); save(STATE, state)
                        say('Replacement updater could not initialize; keeping the working updater')
                    else:
                        state.update(previous=state['active'], active=name, pending=True)
                        save(STATE, state)
                elif name in state['rejected']:
                    say('Keeping the working updater; this replacement previously failed initialization')
        result = invoke(VERSIONS / state['active'], args, lock, state, state['pending'])
        if result is None:
            restore('Replacement updater failed to initialize')
            result = invoke(VERSIONS / state['active'], args, lock, state, False)
            if result is None:
                raise RuntimeError('the previous updater also failed to initialize; recovery media may be needed')
        return result


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        sys.exit('simpleupdate: ' + str(error))
