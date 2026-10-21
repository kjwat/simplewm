#!/usr/bin/python3
"""Upgrade an ISO-era terminal reader with the real full Suite stage; roll back."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'updater'))
import transaction as tx
parser=argparse.ArgumentParser()
parser.add_argument('--stage',type=Path)
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='update-readers-') as temporary:
    base=Path(temporary);prefix=base/'local';stage=base/'stage'
    (prefix/'bin').mkdir(parents=True);(prefix/'share/applications').mkdir(parents=True)
    for name in ('simplepdf','simplepdf-mobi','simpleread','simpleread-mobi'):
        p=prefix/'bin'/name;p.write_text('ISO terminal '+name);p.chmod(0o755)
    (prefix/'share/applications/simplepdf.desktop').write_text('ISO terminal launcher')
    (prefix/'share/applications/simpleread.desktop').write_text('previous terminal launcher')
    (prefix/'share/simpleupdate').mkdir()
    record=prefix/'share/simpleupdate/owned.json'
    tx.write_json(record,tx.inventory(prefix));original=record.read_bytes()
    (prefix/'bin/personal-tool').write_text('keep')
    if args.stage:
        shutil.copytree(args.stage,stage)
    else:
        (stage/'bin').mkdir(parents=True)
        for name in ('simplepdf','simplebook','simplebook-mobi','simplefuture-reader'):
            p=stage/'bin'/name;p.write_text('new '+name);p.chmod(0o755)
    managed=tx.inventory(stage)
    retired=('bin/simplepdf-mobi','bin/simpleread','bin/simpleread-mobi',
             'share/applications/simplepdf.desktop','share/applications/simpleread.desktop')
    if args.stage:
        fields=dict(line.split('=',1) for line in
                    (stage/'share/simplesuite/install-manifest').read_text().splitlines())
        assert set(retired) <= set(fields['retired_paths'].split())
    transaction=tx.Transaction(prefix)
    def verify():
        for name in retired:
            assert not (prefix/name).exists(),name
        for name in ('simplepdf','simplebook','simplebook-mobi'):
            assert (prefix/'bin'/name).read_bytes()==(stage/'bin'/name).read_bytes()
    def fail():
        verify();raise RuntimeError('injected verification failure')
    try:
        transaction.install([stage],fail,managed_paths=managed,retired_paths=retired)
        raise AssertionError('failed verification accepted')
    except RuntimeError as error:
        assert 'injected' in str(error),error
    assert (prefix/'bin/simplepdf-mobi').read_text()=='ISO terminal simplepdf-mobi'
    assert (prefix/'bin/simpleread').read_text()=='ISO terminal simpleread'
    assert record.read_bytes()==original
    transaction.install([stage],verify,managed_paths=managed,retired_paths=retired)
    owned=json.loads(record.read_text())
    assert 'bin/simplebook' in owned
    for name in retired:
        assert name not in owned and (transaction.retained/'old'/name).exists()
    transaction.rollback()
    assert record.read_bytes()==original
    assert (prefix/'bin/simplepdf').read_text()=='ISO terminal simplepdf'
    assert (prefix/'bin/simplepdf-mobi').read_text()=='ISO terminal simplepdf-mobi'
    assert (prefix/'bin/simpleread').read_text()=='ISO terminal simpleread'
    assert not (prefix/'bin/simplebook').exists()
    assert (prefix/'bin/personal-tool').read_text()=='keep'
    # Exact ownership gates retirement; a personal file at an obsolete name
    # and a path containing traversal must never be removed.
    (prefix/'bin/simplepdf-mobi').write_text('personal edit')
    transaction.install([stage],lambda:None,managed_paths=managed,retired_paths=retired)
    assert (prefix/'bin/simplepdf-mobi').read_text()=='personal edit'
    transaction.rollback()
    try:
        transaction.install([stage],lambda:None,managed_paths=managed,retired_paths=('../escape',))
        raise AssertionError('retirement traversal accepted')
    except RuntimeError:pass
print('OK ISO reader upgrade, new payload discovery, obsolete owned helper/launcher retirement, failed verification, rollback and personal-file preservation')
