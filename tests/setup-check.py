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
    repo = home / 'simplewm'
    def checkout_git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    assert checkout_git('branch', '--show-current') == 'main'
    assert checkout_git('rev-parse', 'HEAD') == git('rev-parse', 'main').stdout.strip()
    assert checkout_git('rev-parse', '@{upstream}') == checkout_git('rev-parse', 'HEAD')
    assert checkout_git('ls-files') == 'config'
    assert cfg.is_symlink() and cfg.resolve()==home/'simplewm'
    assert (home/'simplewm/config').read_text()=='border 2\n'
    (home/'simplewm/config').write_text('border 3\n')
    assert (cfg/'config').read_text()=='border 3\n'
    subprocess.run(['python3',str(script)],env=env,check=True)
    assert (cfg/'palette.conf').read_text()=='# personal colors\n'
    assert list((home/'.state/simplewm').glob('config-before-link-*/old-config/config'))
    # A clean offline install must have a real commit and no untracked source.
    fresh = root / 'fresh-home'; fresh.mkdir()
    fresh_env = env | {'HOME': str(fresh), 'XDG_CONFIG_HOME': str(fresh / '.config'),
                       'XDG_STATE_HOME': str(fresh / '.state')}
    subprocess.run(['python3', str(script)], env=fresh_env, check=True)
    clean = subprocess.run(['git', '-C', str(fresh / 'simplewm'), 'status', '--porcelain'],
                           check=True, capture_output=True, text=True)
    assert clean.stdout == ''
    # A fresh install from an older ISO still has the old 13-point default.
    # The newly installed WM assets adopt 12 once, preserving personal edits.
    (data / 'fonts').mkdir()
    (data / 'fonts/UbuntuSansMono[wght].ttf').write_bytes(b'asset-present')
    legacy = (repo / 'config').read_text() + 'monospace_font "Ubuntu Sans Mono 13" # stock size\n'
    (repo / 'config').write_text(legacy)
    subprocess.run(['python3', str(script)], env=env, check=True)
    assert (repo / 'config').read_text() == legacy.replace('Mono 13', 'Mono 12')
    assert (home / '.state/simplewm/config-before-butterfonts').read_text() == legacy
    # A later intentional choice of 13 must remain a user choice.
    (repo / 'config').write_text(legacy)
    subprocess.run(['python3', str(script)], env=env, check=True)
    assert (repo / 'config').read_text() == legacy
    # Other font families and sizes are preserved on the first updated login.
    custom = fresh / 'simplewm/config'
    custom.write_text(custom.read_text() + 'monospace_font "My preferred mono 17"\n')
    before = custom.read_bytes()
    subprocess.run(['python3', str(script)], env=fresh_env, check=True)
    assert custom.read_bytes() == before
print('OK offline source setup, merged personal config, shared edits, backup and repeat setup')
