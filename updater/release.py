#!/usr/bin/python3
"""Maintainer: sign a committed updater payload. Never installs or publishes it."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'updater/launcher.py')
bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key', required=True, type=Path, help='private signing key outside the repository')
    parser.add_argument('--version', required=True, type=int, help='strictly increasing integer release number')
    parser.add_argument('--revision', default='HEAD', help='committed implementation revision')
    parser.add_argument('--output', type=Path, default=ROOT / 'updater')
    args = parser.parse_args()
    if args.key.resolve().is_relative_to(ROOT) or args.key.stat().st_mode & 0o077:
        parser.error('keep the private key outside the repository, readable only by its owner')
    public = subprocess.check_output(['/usr/bin/openssl', 'pkey', '-in', str(args.key),
                                      '-pubout', '-outform', 'DER'])
    pinned = subprocess.check_output(['/usr/bin/openssl', 'pkey', '-pubin',
                                      '-in', str(ROOT / 'updater/release-key.pem'), '-outform', 'DER'])
    if public != pinned:
        parser.error('private signing key does not match the pinned release public key')
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', args.revision + '^{commit}'], text=True).strip()
    payload = {}
    for name, path in bootstrap.FILES.items():
        data = subprocess.check_output(['git', '-C', str(ROOT), 'show', revision + ':' + path])
        compile(data, name, 'exec')
        payload[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    if args.version < 1:
        parser.error('release numbers start at 1')
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = args.output / 'release.json'
    if metadata.exists() and args.version <= json.loads(metadata.read_text())['version']:
        parser.error('use a strictly higher version than the existing release metadata')
    metadata.write_text(json.dumps({'format': 1, 'protocol': 1, 'version': args.version,
                                    'revision': revision, 'files': payload}, sort_keys=True, indent=2) + '\n')
    subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(args.key),
                    '-out', str(args.output / 'release.sig'), str(metadata)], check=True)
    print('Signed updater', args.version, 'from', revision, 'in', args.output)


if __name__ == '__main__':
    main()
