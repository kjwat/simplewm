#!/usr/bin/python3
"""Finalize updater trust and explicit package ownership in a disposable ISO root."""
import argparse
import importlib.util
import os
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE / 'updater'))
import transaction
spec = importlib.util.spec_from_file_location('seed_bootstrap', SOURCE / 'updater/launcher.py')
bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rootfs', type=Path)
    parser.add_argument('--payload', type=Path, action='append', required=True,
                        help='explicit Suite/WM staging tree ending in usr/local; repeat for both')
    args = parser.parse_args()
    root = args.rootfs.resolve()
    if root == Path('/') or not (root / 'etc/calamares/settings.conf').is_file():
        parser.error('expected a disposable extracted SimpleOS image, never the host root')
    if os.geteuid() != 0:
        parser.error('finalize the staged image with administrator privileges to set real root ownership')
    os.umask(0o022)
    prefix = root / 'usr/local'
    data = prefix / 'share/simpleupdate'
    metadata, name = bootstrap.manifest(data, data / 'release-key.pem')
    _, installed = bootstrap.verify_payload(prefix / 'libexec/simpleupdate/versions' / name,
                                             data / 'release-key.pem')
    if installed != name:
        parser.error('seed metadata differs from its version directory')
    owned = {}
    for payload in args.payload:
        if payload.resolve() == prefix:
            parser.error('supply explicit package stages, never the assembled /usr/local')
        for name, expected in transaction.inventory(payload).items():
            transaction.relative(name)
            if name == 'share/simpleupdate/owned.json':
                continue
            target = prefix / name
            for parent in (target.parent, *target.parent.parents):
                if parent == root:
                    break
                if parent.is_symlink():
                    parser.error('symlink in installed payload parent: ' + str(parent))
            if transaction.fingerprint(target) != expected:
                parser.error('assembled file differs from its package payload: ' + name)
            if name in owned and owned[name] != expected:
                parser.error('package payloads disagree about ' + name)
            owned[name] = expected
    for component in ('simplewm', 'simplesuite'):
        for name in ('install-manifest', 'source.bundle'):
            if f'share/{component}/{name}' not in owned:
                parser.error(f'missing explicit {component} provenance payload: {name}')
    if 'bin/simpleupdate' not in owned or 'share/simpleupdate/release-key.pem' not in owned:
        parser.error('the signed updater seed must be part of the explicit WM payload')
    directories = {root / 'usr', prefix, root / 'var', root / 'var/lib'}
    for name in owned:
        path = prefix / name
        os.chown(path, 0, 0, follow_symlinks=False)
        for parent in path.parents:
            if parent == root:
                break
            directories.add(parent)
    for directory in directories:
        if directory.is_symlink() or not directory.is_dir():
            parser.error('unsafe image directory: ' + str(directory))
        os.chown(directory, 0, 0); directory.chmod(0o755)
    record = data / 'owned.json'
    transaction.write_json(record, owned)
    os.chown(record, 0, 0)
    for relative in ('var/lib/simpleupdate', 'usr/local/.simpleupdate-ordinary', 'usr/local/.simpleupdate-previous'):
        path = root / relative
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            parser.error('image contains update/recovery state; preserve and remove it before release: ' + relative)
    print(f'Verified signed updater {metadata["version"]} and {len(owned)} explicit package paths')


if __name__ == '__main__':
    main()
