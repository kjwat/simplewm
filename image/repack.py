#!/usr/bin/python3
"""Repack a prepared SimpleOS live filesystem and preserve hybrid BIOS/UEFI boot."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent

def run(*args, **options):
    print(' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **options)

def digest(path, algorithm='sha256'):
    value = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_iso', type=Path)
    parser.add_argument('rootfs', type=Path)
    parser.add_argument('media', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--reuse-squashfs', action='store_true', help='only after verifying rootfs is unchanged')
    args = parser.parse_args()
    base, root, media, output = [value.resolve() for value in (args.base_iso, args.rootfs, args.media, args.output)]
    if root == Path('/') or media == Path('/') or not (root / 'etc/calamares/settings.conf').exists():
        parser.error('expected disposable extracted SimpleOS staging trees')
    if not (media / 'isolinux/isolinux.bin').exists() or output == base:
        parser.error('missing extracted media or output would replace the base')
    live = media / 'live'
    listing = subprocess.run(['xorriso', '-indev', str(base), '-find', '/live', '-type', 'f', '-exec', 'echo'],
                             capture_output=True, text=True, check=True).stdout
    obsolete = [p.strip("'\"") for p in listing.splitlines()
                if p.strip("'\"").startswith(('/live/vmlinuz-', '/live/initrd.img-'))]
    for path in live.iterdir():
        if path.name.startswith(('vmlinuz-', 'initrd.img-')):
            path.unlink()
    liquorix = sorted((root / 'boot').glob('vmlinuz-*-liquorix-amd64'))[-1]
    debian = sorted((root / 'boot').glob('vmlinuz-*+deb13-amd64'))[-1]
    version = liquorix.name[len('vmlinuz-'):]
    fallback = debian.name[len('vmlinuz-'):]
    for source, name in [(liquorix, 'vmlinuz'), (root / f'boot/initrd.img-{version}', 'initrd.img'),
                         (debian, debian.name), (root / f'boot/initrd.img-{fallback}', f'initrd.img-{fallback}')]:
        shutil.copy2(source, live / name)
    print(f'Default live kernel: {version}; fallback: {fallback}', flush=True)
    config = media / 'boot/grub/grub.cfg'
    display_config = media / 'boot/grub/config.cfg'
    display_config.write_text(display_config.read_text().replace('set gfxmode=800x600', 'set gfxmode=auto'))
    config.write_text(f'''source /boot/grub/config.cfg

menuentry "Start SimpleOS (Liquorix, XFCE installer)" --hotkey=l {{
    linux /live/vmlinuz boot=live components quiet splash loglevel=3 rd.systemd.show_status=auto findiso=${{iso_path}}
    initrd /live/initrd.img
}}
menuentry "SimpleOS live (Debian kernel fallback)" {{
    linux /live/vmlinuz-{fallback} boot=live components quiet splash findiso=${{iso_path}}
    initrd /live/initrd.img-{fallback}
}}
menuentry "SimpleOS live (Liquorix, basic graphics)" {{
    linux /live/vmlinuz boot=live components nomodeset nosplash
    initrd /live/initrd.img
}}
submenu "Utilities..." --hotkey=u {{
    source /boot/grub/theme.cfg
    if [ "${{grub_platform}}" = "efi" ]; then
        menuentry "UEFI Firmware Settings" --hotkey=f {{ fwsetup; }}
    fi
    menuentry "Verify integrity of the SimpleOS boot medium" --hotkey=v {{
        linux /live/vmlinuz boot=live components findiso=${{iso_path}} verify-checksums
        initrd /live/initrd.img
    }}
}}
''')
    (media / 'isolinux/live.cfg').write_text(f'''label live-amd64
    menu label ^Start SimpleOS (Liquorix, XFCE installer)
    menu default
    linux /live/vmlinuz
    initrd /live/initrd.img
    append boot=live components quiet splash loglevel=3 rd.systemd.show_status=auto

label live-debian
    menu label SimpleOS live (Debian kernel fallback)
    linux /live/vmlinuz-{fallback}
    initrd /live/initrd.img-{fallback}
    append boot=live components quiet splash

label live-basic
    menu label SimpleOS live (Liquorix, basic graphics)
    linux /live/vmlinuz
    initrd /live/initrd.img
    append boot=live components nomodeset nosplash
''')
    menu = media / 'isolinux/menu.cfg'
    menu.write_text(re.sub(r'menu title SimpleOS .* - the writing system',
                          'menu title SimpleOS 0.8 - SimpleWM writing desk', menu.read_text()))
    (media / '.disk/info').write_text('SimpleOS 0.8 SimpleWM - amd64 live/install image, Liquorix default\n')
    (media / '.disk/mkisofs').write_text('SimpleOS: original hybrid BIOS/UEFI boot layout replayed with xorriso; see SimpleWM image/repack.py\n')
    # Restore metadata lost by rootless extraction, retaining only existing paths.
    pseudo = media.parent / 'simplewm-ownership.pseudo'
    entries = []
    for line in (HERE / 'base-ownership-and-xattrs.pseudo').read_text().splitlines():
        if line.startswith('#') or not line.strip():
            continue
        path = root / line.split()[0]
        if path.exists() or path.is_symlink():
            entries.append(line)
    pseudo.write_text('\n'.join(entries) + '\n')
    if not args.reuse_squashfs:
        total = sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())
        (live / 'filesystem.size').write_text(str(total) + '\n')
        run('mksquashfs', root, live / 'filesystem.squashfs', '-noappend', '-comp', 'xz', '-b', '1048576',
            *([] if os.geteuid() == 0 else ['-all-root', '-pseudo-override', '-pf', pseudo]),
            '-processors', min(8, os.cpu_count() or 1),
            '-mem', '4G', '-no-progress')
    result = run('unsquashfs', '-ll', live / 'filesystem.squashfs', 'usr/bin/sudo', 'usr/bin/pkexec',
                 capture_output=True, text=True).stdout
    for path in ('usr/bin/sudo', 'usr/bin/pkexec'):
        if not re.search(r'-rwsr-xr-x\s+.*squashfs-root/' + re.escape(path) + r'$', result, re.M):
            raise RuntimeError(f'privileged mode missing: {path}')
    # Every media file is covered except boot bytes rewritten by xorriso and
    # self-referential checksum lists. Uppercase/md5 also cover sha256sum.txt.
    excluded = {'SHA256SUMS', 'md5sum.txt', 'sha256sum.txt', 'isolinux/boot.cat', 'isolinux/isolinux.bin'}
    files = sorted(p for p in media.rglob('*') if p.is_file() and str(p.relative_to(media)) not in excluded)
    sha = {p: digest(p) for p in files}
    lower = ''.join(f'{sha[p]}  ./{p.relative_to(media)}\n' for p in files)
    (media / 'sha256sum.txt').write_text(lower)
    (media / 'SHA256SUMS').write_text(lower + f'{digest(media / "sha256sum.txt")}  ./sha256sum.txt\n')
    (media / 'md5sum.txt').write_text(''.join(f'{digest(p, "md5")}  ./{p.relative_to(media)}\n'
                                                for p in [*files, media / 'sha256sum.txt']))
    modified = ['.disk/info', '.disk/mkisofs', 'isolinux/menu.cfg', 'isolinux/live.cfg', 'boot/grub/grub.cfg', 'boot/grub/config.cfg',
                'SHA256SUMS', 'sha256sum.txt', 'md5sum.txt']
    modified.extend(f'live/{p.name}' for p in live.iterdir())
    temporary = output.with_name('.' + output.name + '.building')
    if temporary.exists():
        temporary.unlink()
    command = ['xorriso', '-indev', str(base), '-outdev', str(temporary), '-boot_image', 'any', 'replay',
               '-volid', 'SIMPLEOS_0_8']
    # Remove obsolete versioned kernels from the base, including on repeat builds.
    if obsolete:
        command.extend(['-rm', *obsolete, '--'])
    for relative in modified:
        command.extend(['-map', str(media / relative), '/' + relative])
    run(*command, '-commit', '-end')
    temporary.replace(output)
    output.with_suffix(output.suffix + '.sha256').write_text(digest(output) + '  ' + output.name + '\n')
    print(f'Built {output}', flush=True)

if __name__ == '__main__':
    main()
