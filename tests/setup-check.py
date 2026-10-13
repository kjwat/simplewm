#!/usr/bin/python3
"""Offline setup merges settings and keeps both public paths on the same files."""
from pathlib import Path
import os, subprocess, tempfile
script = Path(__file__).resolve().parents[1] / 'scripts/simplewm-setup'
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp); home = root/'home'; home.mkdir()
    data = root/'data'; data.mkdir()
    source = root/'source'; source.mkdir()
    def git(*args):
        return subprocess.run(['git','-C',str(source),*args],check=True,capture_output=True,text=True)
    git('init','-b','main')
    git('config','user.name','Test'); git('config','user.email','test@example.invalid')
    (source/'config').write_text('border 1\n')
    git('add','config'); git('commit','-m','defaults')
    git('bundle','create',str(data/'source.bundle'),'main')
    (data/'config').write_text('border 1\n')
    cfg=home/'.config/simplewm'; cfg.mkdir(parents=True)
    (cfg/'config').write_text('border 2\n')
    (cfg/'palette.conf').write_text('# personal colors\n')
    env=os.environ|{'HOME':str(home),'XDG_CONFIG_HOME':str(home/'.config'),'XDG_STATE_HOME':str(home/'.state'),'SIMPLEWM_SYSTEM_DATA_DIR':str(data)}
    subprocess.run(['python3',str(script)],env=env,check=True)
    assert cfg.is_symlink() and cfg.resolve()==home/'simplewm'
    assert (home/'simplewm/config').read_text()=='border 2\n'
    (home/'simplewm/config').write_text('border 3\n')
    assert (cfg/'config').read_text()=='border 3\n'
    subprocess.run(['python3',str(script)],env=env,check=True)
    assert (cfg/'palette.conf').read_text()=='# personal colors\n'
    assert list((home/'.state/simplewm').glob('config-before-link-*/old-config/config'))
print('OK offline source setup, merged personal config, shared edits, backup and repeat setup')
