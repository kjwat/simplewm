#!/usr/bin/python3
"""Real signed seed/update/build test inside a disposable copy of a cached ISO root.

Requires root for mount namespaces and real root/nobody separation. No host APT
or installation. A test HTTPS origin and Git transport serve unpublished source;
APT dependency installation and WM compilation are real, full-upgrade simulated.
"""
import argparse
import functools
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tarfile
import threading

REPO = Path(__file__).resolve().parent.parent

def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)

def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=*', '-c', 'user.name=Updater Test',
        '-c', 'user.email=test@example.invalid', *map(str, args)], text=True).strip()

def write(path, contents, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(contents); path.chmod(mode)

SHIM = '''#!/usr/bin/python3.13
import json,os,sys,subprocess
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
record={'command':name,'args':args,'uid':os.getuid(),'gid':os.getgid()}
if name=='git' and 'fetch' in args and 'origin' in args:
    directory=args[args.index('-C')+1]
    origin=subprocess.check_output(['/usr/bin/git','-C',directory,'remote','get-url','origin'],text=True).strip()
    name_in=origin.rsplit('/',1)[-1]
    args[args.index('origin')]='http://127.0.0.1:PORT/'+name_in
    record['fixture_transport']=True
if name=='apt-get' and 'full-upgrade' in args:
    args=['-s' if arg=='-y' else arg for arg in args if arg!='--download-only']
    record['os_upgrade_simulated']=True
with open('/audit-output/commands.jsonl','a') as output:output.write(json.dumps(record)+'\\n')
os.execv('/usr/bin/'+('python3.13' if name=='python3' else name),[name,*args])
'''

GUEST = r'''import hashlib,importlib.util,json,os,shutil,subprocess,sys,time
from pathlib import Path
output=Path('/audit-output'); config=json.loads(Path('/audit/config.json').read_text())
os.umask(0o022)
Path('/run/lock').mkdir(exist_ok=True); Path('/tmp').chmod(0o1777); Path('/dev/shm').chmod(0o1777)
# Install the seed through the actual Makefile DESTDIR path. Cached binaries
# belong to the same WM sources; the ordinary update below really recompiles.
subprocess.run(['make','-C','/seed-source','-o','build/simplewm','-o','build/simplewm-lock-client',
                'DESTDIR=/seed-payload','install'],check=True)
prefix=Path('/usr/local'); stage=Path('/seed-payload/usr/local')
for name in ('source','source.bundle','install-manifest'):
    src=prefix/'share/simplewm'/name; dst=stage/'share/simplewm'/name
    if src.is_dir():shutil.copytree(src,dst,symlinks=True)
    elif src.exists():shutil.copyfile(src,dst)
subprocess.run(['cp','-a',str(stage)+'/.',str(prefix)],check=True)
# Build an explicit real Suite package stage. This also supplies a complete
# ownership inventory for the later grouped --rebuild and final image path.
seedmetadata=(prefix/'share/simpleupdate/release.json').read_bytes()
seedname=str(json.loads(seedmetadata)['version'])+'-'+hashlib.sha256(seedmetadata).hexdigest()
seedversion=prefix/'libexec/simpleupdate/versions'/seedname
spec=importlib.util.spec_from_file_location('seed_engine',seedversion/'engine.py')
seedengine=importlib.util.module_from_spec(spec); spec.loader.exec_module(seedengine)
legacy=seedengine.load_legacy()
with (output/'suite-seed-dependencies.log').open('w') as log:
    subprocess.run(['/usr/local/bin/apt-get','update','-o','APT::Update::Error-Mode=any'],
                   stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run(['/usr/local/bin/apt-get','-y','--no-install-recommends','install',*legacy.BUILD_PACKAGES],
                   stdout=log,stderr=subprocess.STDOUT,check=True)
suitework=Path('/var/tmp/suite-seed'); suitework.mkdir(); os.chown(suitework,65534,65534)
suitehome=suitework/'home'; suitehome.mkdir(); os.chown(suitehome,65534,65534)
suitestage=Path('/suite-payload'); suitestage.mkdir(); os.chown(suitestage,65534,65534)
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(suitehome),'LANG':'C.UTF-8',
     'LC_ALL':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','PYTHONDONTWRITEBYTECODE':'1'}
subprocess.run(['git','clone','--quiet',config['suite_url'],str(suitework/'source')],
               env=env,user=65534,group=65534,extra_groups=[],check=True)
subprocess.run(['git','-C',str(suitework/'source'),'checkout','--quiet','--detach',config['suite']],
               env=env,user=65534,group=65534,extra_groups=[],check=True)
plan=suitework/'plan.json'; plan.write_text(json.dumps({'component':'SimpleSuite',
    'source':str(suitework/'source'),'stage':str(suitestage),'sha':config['suite'], 'env':env,'verify':False}))
with (output/'suite-seed-build.log').open('w') as log:
    subprocess.run(['python3','-I',str(seedversion/'engine.py'),'--build-plan',str(plan)],
                   env=env,user=65534,group=65534,extra_groups=[],stdout=log,stderr=subprocess.STDOUT,check=True)
subprocess.run(['cp','-a',str(suitestage/'usr/local')+'/.',str(prefix)],check=True)
subprocess.run(['python3','/seed-source/image/seed-updater.py','/image',
                '--payload',str(stage),'--payload',str(suitestage/'usr/local')],check=True)
personal=Path('/home/writer/writing/book'); personal.parent.mkdir(parents=True,exist_ok=True)
personal.write_text('a manuscript that must survive')
local=prefix/'share/simplewm/config'; local.write_text(local.read_text()+'\n# personal preference\n')
unknown=prefix/'bin/my-tool'; unknown.write_text('personal tool')
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (personal,local,unknown)}
launcher=hashlib.sha256((prefix/'bin/simpleupdate').read_bytes()).hexdigest()
transport=subprocess.run(['/usr/bin/python3','-I',str(prefix/'bin/simpleupdate'),
                          '--bootstrap-fetch','main/updater/release.json','16384'],
                         user=65534,group=65534,extra_groups=[],capture_output=True,text=True)
if transport.returncode:raise RuntimeError('fixture transport: '+transport.stderr)
def call(label,*args,success=True):
    with (output/(label+'.log')).open('w') as log:
        result=subprocess.run(['/usr/local/bin/simpleupdate',*args],stdout=log,stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL,timeout=900)
    text=(output/(label+'.log')).read_text()
    if (result.returncode==0)!=success:raise RuntimeError(label+': '+text[-10000:])
    return text
text=call('first')
assert 'Authenticated future updater handles this request' in text
assert 'Building and checking SimpleWM' in text
assert json.loads(Path('/var/lib/simpleupdate/ordinary.json').read_text())['updater']==2
assert json.loads(Path('/var/lib/simpleupdate/updater.json').read_text())['active'].startswith('2-')
assert 'simplewm_source_sha='+config['target'] in (prefix/'share/simplewm/install-manifest').read_text()
text=call('repeat')
assert 'Building and checking' not in text
assert hashlib.sha256((prefix/'bin/simpleupdate').read_bytes()).hexdigest()==launcher
for path,digest in before.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
# Offline rollback must not attempt bootstrap networking.
text=call('rollback','--rollback-sources')
assert 'Previous Suite/WM files restored' in text
assert 'simplewm_source_sha='+config['original'] in (prefix/'share/simplewm/install-manifest').read_text()
# A fresh ordinary invocation installs the same authenticated release again.
call('after-rollback')
text=call('rebuild-both','--rebuild')
assert 'Building and checking SimpleSuite' in text and 'Building and checking SimpleWM' in text
# Publish a correctly signed replacement that passes the nobody probe but
# fails before READY. The actual installed launcher must continue with v2.
(output/'published-version').write_text('3')
text=call('failed-replacement','--wm-only')
assert 'restored the previous updater' in text
statefile=Path('/var/lib/simpleupdate/updater.json')
state=json.loads(statefile.read_text()); assert state['active'].startswith('2-') and state['rejected']
call('rejected-repeat','--wm-only')
active=state['active']
state.update(active=state['rejected'][-1],previous=active,pending=True)
statefile.write_text(json.dumps(state))
assert 'activation was interrupted' in call('activation-interrupted','--wm-only')
(output/'bad-signature').touch()
assert 'signature is invalid' in call('bad-signature','--wm-only',success=False)
(output/'bad-signature').unlink()
# Kill a real source installation after its first replacement. Even with the
# HTTPS origin down, the next invocation must replay local recovery first.
payload=prefix/'libexec/simpleupdate/versions'/active
sys.path.insert(0,str(payload)); import transaction as tx
stage=Path('/tmp/interrupted-stage'); (stage/'bin').mkdir(parents=True)
ownership=prefix/'share/simpleupdate/owned.json'; owned=json.loads(ownership.read_text())
for name in ('update-test-a','update-test-b'):
    (prefix/'bin'/name).write_text('old'); (stage/'bin'/name).write_text('new')
    owned['bin/'+name]=tx.fingerprint(prefix/'bin'/name)
tx.write_json(ownership,owned)
script=Path('/tmp/interrupt-source.py')
script.write_text("""import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]); import transaction as tx
replace=os.replace
def cut(source,target):
    replace(source,target)
    if str(source).endswith('/new/bin/update-test-a'):os._exit(91)
os.replace=cut
tx.Transaction(Path('/usr/local')).install([Path('/tmp/interrupted-stage')],lambda:None)
""")
assert subprocess.run(['python3',str(script),str(payload)]).returncode==91
assert (prefix/'bin/update-test-a').read_text()=='new'
(output/'offline').touch()
text=call('offline-recovery','--wm-only',success=False)
assert 'Recovered the interrupted Suite/WM installation' in text
assert all((prefix/'bin'/name).read_text()=='old' for name in ('update-test-a','update-test-b'))
assert not (prefix/'.simpleupdate-ordinary').exists()
(output/'offline').unlink()
commands=[json.loads(line) for line in (output/'commands.jsonl').read_text().splitlines()]
fetches=[c for c in commands if c['command']=='python3' and '--bootstrap-fetch' in c['args']]
builds=[c for c in commands if c['command']=='make' and 'DESTDIR=/seed-payload' not in c['args']]
assert fetches and all(c['uid']==65534 and c['gid']==65534 for c in fetches)
assert builds and all(c['uid']==65534 and c['gid']==65534 for c in builds)
installs=[c for c in commands if c['command']=='apt-get' and 'install' in c['args']]
assert installs and all(c['uid']==0 for c in installs)
for name in ('simplewm','simplewm-lock-client'):
    assert 'not found' not in subprocess.check_output(['ldd',str(prefix/'bin'/name)],text=True)
report={'signed_seed_install':True,'future_updater_delivered':True,'same_request_continued':True,
        'actual_root_nobody':True,'wm_build_real':True,'headless_startup_passed':True,
        'apt_dependencies_real':True,'apt_full_upgrade_simulated':True,'repeat_skips_builds':True,
        'personal_files_preserved':True,'offline_retained_rollback':True,'target':config['target']}
report.update(failed_replacement_fallback=True,interrupted_activation_recovered=True,
              corrupt_signature_refused=True,offline_interrupted_source_recovery=True,
              suite_build_real=True,grouped_rebuild_real=True,image_seed_finalization=True)
(output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('OK real signed installation, future updater delivery, root/nobody build, repeat, personal files and offline rollback',flush=True)
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0: parser.error('root is required for actual root/nobody integration')
    original, work = args.rootfs.resolve(), args.work_dir.resolve()
    if original == Path('/') or work.exists() or work.is_relative_to(original):
        parser.error('use a preserved cached rootfs and a separate NEW work directory')
    if not (original/'usr/local/bin/simplewm').is_file(): parser.error('missing cached ISO payload')
    work.mkdir(mode=0o755, parents=True)
    source=work/'source'; source.mkdir()
    # An isolated repository retains real ancestry and includes pending work,
    # without committing or changing the user's checkout.
    bundle=work/'wm.bundle'; git('-C',REPO,'bundle','create',bundle,'--all')
    git('clone','--quiet',bundle,source); bundle.unlink()
    names=subprocess.check_output(['git','-c','safe.directory=*','-C',str(REPO),'ls-files','-z',
                                   '--cached','--others','--exclude-standard']).decode().split('\0')
    for name in filter(None,names):
        if name.startswith('UPDATER-HANDOFF'): continue
        src=REPO/name; dst=source/name
        if src.is_file():dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
    key=work/'release-private.pem'
    run('openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out',key,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    run('openssl','pkey','-in',key,'-pubout','-out',source/'updater/release-key.pem',stdout=subprocess.DEVNULL)
    git('-C',source,'add','.'); git('-C',source,'commit','--quiet','-m','isolated updater implementation')
    run('python3',source/'updater/release.py','--key',key,'--version','1')
    seed=work/'seed-source'; shutil.copytree(source,seed,ignore=shutil.ignore_patterns('.git','build','__pycache__'))
    (seed/'build').mkdir()
    for name in ('simplewm','simplewm-lock-client'):
        shutil.copy2(original/'usr/local/bin'/name,seed/'build'/name)
    engine=source/'updater/engine.py'
    engine.write_text(engine.read_text().replace('    legacy.main()',
        "    legacy.say('Authenticated future updater handles this request')\n    legacy.main()"))
    git('-C',source,'add','.'); git('-C',source,'commit','--quiet','-m','isolated future updater improvement')
    payload_revision=git('-C',source,'rev-parse','HEAD')
    run('python3',source/'updater/release.py','--key',key,'--version','2')
    git('-C',source,'add','.'); git('-C',source,'commit','--quiet','-m','isolated signed future release')
    target=git('-C',source,'rev-parse','HEAD')
    fixture=work/'http'; fixture.mkdir()
    for name,repo,revision in (('simplewm',source,target),('simplesuite',REPO.parent/'simplesuite',
        dict(line.split('=',1) for line in (original/'usr/local/share/simplesuite/install-manifest').read_text().splitlines())['simplesuite_source_sha'])):
        bundle=work/(name+'.bundle'); git('-C',repo,'bundle','create',bundle,'--all')
        bare=fixture/(name+'.git'); git('clone','--quiet','--bare',bundle,bare); bundle.unlink()
        git('-C',bare,'update-ref','refs/heads/main',revision); git('-C',bare,'symbolic-ref','HEAD','refs/heads/main')
        git('-C',bare,'update-server-info')
    for name in ('release.json','release.sig'):
        dest=fixture/'main/updater'/name; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/'updater'/name,dest)
    spec=importlib.util.spec_from_file_location('test_boot',source/'updater/launcher.py')
    boot=importlib.util.module_from_spec(spec); spec.loader.exec_module(boot)
    for path in boot.FILES.values():
        dest=fixture/payload_revision/path; dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(subprocess.check_output(['git','-c','safe.directory=*','-C',str(source),'show',payload_revision+':'+path]))
    # Keep v2 as the component source while offering v3 only through the
    # independently authenticated updater channel.
    release2=fixture/'releases/2'; release2.mkdir(parents=True)
    for name in ('release.json','release.sig'):shutil.copyfile(source/'updater'/name,release2/name)
    engine.write_text(engine.read_text().replace("    if sys.argv[1:2] == ['--bootstrap-ready-fd']:\n",
        "    if sys.argv[1:2] == ['--bootstrap-ready-fd']:\n        sys.exit('fixture: failed before readiness')\n"))
    git('-C',source,'add','.'); git('-C',source,'commit','--quiet','-m','isolated failed updater replacement')
    revision3=git('-C',source,'rev-parse','HEAD')
    run('python3',source/'updater/release.py','--key',key,'--version','3')
    release3=fixture/'releases/3'; release3.mkdir(parents=True)
    for name in ('release.json','release.sig'):shutil.copyfile(source/'updater'/name,release3/name)
    for path in boot.FILES.values():
        dest=fixture/revision3/path; dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(subprocess.check_output(['git','-c','safe.directory=*','-C',str(source),'show',revision3+':'+path]))
    write(fixture/'repos/kjwat/simplewm',json.dumps({'full_name':'kjwat/simplewm'}))
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path.startswith('/kjwat/simplewm/'):
                self.path = self.path[len('/kjwat/simplewm'):]
            if self.path.startswith('/main/updater/release.'):
                if (output/'offline').exists():
                    self.send_error(503); return
                if self.path.endswith('.sig') and (output/'bad-signature').exists():
                    self.send_response(200); self.end_headers(); self.wfile.write(b'bad signature'); return
                version=(output/'published-version').read_text().strip() if (output/'published-version').exists() else '2'
                self.path='/releases/'+version+'/'+Path(self.path).name
            super().do_GET()
    handler=functools.partial(Handler,directory=str(fixture))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    tls=http.server.ThreadingHTTPServer(('127.0.0.1',443),handler)
    cert=work/'transport.pem'; tlskey=work/'transport-private.pem'
    run('openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=raw.githubusercontent.com',
        '-addext','subjectAltName=DNS:raw.githubusercontent.com,DNS:api.github.com','-keyout',tlskey,'-out',cert,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,tlskey)
    tls.socket=context.wrap_socket(tls.socket,server_side=True)
    for service in (server,tls):threading.Thread(target=service.serve_forever,daemon=True).start()
    root=work/'rootfs'
    print('Copying cached ISO test filesystem; host installation is untouched.',flush=True)
    run('cp','-a','--reflink=auto',original,root)
    # Earlier extraction used group-writable directories. A newly seeded image
    # requires protected system parents; no personal directories are changed.
    for relative in ('usr','usr/local','usr/local/bin','usr/local/share','usr/local/libexec','var','var/lib'):
        path=root/relative; path.mkdir(exist_ok=True); path.chmod(0o755)
    for path in (root/'usr/local').rglob('*'):
        if path.is_dir() and not path.is_symlink():path.chmod(0o755)
    with (root/'etc/ssl/certs/ca-certificates.crt').open('a') as out:out.write(cert.read_text())
    with (root/'etc/hosts').open('a') as out:out.write('\n127.0.0.1 raw.githubusercontent.com api.github.com\n')
    audit=work/'audit'; audit.mkdir()
    output=work/'output'; output.mkdir(); write(output/'commands.jsonl','',0o666)
    old=dict(line.split('=',1) for line in (original/'usr/local/share/simplewm/install-manifest').read_text().splitlines())['simplewm_source_sha']
    suite=dict(line.split('=',1) for line in (original/'usr/local/share/simplesuite/install-manifest').read_text().splitlines())['simplesuite_source_sha']
    write(audit/'config.json',json.dumps({'target':target,'original':old,'suite':suite,
                                       'suite_url':f'http://127.0.0.1:{server.server_address[1]}/simplesuite.git'}))
    write(audit/'guest.py',GUEST)
    shim=SHIM.replace('PORT',str(server.server_address[1]))
    for name in ('git','apt-get','make'):write(root/'usr/local/bin'/name,shim,0o755)
    (root/'usr/bin/python3').unlink(); write(root/'usr/bin/python3',shim,0o755)
    write(root/'usr/sbin/policy-rc.d','#!/bin/sh\nexit 101\n',0o755)
    command=['bwrap','--die-with-parent','--unshare-pid','--unshare-ipc','--unshare-uts',
             '--bind',str(root),'/', '--proc','/proc','--dev','/dev','--tmpfs','/dev/shm','--tmpfs','/run','--tmpfs','/tmp',
             '--bind',str(root),'/image',
             '--ro-bind',str(seed),'/seed-source','--ro-bind',str(audit),'/audit',
             '--bind',str(output),'/audit-output','--ro-bind','/etc/resolv.conf','/etc/resolv.conf','--chdir','/']
    for cap in ('CAP_CHOWN','CAP_DAC_OVERRIDE','CAP_FOWNER','CAP_SETGID','CAP_SETUID','CAP_SYS_CHROOT'):
        command+=['--cap-add',cap]
    command+=['--','/usr/bin/python3','/audit/guest.py']
    try:
        run(*command,timeout=2400,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
        print('Evidence:',output/'result.json',flush=True)
    finally:
        for service in (server,tls):service.shutdown(); service.server_close()
        owner=REPO.stat()
        for path in (output,*output.iterdir()):os.chown(path,owner.st_uid,owner.st_gid)

if __name__=='__main__':main()
