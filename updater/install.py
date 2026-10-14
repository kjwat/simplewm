#!/usr/bin/python3
"""Install the versioned bootstrap seed through the normal SimpleWM DESTDIR payload."""
import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'updater/launcher.py')
bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)


def main():
    os.umask(0o022)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destdir', default='')
    parser.add_argument('--prefix', default='/usr/local')
    args = parser.parse_args()
    prefix = Path(args.destdir or '/') / args.prefix.lstrip('/')
    metadata, name = bootstrap.manifest(ROOT / 'updater')
    # Verify all seed bytes before changing any installation path. This also
    # prevents a mismatched working tree from silently entering a release ISO.
    with tempfile.TemporaryDirectory(prefix='simpleupdate-seed-') as temp:
        seed = Path(temp)
        shutil.copyfile(ROOT / 'updater/release.json', seed / 'release.json')
        for file, source in bootstrap.FILES.items():
            shutil.copyfile(ROOT / source, seed / file)
        bootstrap.verify_payload(seed)
        payload = prefix / 'libexec/simpleupdate/versions' / name
        payload.mkdir(parents=True, exist_ok=True)
        for source in seed.iterdir():
            target = payload / source.name
            shutil.copyfile(source, target)
            target.chmod(0o755 if target.name == 'simpleupdate-target' else 0o644)
        data = prefix / 'share/simpleupdate'; data.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'updater/release.json', data / 'release.json')
        (data / 'release.json').chmod(0o644)
        launcher = prefix / 'bin/simpleupdate'; launcher.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'updater/launcher.py', launcher); launcher.chmod(0o755)


if __name__ == '__main__':
    main()
