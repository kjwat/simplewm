#!/usr/bin/python3
"""Maintainer: describe a committed updater payload. Never installs or publishes it."""
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
    parser.add_argument('--version', required=True, type=int, help='strictly increasing integer release number')
    parser.add_argument('--revision', default='HEAD', help='committed implementation revision')
    parser.add_argument('--output', type=Path, default=ROOT / 'updater')
    args = parser.parse_args()
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
    print('Prepared updater', args.version, 'from', revision, 'in', args.output)


if __name__ == '__main__':
    main()
