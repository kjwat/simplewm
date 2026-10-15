#!/usr/bin/python3
"""Check the installed font payload and real Fontconfig selection."""
import configparser
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='simplewm-fonts-') as temp:
    root = Path(temp)
    home = root / 'A writer’s desk'
    home.mkdir()
    stage = root / 'stage'
    subprocess.run(['make', '-C', str(source), f'DESTDIR={stage}', 'install-fonts'],
                   check=True, stdout=subprocess.DEVNULL)
    data = stage / 'usr/local/share/simplewm'
    fonts = data / 'fonts'
    for line in (source / 'fonts/SHA256SUMS').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        path = fonts / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert path.stat().st_mode & 0o777 == 0o644
    assert 'UBUNTU FONT LICENCE Version 1.0' in (fonts / 'LICENCE.txt').read_text()
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
               XDG_CACHE_HOME=str(home / '.cache'), GSETTINGS_BACKEND='memory',
               SIMPLEWM_SYSTEM_DATA_DIR=str(data))
    for name in ('FONTCONFIG_FILE', 'FONTCONFIG_PATH', 'SIMPLEWM_MONO_FONT', 'SIMPLEWM_FONT'):
        env.pop(name, None)
    subprocess.run(['/usr/bin/python3', str(source / 'scripts/simplewm-style')],
                   env=env, check=True)
    cfg = configparser.ConfigParser()
    cfg.read(home / '.config/gtk-3.0/settings.ini')
    assert cfg['Settings']['gtk-font-name'] == 'Ubuntu Sans 11'
    for family in ('Ubuntu Sans', 'Ubuntu Sans Mono'):
        for style in ('Regular', 'Bold', 'Italic', 'Bold Italic'):
            result = subprocess.run(['fc-match', '-f', '%{file}\n%{fontversion}\n%{hintstyle}\n%{rgba}\n',
                                     f'{family}:style={style}'],
                                    env=env, check=True, capture_output=True, text=True)
            path, version, hinting, rgba = result.stdout.splitlines()
            assert Path(path).parent == fonts, (family, style, result)
            assert version == '65929' and hinting == '1' and rgba == '1', result
    unrelated = subprocess.run(['fc-match', '-f', '%{family}\n', 'DejaVu Sans Mono'],
                               env=env, check=True, capture_output=True, text=True)
    assert unrelated.stdout.strip() == 'DejaVu Sans Mono'
print('OK staged font hashes/licence, captured regular/bold/italic faces, RGB/slight and other families')
