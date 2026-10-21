"""Durable ordinary-source installation; APT is deliberately outside rollback."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

RESERVE = 64 * 1024 * 1024


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, data):
    fd, name = tempfile.mkstemp(prefix='.simpleupdate-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, sort_keys=True)
            out.write('\n'); out.flush(); os.fchmod(out.fileno(), 0o644); os.fsync(out.fileno())
        os.replace(name, path); sync(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def relative(value):
    path = Path(value)
    if (not value or path.is_absolute() or '..' in path.parts
            or str(path) != value or path.parts[0] not in ('bin', 'sbin', 'share', 'libexec')):
        raise RuntimeError('invalid installation path: ' + value)
    return path


def parents(root, path):
    for parent in [root, *(root / path).parents][::-1]:
        if parent != root and not parent.is_relative_to(root):
            continue
        if parent.is_symlink():
            raise RuntimeError('installation parent is a symbolic link: ' + str(parent))
        if not parent.exists():
            parent.mkdir(); sync(parent.parent)
        if not parent.is_dir():
            raise RuntimeError('installation parent is not a directory: ' + str(parent))
        info = parent.stat()
        if os.geteuid() == 0 and (info.st_uid != 0 or info.st_mode & 0o022):
            raise RuntimeError('installation directory is writable by a non-administrator: ' + str(parent))


def fingerprint(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return {'link': os.readlink(path)}
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError('refusing to replace a directory or special file: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise RuntimeError('installation file changed type: ' + str(path))
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'sha256': digest, 'mode': stat.S_IMODE(info.st_mode)}


def copy_file(source, destination):
    """Copy without following the source; backups are never consumed by recovery."""
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    else:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as src, destination.open('xb') as dst:
            info = os.fstat(src.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError('unsupported source file: ' + str(source))
            shutil.copyfileobj(src, dst)
            os.fchmod(dst.fileno(), stat.S_IMODE(info.st_mode) & 0o777)
            dst.flush(); os.fsync(dst.fileno())
    sync(destination.parent)


def freeze(source, destination):
    """Capture unprivileged staging using directory FDs, never traversing links."""
    destination.mkdir(mode=0o700)
    def walk(source_fd, target):
        for name in sorted(os.listdir(source_fd)):
            info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
            output = target / name
            if stat.S_ISDIR(info.st_mode):
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=source_fd)
                try:
                    output.mkdir(mode=0o755); walk(fd, output)
                finally:
                    os.close(fd)
            elif stat.S_ISLNK(info.st_mode):
                link = os.readlink(name, dir_fd=source_fd)
                if os.path.isabs(link):
                    raise RuntimeError('absolute staging link: ' + name)
                output.symlink_to(link)
            elif stat.S_ISREG(info.st_mode):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source_fd)
                with os.fdopen(fd, 'rb') as src, output.open('xb') as dst:
                    if not stat.S_ISREG(os.fstat(src.fileno()).st_mode):
                        raise RuntimeError('staged file changed type')
                    shutil.copyfileobj(src, dst)
                    os.fchmod(dst.fileno(), 0o755 if info.st_mode & 0o111 else 0o644)
                    dst.flush(); os.fsync(dst.fileno())
            else:
                raise RuntimeError('special file in staged payload: ' + name)
        sync(target)
    fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        walk(fd, destination)
    finally:
        os.close(fd)
    for path in destination.rglob('*'):
        relative(str(path.relative_to(destination)))
        if path.is_symlink() and not path.resolve().is_relative_to(destination.resolve()):
            raise RuntimeError('symbolic link escapes staged payload: ' + str(path))
    destination.chmod(0o755); sync(destination.parent)


def inventory(root):
    return {str(p.relative_to(root)): fingerprint(p) for p in sorted(root.rglob('*'))
            if p.is_symlink() or p.is_file()}


class Transaction:
    def __init__(self, prefix):
        self.prefix = prefix
        self.directory = prefix / '.simpleupdate-ordinary'
        self.retained = prefix / '.simpleupdate-previous'
        self.ownership = prefix / 'share/simpleupdate/owned.json'

    def journal(self, state):
        write_json(self.directory / 'journal.json', state)

    def read(self):
        state = json.loads((self.directory / 'journal.json').read_text())
        if (not isinstance(state, dict) or state.get('format') != 1
                or state.get('status') not in ('staged', 'installing', 'committed', 'recovering', 'recovered')
                or not isinstance(state.get('files'), list)):
            raise RuntimeError('invalid source recovery journal; manual inspection required')
        names = set()
        for item in state['files']:
            relative(item['path'])
            if item['path'] in names:
                raise RuntimeError('duplicate source recovery path')
            names.add(item['path'])
            if set(item) != {'path', 'before', 'after'}:
                raise RuntimeError('invalid source recovery entry')
        return state

    def restore(self, state):
        state['status'] = 'recovering'; self.journal(state)
        for item in reversed(state['files']):
            path = relative(item['path'])
            parents(self.prefix, path)
            target = self.prefix / path
            actual = fingerprint(target)
            if actual == item['before']:
                continue  # Recovery may itself have lost power after this file.
            if actual != item['after']:
                raise RuntimeError(f'{target} changed outside the transaction; manual recovery required')
            if item['before'] is None:
                target.unlink(); sync(target.parent)
            else:
                backup = self.directory / 'old' / path
                if fingerprint(backup) != item['before']:
                    raise RuntimeError('source recovery backup is damaged: ' + str(backup))
                fd, name = tempfile.mkstemp(prefix='.simpleupdate-restore-', dir=target.parent)
                os.close(fd); os.unlink(name)
                try:
                    copy_file(backup, Path(name))
                    os.replace(name, target); sync(target.parent)
                finally:
                    Path(name).unlink(missing_ok=True)
        state['status'] = 'recovered'; self.journal(state)

    def recover(self):
        if not self.directory.exists():
            return False
        if self.directory.is_symlink():
            raise RuntimeError('unsafe source transaction directory')
        if not (self.directory / 'journal.json').exists():
            # No installation starts before the complete journal is durable.
            shutil.rmtree(self.directory); sync(self.prefix)
            return True
        state = self.read()
        if state['status'] == 'committed':
            self.retain()
            return False
        if state['status'] not in ('staged', 'recovered'):
            self.restore(state)
        shutil.rmtree(self.directory); sync(self.prefix)
        return True

    def retain(self):
        if self.retained.exists():
            shutil.rmtree(self.retained); sync(self.prefix)
        os.rename(self.directory, self.retained); sync(self.prefix)

    def rollback(self):
        self.recover()
        if not self.retained.is_dir() or self.retained.is_symlink():
            raise RuntimeError('no previous source installation is available')
        os.rename(self.retained, self.directory); sync(self.prefix)
        state = self.read()
        self.restore(state)
        self.recover()

    def install(self, stages, verify, say=print, progress=lambda *args: None, *, managed_paths=(), retired_paths=()):
        self.recover()
        if not self.ownership.is_file() or self.ownership.is_symlink():
            raise RuntimeError('packaged-file inventory is missing; ordinary source installation is blocked')
        owned = json.loads(self.ownership.read_text())
        if not isinstance(owned, dict):
            raise RuntimeError('invalid packaged-file inventory')
        # The caller supplies the actual paths from authenticated component
        # payloads, after provenance and staging checks. The old inventory is
        # installation history, not a permanent limit on a growing suite.
        managed_paths = frozenset(str(relative(path)) for path in managed_paths)
        self.directory.mkdir(mode=0o700); sync(self.prefix)
        incoming = self.directory / 'new'; incoming.mkdir()
        old = self.directory / 'old'; old.mkdir()
        state = {'format': 1, 'status': 'staged', 'files': []}
        try:
            for index, stage in enumerate(stages):
                captured = self.directory / f'captured-{index}'
                freeze(stage, captured)
                for text, after in inventory(captured).items():
                    path = relative(text)
                    target = self.prefix / path
                    parents(self.prefix, path)
                    before = fingerprint(target)
                    if before is not None and before != owned.get(text) and before != after:
                        component_data = text.startswith(('share/simplewm/', 'share/simplesuite/'))
                        provenance = component_data and path.parts[2] in (
                            'install-manifest', 'install-source', 'source.bundle', 'source')
                        if component_data and not provenance:
                            say('Preserving locally modified file: ' + str(target))
                            continue
                        if text not in owned:
                            info = target.lstat()
                            if (text not in managed_paths or info.st_uid != os.geteuid()
                                    or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022)):
                                raise RuntimeError('unmanaged program conflicts with update: ' + str(target))
                            say('Including existing component file (backup retained): ' + str(target))
                        else:
                            # Ownership covers the path across local rebuilds;
                            # recovery restores the exact build being replaced.
                            say('Replacing locally rebuilt program (backup retained): ' + str(target))
                    if (incoming / path).exists() or (incoming / path).is_symlink():
                        raise RuntimeError('components have overlapping install paths: ' + text)
                    parents(incoming, path); copy_file(captured / path, incoming / path)
                    owned[text] = after
                    if before != after:
                        state['files'].append({'path': text, 'before': before, 'after': after})
            # A verified full component payload can explicitly retire renamed
            # files. Only exact previously owned bytes qualify; personal or
            # locally edited files remain untouched. Retirements use the same
            # durable backup/journal as replacements, including rollback.
            for text in sorted(set(retired_paths)):
                path = relative(text)
                if text in managed_paths or (incoming / path).exists():
                    raise RuntimeError('retired path is also supplied by the update: ' + text)
                if text not in owned:
                    continue
                parents(self.prefix, path)
                before = fingerprint(self.prefix / path)
                if before is not None and before != owned[text]:
                    say('Preserving locally modified retired file: ' + str(self.prefix / path))
                    continue
                owned.pop(text)
                if before is not None:
                    state['files'].append({'path': text, 'before': before, 'after': None})
            # Ownership and component provenance are part of the same rollback.
            path = self.ownership.relative_to(self.prefix)
            parents(incoming, path); write_json(incoming / path, owned)
            state['files'].append({'path': str(path), 'before': fingerprint(self.ownership),
                                   'after': fingerprint(incoming / path)})
            size = sum((incoming / item['path']).lstat().st_size for item in state['files'] if item['after'] is not None)
            size += sum((self.prefix / item['path']).lstat().st_size for item in state['files'] if item['before'])
            if shutil.disk_usage(self.prefix).free < size + RESERVE:
                raise RuntimeError('not enough disk space for installation and recovery copies')
            count = len(state['files'])
            for index, item in enumerate(state['files'], 1):
                path = relative(item['path'])
                if item['before'] is not None:
                    parents(old, path); copy_file(self.prefix / path, old / path)
                    if fingerprint(old / path) != item['before']:
                        raise RuntimeError('installed file changed while preparing its backup')
                progress('Backing up', index, count)
            # All payloads, backups and directory entries precede installing.
            for directory in sorted([incoming, old, *incoming.rglob('*'), *old.rglob('*')], reverse=True):
                if directory.is_dir() and not directory.is_symlink():
                    sync(directory)
            state['files'].sort(key=lambda item: (item['path'].endswith('/install-manifest'), item['path']))
            self.journal(state)
            state['status'] = 'installing'; self.journal(state)
            for index, item in enumerate(state['files'], 1):
                path = relative(item['path'])
                target = self.prefix / path
                if fingerprint(target) != item['before']:
                    raise RuntimeError('installed file changed during installation: ' + str(target))
                if item['after'] is None:
                    target.unlink()
                else:
                    os.replace(incoming / path, target)
                    sync((incoming / path).parent)
                sync(target.parent)
                progress('Installing', index, count)
            for item in state['files']:
                if fingerprint(self.prefix / item['path']) != item['after']:
                    raise RuntimeError('installed file failed verification: ' + item['path'])
            verify()
            state['status'] = 'committed'; self.journal(state)
        except BaseException:
            self.recover()
            raise
        self.retain()
        say('Previous programs retained in ' + str(self.retained / 'old'))
