#!/usr/bin/python3
"""Apply SimpleOS policy to an extracted Debian 13 image, after package/build staging.

Input rootfs is disposable image staging. Never run against the host's /.
Latest SimpleSuite must already be built into payload/usr/local.
"""
import argparse
import configparser
from pathlib import Path
import shutil

RELEASE = '0.7-simplewm'
SOURCE = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rootfs', type=Path)
    parser.add_argument('payload', type=Path)
    parser.add_argument('suite_source', type=Path)
    parser.add_argument('--suite-revision',
                        help='verified official Suite commit represented by the staged payload')
    args = parser.parse_args()
    manifest = args.payload / 'usr/local/share/simplesuite/install-manifest'
    installed = next((line.split('=', 1)[1] for line in manifest.read_text().splitlines()
                      if line.startswith('simplesuite_source_sha=')), '')
    revision = args.suite_revision or installed
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        parser.error('--suite-revision must be a full Git commit SHA')
    if revision != installed:
        parser.error('Suite revision does not match the staged install manifest')
    root = args.rootfs.resolve()
    if root == Path('/') or not (root / 'etc/calamares/settings.conf').is_file():
        parser.error('expected an extracted SimpleOS live image')
    def remove(relative):
        path = root / relative
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
    def write(relative, text, mode=0o644):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(mode)
    def copy(source, relative):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)
    for relative in [
        'usr/local/bin/dwm', 'usr/local/src/dwm-simpleos', 'usr/share/xsessions/dwm.desktop',
        'usr/local/bin/simpleos-status', 'usr/local/bin/simpleos-trident-first-run',
        'usr/local/bin/wallpaper-theme-dwm.sh', 'usr/share/applications/simpleos-wallpaper.desktop',
        'etc/skel/.local/share/simplesuite', 'etc/skel/.xinitrc',
        'usr/local/share/simplesuite/source', 'usr/local/share/scriptorium/source',
        'usr/local/share/simpleos/CHANGES.csv', 'usr/local/share/simpleos/CHANGES.md',
        'usr/local/share/simpleos/payload.sha256',
    ]:
        remove(relative)
    # A previous prepared image uses a canonical sbin daemon with a bin symlink.
    # Replace that link before copying a fresh installer's regular bin payload.
    daemon_link = root / 'usr/local/bin/simpleserved'
    if daemon_link.is_symlink():
        daemon_link.unlink()
    shutil.copytree(args.payload / 'usr/local', root / 'usr/local', dirs_exist_ok=True, symlinks=True)
    # A clean source snapshot replaces the old snapshot; no stale files survive.
    shutil.copytree(args.suite_source, root / 'usr/local/share/simplesuite/source',
                    ignore=shutil.ignore_patterns('.git', 'build', '__pycache__'), symlinks=True)
    write('usr/local/share/simplesuite/install-source', '/usr/local/share/simplesuite/source\n')
    copy(root / 'usr/local/bin/simpleserved', 'usr/local/sbin/simpleserved')
    # Preserve the suite's public daemon invocation, with one canonical binary.
    remove('usr/local/bin/simpleserved')
    (root / 'usr/local/bin/simpleserved').symlink_to('../sbin/simpleserved')
    copy(SOURCE / 'image/simpleos-finalize-target', 'usr/local/sbin/simpleos-finalize-target')
    copy(SOURCE / 'image/login.sh', 'usr/local/share/simplewm/login.sh')
    copy(SOURCE / 'image/user-profile.sh', 'etc/skel/.profile')
    copy(SOURCE / 'image/calamares-show.qml', 'etc/calamares/branding/simpleos/show.qml')
    copy(SOURCE / 'image/20-simpleos-liquorix.cfg', 'etc/default/grub.d/20-simpleos-liquorix.cfg')
    write('usr/local/bin/simpleos-session', '#!/bin/sh\nexec /usr/local/bin/simplewm-session "$@"\n', 0o755)
    write('usr/local/bin/simpleos-screenshot', '#!/bin/sh\nexec /usr/local/bin/simplewm-screenshot "$@"\n', 0o755)
    write('etc/profile.d/simpleos-session.sh', '''# SimpleOS system defaults, also used by TTY and live installer terminals.
export QT_QPA_PLATFORMTHEME=${QT_QPA_PLATFORMTHEME:-gtk3}
export SIMPLEOS_BUNDLED_SIMPLESUITE_SOURCE=/usr/local/share/simplesuite/source
''')
    write('usr/local/share/applications/simplewm-wallpaper.desktop', '''[Desktop Entry]
Name=Wallpaper and colors
Comment=Choose a wallpaper and a legible palette
Exec=simpleterm -e wallpaper-theme --wizard
Icon=preferences-desktop-wallpaper
Type=Application
Terminal=false
Categories=Settings;DesktopSettings;
Keywords=wallpaper;theme;simplewm;
''')
    # Upgrade-safe identity: dpkg-divert must have been set before this script.
    if not (root / 'usr/lib/os-release.debian').is_file():
        raise RuntimeError('first divert /usr/lib/os-release to /usr/lib/os-release.debian with dpkg-divert')
    write('usr/lib/os-release', f'''PRETTY_NAME="SimpleOS {RELEASE} (Debian 13)"
NAME="SimpleOS"
VERSION_ID="{RELEASE}"
VERSION="{RELEASE} (Debian 13 trixie)"
VERSION_CODENAME=trixie
ID=simpleos
ID_LIKE=debian
HOME_URL="https://www.debian.org/"
SUPPORT_URL="https://www.debian.org/support"
BUG_REPORT_URL="https://github.com/kjwat/simplesuite/issues"
''')
    write('etc/issue', f'SimpleOS {RELEASE} \\n \\l\n\nLog in on tty1 to open SimpleWM. Super+F1: help. Updates: simpleupdate.\n\n')
    write('etc/issue.net', f'SimpleOS {RELEASE}\n')
    write('etc/motd', f'''SimpleOS {RELEASE} — the writing system

SimpleWM opens after login on the installed system's first console.
Super+Enter: Simpleterm. Super+Space: Firefox. Super+F1: help.
Updates: simpleupdate. The live medium keeps XFCE for Calamares.
''')
    for relative in ['VERSION', 'REVISION']:
        write('usr/local/share/simpleos/' + relative, (RELEASE if relative == 'VERSION' else revision[:12]) + '\n')
    write('usr/local/share/simpleos/simplesuite.commit', revision + '\n')
    write('usr/local/share/simpleos/SOURCES.lock', f'''SimpleOS {RELEASE}
Base: SimpleOS 0.6-r1 ISO (unaltered BIOS/UEFI boot loaders and XFCE Calamares flow)
SimpleWM: 0.1.0, GPL-3.0, local source /usr/local/share/simplewm/source
dwl protocol core: v0.7, 74e45c4014ae7048ecbb76eb6f54034b8b479480
SimpleSuite official: https://github.com/kjwat/simplesuite.git
SimpleSuite commit: {revision}
Suite source: /usr/local/share/simplesuite/source
Debian: trixie, trixie-updates, trixie-security, normal signed APT
Liquorix: https://liquorix.net/debian trixie main, dedicated Signed-By keyring
Custom commands/assets: /usr/local; user preferences/data remain in each home
Wallpaper palette engine: user-supplied wallpaper-theme-dwm.sh 3.8, adapted without fontbomb
''')
    branding = root / 'etc/calamares/branding/simpleos/branding.desc'
    branding.write_text(branding.read_text().replace('0.6-r1', RELEASE).replace('"#135BFF"', '"#536a5b"'))
    for version in ('gtk-3.0', 'gtk-4.0'):
        settings = root / f'etc/skel/.config/{version}/settings.ini'
        if settings.exists():
            settings.write_text(settings.read_text().replace('gtk-theme-name=SimpleOS', 'gtk-theme-name=Yaru-red-dark')
                                .replace('gtk-cursor-theme-name=Adwaita', 'gtk-cursor-theme-name=Yaru'))
    dconf = root / 'etc/dconf/db/simpleos.d/00-simpleos'
    dconf.write_text(dconf.read_text().replace("gtk-theme='SimpleOS'", "gtk-theme='Yaru-red-dark'")
                     .replace('Ubuntu Sans Mono 12', 'Ubuntu Sans Mono 13'))
    if '[org/gnome/desktop/peripherals/mouse]' not in dconf.read_text():
        with dconf.open('a') as out:
            out.write("\n[org/gnome/desktop/peripherals/mouse]\nspeed=0.0\nnatural-scroll=false\nleft-handed=false\n\n[org/gnome/desktop/peripherals/touchpad]\nspeed=0.0\nnatural-scroll=true\ntap-to-click=true\ndisable-while-typing=true\n")
    copy(SOURCE / 'image/simpleterm-settings.ini', 'etc/skel/.config/simpleterm/settings.ini')
    term = root / 'etc/skel/.config/simpleterm/settings.ini'
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(term)
    # Font follows the desktop instead of freezing a copied preference.
    cfg['Text']['font'] = 'Ubuntu Sans Mono 13'
    cfg['Text']['custom-font'] = 'false'
    with term.open('w') as out:
        cfg.write(out)
    bashrc = root / 'etc/skel/.bashrc'
    with bashrc.open('a') as out:
        for short, command in (('note', 'simplenote'), ('term', 'simpleterm'), ('save', 'simplesave')):
            if f'alias {short}=' not in bashrc.read_text():
                out.write(f"\nalias {short}='/usr/local/bin/{command}'\n")
    live_setup = root / 'usr/local/bin/simpleos-live-session-setup'
    live_setup.write_text(live_setup.read_text().replace('installed dwm system', 'installed SimpleWM system')
                          .replace('-s SimpleOS', '-s Yaru-red-dark').replace('Ubuntu Sans Mono 12', 'Ubuntu Sans Mono 13'))
    wallpaper = root / 'usr/local/bin/simpleos-default-wallpaper'
    wallpaper.write_text(wallpaper.read_text().replace('/usr/share/backgrounds/simpleos/', '/usr/local/share/backgrounds/simpleos/'))
    # The pre-existing battery policy is also a SimpleOS-owned executable.
    battery = root / 'usr/libexec/simpleos-battery-charge-limit'
    if battery.exists():
        copy(battery, 'usr/local/sbin/simpleos-battery-charge-limit')
        battery.unlink()
        unit = root / 'usr/lib/systemd/system/simpleos-battery-charge-limit.service'
        unit.write_text(unit.read_text().replace('/usr/libexec/simpleos-battery-charge-limit', '/usr/local/sbin/simpleos-battery-charge-limit'))
    print(f'Prepared {root}: {RELEASE}, SimpleWM, canonical latest suite source, Ubuntu settings')

if __name__ == '__main__':
    main()
