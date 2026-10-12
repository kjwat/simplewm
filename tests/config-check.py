#!/usr/bin/python3
import os
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).resolve().parent.parent
binary = source / 'build/simplewm'
base = (source / 'config').read_text()
passed = 0
with tempfile.TemporaryDirectory(prefix='simplewm-config-') as temp:
    root = Path(temp)
    cases = [
        ('default', base, True),
        ('unknown', base + '\nbogus value\n', False),
        ('bad color', base + '\ncolor focused #qwerty\n', False),
        ('negative gaps', base + '\ngaps inner -1\n', False),
        ('fractional gap', base + '\ngaps outer 1.5\n', False),
        ('NaN speed', base + '\ninput touchpad accel_speed=nan\n', False),
        ('oversized scale', base + '\noutput * scale=10\n', False),
        ('bad binding', base + '\nbindsym Super+MadeUp close\n', False),
        ('bad action', base + '\nbindsym Super+a destroy_everything\n', False),
        ('workspace bounds', base + '\nbindsym Super+a workspace 10\n', False),
        ('no quote', base + '\nfont "Ubuntu Sans 11\n', False),
        ('huge line', base + '\n' + 'a' * 9000, False),
        ('embedded NUL', base + '\nfont "a\0b"', False),
        ('quoted rule', base + '\nrule title="*A title with spaces*" floating=yes\n', True),
        ('shift digit', base + '\nbindsym Super+Shift+1 send 1\n', True),
        ('keymap error', base + '\nkeyboard_layout not_a_real_layout\n', False),
        ('include missing', base + '\ninclude missing.conf\n', False),
        ('variable override', base + '\nset $mod Alt\nbindsym $mod+j focus next\n', True),
        ('variable expansion', base + '\nset $editor $terminal -e nano\nbindsym Super+a exec $editor\n', True),
        ('invalid variable', base + '\nset $bad+name wrong\n', False),
    ]
    (root / 'palette.conf').write_text('color focused #aabbcc\n')
    cases.append(('include', base + '\ninclude palette.conf\n', True))
    (root / 'cycle.conf').write_text('include cycle.conf\n')
    cases.append(('include cycle', base + '\ninclude cycle.conf\n', False))
    for name, text, valid in cases:
        path = root / 'config'
        path.write_text(text)
        result = subprocess.run([str(binary), '--check-config', '-c', str(path)], capture_output=True, text=True)
        assert (result.returncode == 0) == valid, (name, result.stdout, result.stderr)
        if not valid:
            assert str(path) in result.stderr or 'cycle.conf' in result.stderr
        passed += 1
print(f'OK {passed} configuration cases')
