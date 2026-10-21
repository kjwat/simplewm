#!/usr/bin/python3
"""Upgrade terminal or previous native readers with the full Suite stage; roll back."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'updater'))
import transaction as tx
parser=argparse.ArgumentParser()
parser.add_argument('--stage',type=Path)
parser.add_argument('--previous-stage',type=Path,
                    help='previous full Suite /usr/local payload; defaults to ISO terminal readers')
args=parser.parse_args()
if args.previous_stage and not args.stage:
    parser.error('--previous-stage requires --stage')
with tempfile.TemporaryDirectory(prefix='update-readers-') as temporary:
    base=Path(temporary);prefix=base/'local';stage=base/'stage'
    if args.previous_stage:
        tx.freeze(args.previous_stage,prefix)
    else:
        (prefix/'bin').mkdir(parents=True);(prefix/'share/applications').mkdir(parents=True)
        for name in ('simplepdf','simplepdf-mobi','simpleread','simpleread-mobi'):
            p=prefix/'bin'/name;p.write_text('ISO terminal '+name);p.chmod(0o755)
        (prefix/'share/applications/simplepdf.desktop').write_text('ISO terminal launcher')
        (prefix/'share/applications/simpleread.desktop').write_text('previous terminal launcher')
    (prefix/'share/simpleupdate').mkdir(exist_ok=True)
    record=prefix/'share/simpleupdate/owned.json'
    tx.write_json(record,tx.inventory(prefix));original=record.read_bytes()
    (prefix/'bin/personal-tool').write_text('keep')
    before=tx.inventory(prefix)
    if args.stage:
        tx.freeze(args.stage,stage)
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
        assert fields['payload_scope']=='full'
        assert 'simplepdf' in fields['installed_programs'].split()
        assert set(retired) <= set(fields['retired_paths'].split())
    def check_pdf():
        if not args.stage:
            return
        binary=prefix/'bin/simplepdf'
        # The full Suite payload consumed by SimpleUpdate must carry the same
        # embedded view fixes and reader styling as a standalone installation.
        env=dict(os.environ)
        env.pop('LD_LIBRARY_PATH',None);env.pop('LD_PRELOAD',None)
        subprocess.run([str(binary),'--version'],env=env,check=True)
        if sys.platform.startswith('linux'):
            dynamic=subprocess.check_output(['readelf','-d',str(binary)],text=True)
            assert 'libevview3.so' not in dynamic,dynamic
            assert 'RUNPATH' not in dynamic and 'RPATH' not in dynamic,dynamic
        resources=subprocess.check_output(['gresource','list',str(binary)],text=True).splitlines()
        for name in ('simplepdf.css','simplepdf-page-frame.png'):
            assert '/org/simplesuite/Simplepdf/'+name in resources,name
        desktop=prefix/'share/applications/org.simplesuite.Simplepdf.desktop'
        assert 'Exec=simplepdf %F' in desktop.read_text()
        subprocess.run(['desktop-file-validate',str(desktop)],check=True)
        for name in ('simplepdf.svg','SIMPLEPDF.md','EVINCE-NOTICE.md',
                     'EVINCE-COPYING','EVINCE-COPYING.LGPL'):
            path='share/simplesuite/simplepdf/'+name
            assert tx.fingerprint(prefix/path)==managed[path],path
    transaction=tx.Transaction(prefix)
    def verify():
        for name in retired:
            assert not (prefix/name).exists(),name
        for name in ('simplepdf','simplebook','simplebook-mobi'):
            assert (prefix/'bin'/name).read_bytes()==(stage/'bin'/name).read_bytes()
        check_pdf()
    def fail():
        verify();raise RuntimeError('injected verification failure')
    try:
        transaction.install([stage],fail,managed_paths=managed,retired_paths=retired)
        raise AssertionError('failed verification accepted')
    except RuntimeError as error:
        assert 'injected' in str(error),error
    assert record.read_bytes()==original
    assert tx.inventory(prefix)==before,'failed verification did not restore the complete previous payload'
    transaction.install([stage],verify,managed_paths=managed,retired_paths=retired)
    owned=json.loads(record.read_text())
    assert 'bin/simplebook' in owned
    for path in managed:
        assert owned[path]==managed[path],path
    for name in retired:
        assert name not in owned
        assert (transaction.retained/'old'/name).exists()==(name in before),name
    transaction.rollback()
    assert record.read_bytes()==original
    assert (prefix/'bin/personal-tool').read_text()=='keep'
    assert tx.inventory(prefix)==before,'rollback did not restore the complete previous payload'
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
if args.stage:
    print('OK updated native PDF executable, embedded view/resources, launcher and licensing through the full Suite transaction')
print('OK reader upgrade, new payload discovery, obsolete owned helper/launcher retirement, failed verification, rollback and personal-file preservation')
