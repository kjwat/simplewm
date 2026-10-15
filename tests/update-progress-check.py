#!/usr/bin/python3
"""Exercise the actual progress renderer and silent commands through a PTY."""
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parent.parent
DRIVER = r'''
import importlib.machinery, importlib.util, signal, subprocess, sys
loader = importlib.machinery.SourceFileLoader('update', sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
update = importlib.util.module_from_spec(spec); loader.exec_module(update)
handler = signal.getsignal(signal.SIGALRM)
with open(sys.argv[2], 'w') as log:
    update.LOG_STREAM = log
    update.QUIET = sys.argv[3] != 'verbose'
    progress = update.Progress(); update.PROGRESS = progress
    success = False
    try:
        progress.start()
        progress.step(1, 'Checking repositories')
        progress.step(5, 'Building SimpleSuite')
        update.run([sys.executable, '-c',
            "import time; print('CC simplepdf-mobi', flush=True); time.sleep(1.6)"])
        if sys.argv[3] == 'failure':
            update.run([sys.executable, '-c', "raise SystemExit(3)"])
        progress.step(6, 'Installing programs')
        progress.files('Installing', 3, 4)
        progress.step(7, 'Verifying installation')
        success = True
    except subprocess.CalledProcessError as error:
        assert error.returncode == 3
    finally:
        progress.close(success=success)
        update.PROGRESS = None
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == handler
    update.say('Finished' if success else 'Failed')
'''

with tempfile.TemporaryDirectory(prefix='progress-check-') as temp:
    base = Path(temp); driver = base / 'driver.py'; driver.write_text(DRIVER)
    for mode in ('quiet', 'verbose', 'failure'):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 140, 0, 0))
        log = base / (mode + '.log')
        process = subprocess.Popen([sys.executable, str(driver), str(ROOT / 'scripts/simpleupdate'),
                                    str(log), mode], stdout=slave, stderr=slave)
        os.close(slave)
        output = b''; live_frames = 0; deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                if not select.select([master], [], [], 0.1)[0]:
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output += chunk
                if b'0:01 Building SimpleSuite' in chunk and process.poll() is None:
                    live_frames += 1
            else:
                raise AssertionError('progress command hung')
            assert process.wait(timeout=3) == 0, output.decode()
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
            os.close(master)
        assert live_frames, 'no heartbeat while the compiler was silent'
        assert b'[#############-----------]' in output, output.decode()
        assert (b'[########################]' in output) == (mode != 'failure')
        assert output.rstrip().endswith(b'Failed' if mode == 'failure' else b'Finished')
        assert 'CC simplepdf-mobi\n' in log.read_text()
        assert '\x1b' not in log.read_text(), 'terminal controls leaked into the transcript'
    result = subprocess.run([sys.executable, str(driver), str(ROOT / 'scripts/simpleupdate'),
                             str(base / 'pipe.log'), 'quiet'], capture_output=True, text=True, check=True)
    assert '\x1b' not in result.stdout and '\r' not in result.stdout
    assert '[########################]' in result.stdout
    print('OK filling terminal bar, live heartbeat during silent commands, verbose output, clean logs/pipes and failure cleanup')
