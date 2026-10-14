#!/usr/bin/python3
"""ISO assembly: register only files supplied by explicit package staging trees."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from transaction import fingerprint, inventory, relative, write_json


def main():
    os.umask(0o022)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True, type=Path, help='assembled rootfs/usr/local')
    parser.add_argument('--payload', required=True, type=Path, action='append', help='verified package stage/usr/local; repeat for Suite and WM')
    args = parser.parse_args()
    record = args.prefix / 'share/simpleupdate/owned.json'
    owned = json.loads(record.read_text()) if record.exists() else {}
    for payload in args.payload:
        if payload.resolve() == args.prefix.resolve():
            parser.error('inventory explicit package staging trees, never all of an existing /usr/local')
        for name, expected in inventory(payload).items():
            relative(name)
            if name == 'share/simpleupdate/owned.json':
                continue
            if fingerprint(args.prefix / name) != expected:
                parser.error('assembled image differs from its packaged payload: ' + name)
            owned[name] = expected
    record.parent.mkdir(parents=True, exist_ok=True)
    write_json(record, owned)
    print('Registered', len(owned), 'packaged paths; unrelated installed files were not adopted')


if __name__ == '__main__':
    main()
