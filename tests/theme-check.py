#!/usr/bin/python3
import configparser
import os
from pathlib import Path
import subprocess
import tempfile
from PIL import Image

source=Path(__file__).resolve().parent.parent
tool=source / 'scripts/simplewm-theme'
with tempfile.TemporaryDirectory(prefix='simplewm-theme-') as temp:
    home=Path(temp) / 'A writer’s desk'
    home.mkdir()
    cfg=home / '.config'
    (cfg / 'simplewm').mkdir(parents=True)
    config=cfg / 'simplewm/config'
    original=(source / 'config').read_text()
    config.write_text(original)
    (cfg / 'simpleterm').mkdir()
    terminal=cfg / 'simpleterm/settings.ini'
    old='[Text]\nfont=My beloved font 17\ncustom-font=true\ncell-height=1.2\n[Colors]\nforeground=rgb(1,2,3)\n'
    terminal.write_text(old)
    (cfg / 'gtk-3.0').mkdir()
    gtk=cfg / 'gtk-3.0/gtk.css'
    gtk.write_text('/* personal CSS */\n')
    firefox=cfg / 'mozilla/firefox/writer.default'
    firefox.mkdir(parents=True)
    (firefox.parent / 'profiles.ini').write_text('[Profile0]\nPath=writer.default\nIsRelative=1\n')
    (firefox / 'user.js').write_text('user_pref("browser.startup.page", 3);\n')
    env=os.environ.copy()
    for key in ('SIMPLEWM_SOCKET','DISPLAY','WAYLAND_DISPLAY'):
        env.pop(key,None)
    env.update(HOME=str(home),XDG_CONFIG_HOME=str(cfg),XDG_DATA_HOME=str(home / '.local/share'),
               XDG_STATE_HOME=str(home / '.local/state'))
    image=home / 'wallpaper with spaces.png'
    Image.new('RGB',(128,128),(23,80,54)).save(image)
    # With no image argument the original terminal wizard must be used.
    wizard = subprocess.run(['python3',str(tool)], input=str(image) + '\n\n',
                            env=env, check=True, text=True, capture_output=True)
    assert 'Wallpaper image (path):' in wizard.stdout
    assert 'Mode: fit / fill / center / stretch / tile [fill]:' in wizard.stdout
    term=configparser.ConfigParser()
    term.read(terminal)
    assert dict(term['Text'])=={'font':'My beloved font 17','custom-font':'true','cell-height':'1.2'}
    assert 'include palette*.conf' in config.read_text()
    assert 'A writer’s desk' in (cfg / 'simplewm/palette.conf').read_text()
    assert 'personal CSS' in gtk.read_text()
    assert 'browser.startup.page' in (firefox / 'user.js').read_text()
    assert (firefox / 'chrome/wallpaper-theme.css').exists()
    subprocess.run(['python3',str(tool),'--rollback'],env=env,check=True)
    assert config.read_text()==original
    assert terminal.read_text()==old
    assert gtk.read_text()=='/* personal CSS */\n'
    assert not (cfg / 'simplewm/palette.conf').exists()
print('OK wallpaper palette, Unicode/spaced paths, font preservation, existing GTK/Firefox config preservation, and rollback')
