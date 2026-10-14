#!/usr/bin/python3
"""Run the r3 ISO updater unchanged against real Git source/build/install.

Requires root for real root/nobody credentials inside a mount/PID namespace.
Pass a disposable extracted ISO rootfs and a NEW work directory. All writes
are confined to a copy of that rootfs. Debian/Liquorix full-upgrade is simulated;
APT index refresh, signed dependency installation, compilation, source/history
checks and the installation transaction are real. Only Git network transport
uses local HTTP fixtures so unpublished source can be verified before pushing.
"""
import argparse
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

REPO = Path(__file__).resolve().parent.parent
R3_WM = '4793cbca276a6a5e1155911eb153250083b7e661'


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=*', *map(str, args)], text=True).strip()


def write(path, contents, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    path.chmod(mode)


SHIM = '''#!/usr/bin/python3
import json,os,sys,subprocess
from pathlib import Path
config=json.loads(Path('/audit/config.json').read_text())
name=Path(sys.argv[0]).name
args=sys.argv[1:]
record={'command':name,'args':args,'uid':os.getuid(),'gid':os.getgid()}
if name=='git' and 'fetch' in args and 'origin' in args:
    directory=args[args.index('-C')+1]
    origin=subprocess.check_output(['/usr/bin/git','-C',directory,'remote','get-url','origin'],text=True).strip()
    if origin in config['origins']:
        args[args.index('origin')]=config['origins'][origin]
        record['fixture_transport']=args[args.index('fetch')+1:]
if name=='apt-get' and 'full-upgrade' in args:
    args=['-s' if arg=='-y' else arg for arg in args]
    record['os_upgrade_simulated']=True
with open('/audit-output/commands.jsonl','a') as output:
    output.write(json.dumps(record)+'\\n')
os.execv('/usr/bin/'+name,[name,*args])
'''

GUEST = '''#!/usr/bin/python3
import hashlib,json,os,subprocess,time
from pathlib import Path
config=json.loads(Path('/audit/config.json').read_text())
output=Path('/audit-output')
exe=Path('/usr/local/bin/simpleupdate')
# A booted installation creates these volatile paths through tmpfiles/systemd.
Path('/run/lock').mkdir(exist_ok=True)
Path('/run/lock').chmod(0o1777)
Path('/tmp').chmod(0o1777)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def revision(component):
    text=Path('/usr/local/share/'+component+'/install-manifest').read_text()
    return dict(line.split('=',1) for line in text.splitlines())[component+'_source_sha']
assert os.geteuid()==0
assert sha(exe)==config['original_updater_sha256']
assert revision('simplewm')==config['original_wm']
assert revision('simplesuite')==config['suite']
personal=Path('/home/writer/.config/simplewm/config')
document=Path('/home/writer/writing/preserved.txt')
before={str(path):sha(path) for path in (personal,document)}
report={'original_wm':revision('simplewm'),'original_updater_sha256':sha(exe),
        'target_wm':config['target_wm'],'os_full_upgrade_simulated':True,
        'apt_dependency_install_real':True,'updater_modified_before_run':False}
for invocation in ('first','repeat'):
    start=time.monotonic()
    with (output/(invocation+'.log')).open('w') as transcript:
        result=subprocess.run([str(exe)],stdout=transcript,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
                              env=os.environ|{'DEBIAN_FRONTEND':'noninteractive'},timeout=900)
    report[invocation]={'exit_code':result.returncode,'elapsed_seconds':round(time.monotonic()-start,2)}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\\n')
    if result.returncode:
        raise SystemExit((output/(invocation+'.log')).read_text())
    assert sha(exe)==config['new_updater_sha256']
    assert revision('simplewm')==config['target_wm']
    assert revision('simplesuite')==config['suite']
    helper=Path('/usr/local/bin/simpleupdate-target')
    assert os.access(helper,os.X_OK) and sha(helper)==config['new_helper_sha256']
    assert os.access('/usr/local/bin/simplewm-lock-client',os.X_OK)
    assert not Path('/usr/local/.simpleupdate-transaction').exists()
    for filename,digest in before.items():assert sha(Path(filename))==digest
    for binary in ('simplewm','simplewm-lock-client'):
        linkage=subprocess.check_output(['ldd','/usr/local/bin/'+binary],text=True)
        assert 'not found' not in linkage
    log=(output/(invocation+'.log')).read_text()
    assert ('Building SimpleWM' in log)==(invocation=='first')
    print('OK '+invocation+': unchanged ISO updater installs its replacement' if invocation=='first'
          else 'OK repeat: newly installed updater runs and skips unchanged source',flush=True)
assert config['original_updater_sha256']!=sha(exe)
help_result=subprocess.check_output([str(exe),'--help'],text=True)
assert '--dry-run' in help_result and '--release-upgrade' in help_result
commands=[json.loads(line) for line in (output/'commands.jsonl').read_text().splitlines()]
fetches=[row for row in commands if row.get('fixture_transport')]
assert fetches and all(row['uid']==65534 and row['gid']==65534 for row in fetches)
installs=[row for row in commands if row['command']=='apt-get' and 'install' in row['args']]
assert installs and all(row['uid']==0 for row in installs)
assert any('libcairo2-dev' in row['args'] for row in installs)
makes=[row for row in commands if row['command']=='make']
assert makes and all(row['uid']==65534 and row['gid']==65534 for row in makes)
assert any('install' in row['args'] for row in makes)
report.update({'installed_updater_sha256':sha(exe),'installed_wm':revision('simplewm'),
    'personal_files_preserved':True,'build_git_uid':65534,'build_git_gid':65534,
    'build_make_uid':65534,'build_make_gid':65534,'runtime_libraries_resolved':True,
    'normal_invocations':2,'separate_bootstrap_command':False})
(output/'result.json').write_text(json.dumps(report,indent=2)+'\\n')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', required=True, type=Path, help='original extracted 0.8-r3 ISO rootfs; preserved')
    parser.add_argument('--work-dir', required=True, type=Path, help='new disposable work directory')
    parser.add_argument('--suite-source', type=Path, default=REPO.parent / 'simplesuite')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('administrator authentication is required for real root/nobody isolation')
    original = args.rootfs.resolve()
    work = args.work_dir.resolve()
    if original == Path('/') or work == Path('/') or work.is_relative_to(original):
        parser.error('expected separate disposable extraction and work directories')
    if work.exists():
        parser.error('work directory already exists; use a new directory')
    for program in ('bwrap', 'git'):
        if not shutil.which(program): parser.error('missing test tool: '+program)
    baseline = (original / 'usr/local/bin/simpleupdate').read_bytes()
    expected = subprocess.check_output(['git', '-c', 'safe.directory=*', '-C', str(REPO),
        'show', R3_WM + ':scripts/simpleupdate'])
    if baseline != expected:
        parser.error('rootfs updater does not match the original r3 ISO revision')
    target = git('-C', REPO, 'rev-parse', 'HEAD')
    original_manifests = dict(line.split('=',1) for line in
        (original / 'usr/local/share/simplesuite/install-manifest').read_text().splitlines())
    suite = original_manifests['simplesuite_source_sha']
    work.mkdir(parents=True, mode=0o755)
    fixture = work / 'http'; fixture.mkdir()
    for name, source, revision in (('simplewm', REPO, target), ('simplesuite', args.suite_source, suite)):
        bare = fixture / (name + '.git')
        # A bundle avoids local clone's separate upload-pack ownership check
        # when this root test reads the workspace user's repository.
        bundle = work / (name + '.bundle')
        git('-C', source, 'bundle', 'create', bundle, '--all')
        git('-c', 'init.defaultBranch=main', 'clone', '--quiet', '--bare', bundle, bare)
        bundle.unlink()
        git('-C', bare, 'update-ref', 'refs/heads/main', revision)
        git('-C', bare, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        git('-C', bare, 'update-server-info')
    print('Copying the original ISO filesystem into a disposable test root.', flush=True)
    root = work / 'rootfs'
    shutil.copytree(original, root, symlinks=True)
    audit = work / 'audit'; audit.mkdir(mode=0o755)
    output = work / 'output'; output.mkdir(mode=0o755)
    write(output / 'commands.jsonl', '', 0o666)
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
        functools.partial(Handler, directory=str(fixture)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_address[1]}'
    current = subprocess.check_output(['git', '-c', 'safe.directory=*', '-C', str(REPO),
        'show', target + ':scripts/simpleupdate'])
    helper = subprocess.check_output(['git', '-c', 'safe.directory=*', '-C', str(REPO),
        'show', target + ':scripts/simpleupdate-target'])
    config = {'original_wm':R3_WM,'target_wm':target,'suite':suite,
        'original_updater_sha256':hashlib.sha256(baseline).hexdigest(),
        'new_updater_sha256':hashlib.sha256(current).hexdigest(),
        'new_helper_sha256':hashlib.sha256(helper).hexdigest(),
        'origins':{f'https://github.com/kjwat/{name}.git':url+'/'+name+'.git'
                   for name in ('simplewm','simplesuite')}}
    write(audit / 'config.json', json.dumps(config,indent=2)+'\n')
    write(audit / 'guest.py', GUEST)
    for program in ('git','apt-get','make'):
        write(root / 'usr/local/bin' / program, SHIM, 0o755)
    write(root / 'usr/sbin/policy-rc.d', '#!/bin/sh\nexit 101\n', 0o755)
    write(root / 'home/writer/.config/simplewm/config', '# personal settings must survive\ngaps inner 7\n')
    write(root / 'home/writer/writing/preserved.txt', 'personal writing must survive\n')
    command = ['bwrap','--die-with-parent','--unshare-pid','--unshare-ipc','--unshare-uts',
        '--bind',str(root),'/', '--proc','/proc','--dev','/dev','--tmpfs','/run','--tmpfs','/tmp',
        '--ro-bind',str(audit),'/audit','--bind',str(output),'/audit-output',
        '--ro-bind','/etc/resolv.conf','/etc/resolv.conf','--chdir','/']
    for cap in ('CAP_CHOWN','CAP_DAC_OVERRIDE','CAP_FOWNER','CAP_SETGID','CAP_SETUID','CAP_SYS_CHROOT'):
        command += ['--cap-add',cap]
    command += ['--','/usr/bin/python3','/audit/guest.py']
    try:
        print('Running plain simpleupdate twice with original root/nobody credentials.', flush=True)
        run(command, timeout=1800, env={key:value for key,value in os.environ.items()
            if key not in ('DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','SIMPLEWM_SOCKET')})
        print('Result:',output / 'result.json', flush=True)
    finally:
        server.shutdown(); server.server_close()
        # Keep evidence readable to the workspace owner after the root test.
        owner = REPO.stat()
        for path in (output, *output.iterdir()): os.chown(path, owner.st_uid, owner.st_gid)


if __name__ == '__main__':
    main()
