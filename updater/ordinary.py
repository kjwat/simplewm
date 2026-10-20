"""Ordinary maintenance; Debian release migration remains in the legacy engine."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

import transaction

STATE = Path('/var/lib/simpleupdate/ordinary.json')
REBOOT = Path('/run/reboot-required')
PHASES = {'not-started', 'downloading', 'verified', 'staged', 'installing',
          'awaiting-reboot', 'completed', 'failed-recoverable', 'manual-recovery-required'}
BOOTSTRAP_PATHS = ('bin/simpleupdate', 'bin/simpleupdate-target',
                   'share/simpleupdate', 'libexec/simpleupdate')


class RecoveryRequired(RuntimeError):
    pass


def read_state():
    if not STATE.exists():
        return {}
    value = json.loads(STATE.read_text())
    if (not isinstance(value, dict) or value.get('format') != 1
            or value.get('phase') not in PHASES):
        raise RecoveryRequired('Invalid ordinary update record: ' + str(STATE))
    return value


def persist(value, phase, **fields):
    value.update(phase=phase, updated=time.time(), **fields)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    transaction.write_json(STATE, value)


def recover(update):
    """Local recovery runs before any bootstrap or component network request."""
    state = read_state()
    if transaction.Transaction(update.PREFIX).recover():
        update.say('Recovered the interrupted Suite/WM installation')
    if state.get('component') == 'APT' and state.get('phase') in {
            'installing', 'failed-recoverable', 'manual-recovery-required'}:
        audit = update.run(['dpkg', '--audit'], capture_output=True, text=True).stdout.strip()
        if audit:
            persist(state, 'manual-recovery-required', error=audit)
            raise RecoveryRequired('Package installation was interrupted. Run sudo dpkg --configure -a, '
                                   'then sudo apt-get -f install; review their output and rerun simpleupdate. '
                                   'APT packages have not been rolled back.')
        update.say('Package records are consistent; the next update will finish outstanding package work')


def space(path, needed):
    while not path.exists():
        path = path.parent
    if shutil.disk_usage(path).free < needed:
        raise RuntimeError(f'Not enough free space on {path}; need at least {needed // (1024*1024)} MiB')


def requirements(source, version):
    path = source / 'simpleupdate-requirements.json'
    if not path.exists():
        return
    if path.is_symlink() or path.stat().st_size > 16384:
        raise RuntimeError('Invalid component updater requirements')
    value = json.loads(path.read_text())
    if (not isinstance(value, dict) or set(value) != {'format', 'minimum_updater', 'protocol'}
            or value['format'] != 1 or value['protocol'] != 1
            or type(value['minimum_updater']) is not int or value['minimum_updater'] < 1):
        raise RuntimeError('Unsupported component updater requirements')
    if value['minimum_updater'] > version:
        raise RuntimeError('Component needs a newer authenticated updater; no component has been installed')


def source_plan(update, args, work, env, demote, uid, gid, version):
    plans = []
    for component, enabled, origin, manifest, key in (
        ('SimpleSuite', not args.os_only and not args.wm_only, update.OFFICIAL,
         update.MANIFEST, 'simplesuite_source_sha'),
        ('SimpleWM', not args.os_only and not args.suite_only, update.OFFICIAL_WM,
         update.WM_MANIFEST, 'simplewm_source_sha')):
        if not enabled:
            continue
        current = update.installed_revision(manifest, key)
        original = None
        if component == 'SimpleWM':
            if args.wm_local:
                original = args.wm_local.resolve()
            elif not current:
                update.say('SimpleWM is not installed; skipping it')
                continue
            elif not update.wm_repository_exists():
                if not current.startswith('local-'):
                    raise RuntimeError('Previously published SimpleWM repository is unavailable')
                if not args.rebuild:
                    update.say('Bundled SimpleWM is unchanged')
                    continue
                original = update.WM_SOURCE
        source = work / component.lower()
        if original is not None:
            if not (original / 'simplewm.c').is_file() or not (original / 'tests/session-check.py').is_file():
                raise RuntimeError('Expected a complete SimpleWM source folder')
            update.source_digest(original)
            shutil.copytree(original, source,
                            ignore=shutil.ignore_patterns('.git', 'build', 'build-*', '__pycache__'))
            for path in (source, *source.rglob('*')):
                if path.is_symlink():
                    raise RuntimeError('Local SimpleWM source contains a symlink')
                os.chown(path, uid, gid)
            sha = update.source_digest(source)
        else:
            update.say('Checking ' + component)
            sha = update.fetch_source(source, env, demote, origin)
            if not update.published_update_allowed(component, source, sha, current, env, demote):
                continue
        requirements(source, version)
        if sha == current and not args.rebuild:
            update.say(component + ' ' + sha[:12] + ' is current; no build needed')
            continue
        plans.append({'component': component, 'source': str(source), 'sha': sha,
                      'stage': str(work / (component.lower() + '-stage')),
                      'env': dict(env), 'verify': args.verify})
        update.say(component + ': ' + str(current or 'unrecorded') + ' -> ' + sha)
    return plans


def build(update, plan, work, env, demote, uid, gid):
    stage = Path(plan['stage']); stage.mkdir(); os.chown(stage, uid, gid)
    record = work / (plan['component'] + '-plan.json')
    record.write_text(json.dumps(plan)); record.chmod(0o644)
    update.run(['/usr/bin/python3', '-I', str(Path(__file__).with_name('engine.py')),
                '--build-plan', str(record)], env=env, preexec_fn=demote)
    return stage / 'usr/local'


def strip_bootstrap(local):
    for name in BOOTSTRAP_PATHS:
        path = local / name
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()


def run(update, args, log, version):
    # Preserve an interrupted operation's record if its recovery needs repair.
    recover(update)
    update.QUIET = not args.verbose
    state = {'format': 1, 'phase': 'not-started', 'updater': version,
             'request': {key: str(value) if isinstance(value, Path) else value
                         for key, value in vars(args).items()},
             'components': {}, 'apt_rollback': False}
    work = None
    completed = False
    progress = update.Progress()
    update.PROGRESS = progress
    try:
        progress.start()
        progress.step(1, 'Checking system and repositories')
        persist(state, 'not-started')
        space(update.PREFIX, 256 * 1024 * 1024)
        space(Path('/var'), 512 * 1024 * 1024)
        if not args.os_only:
            ownership = transaction.Transaction(update.PREFIX).ownership
            if (ownership.is_symlink() or not ownership.is_file()
                    or not isinstance(json.loads(ownership.read_text()), dict)):
                raise RecoveryRequired('Packaged-file inventory is missing or invalid; source updates require a seeded installation')
        current = update.debian_release()
        changes = update.apt_source_changes(current[1])
        if args.check and changes:
            raise RuntimeError('APT sources need codename pinning; preview with --dry-run, then run simpleupdate to apply it')
        update.write_apt_sources(changes)
        if changes or (not args.suite_only and not args.wm_only):
            update.say('Refreshing Debian ' + current[1] + ' and Liquorix repositories')
            update.refresh_apt()
        update.validate_apt_release(current[1])
        uid, gid = update.build_identity()
        work = Path(tempfile.mkdtemp(prefix='simpleupdate-', dir='/var/tmp'))
        os.chown(work, uid, gid)
        home = work / 'home'; home.mkdir(); os.chown(home, uid, gid)
        env = update.safe_environment(home); demote = update.as_user(uid, gid)
        persist(state, 'downloading', component='sources')
        progress.step(2, 'Checking SimpleSuite and SimpleWM sources')
        plans = source_plan(update, args, work, env, demote, uid, gid, version)
        state['components'] = {p['component']: p['sha'] for p in plans}
        persist(state, 'verified')
        full = not args.suite_only and not args.wm_only
        if args.check:
            if full:
                update.run(['apt-get', '-s', 'full-upgrade'])
            persist(state, 'completed', check_only=True)
            completed = True
            update.say('Update check completed; no packages or source components installed')
            return
        packages = []
        modules = None
        for plan in plans:
            if plan['component'] == 'SimpleSuite':
                packages.extend(update.BUILD_PACKAGES)
            else:
                wm_packages, modules = update.discover_wm_dependencies(Path(plan['source']))
                packages.extend(wm_packages)
        packages = list(dict.fromkeys(packages))
        commands = []
        if full:
            commands.append(['apt-get', '-o', 'Dpkg::Options::=--force-confdef', '-o',
                             'Dpkg::Options::=--force-confold', '-y', 'full-upgrade'])
        if packages:
            commands.append(['apt-get', '-y', '--no-install-recommends', 'install', *packages])
        # APT checks/reserves its own archive space. Download every requested
        # package before beginning non-atomic package installation.
        persist(state, 'downloading', component='APT')
        progress.step(3, 'Downloading packages')
        if commands:
            audit = update.run(['dpkg', '--audit'], capture_output=True, text=True).stdout.strip()
            if audit:
                raise RecoveryRequired('dpkg reports unfinished work; run sudo dpkg --configure -a and sudo apt-get -f install before retrying')
        for command in commands:
            update.run([command[0], '--download-only', *command[1:]])
        progress.step(4, 'Installing Debian packages and build dependencies')
        for command in commands:
            persist(state, 'installing', component='APT')
            update.run(command)
            persist(state, 'verified', component='APT')
        with tempfile.TemporaryDirectory(prefix='simpleupdate-captured-', dir='/var/tmp') as captured:
            stages = []
            managed_paths = set()
            progress.step(5, 'Building and checking programs' if plans else 'Programs are current')
            for index, plan in enumerate(plans):
                if plan['component'] == 'SimpleWM':
                    plan['env']['SIMPLEUPDATE_WM_PKGS'] = ' '.join(update.wm_pkg_config(wm_packages, modules))
                persist(state, 'staged', component=plan['component'])
                progress.label = 'Building and checking ' + plan['component']
                update.say(progress.label)
                stage = build(update, plan, work, env, demote, uid, gid)
                local = Path(captured) / str(index)
                transaction.freeze(stage, local)
                strip_bootstrap(local)
                update.validate_local(local)
                key = plan['component'].lower() + '_source_sha'
                manifest = local / 'share' / plan['component'].lower() / 'install-manifest'
                if update.installed_revision(manifest, key) != plan['sha']:
                    raise RuntimeError('Staged component provenance does not match the requested source')
                managed_paths.update(transaction.inventory(local))
                stages.append(local)
            progress.step(6, 'Backing up and installing programs' if stages else 'No programs to install')
            if stages:
                persist(state, 'installing', component='sources')
                def verify():
                    progress.step(7, 'Verifying installation')
                    for plan in plans:
                        key = plan['component'].lower() + '_source_sha'
                        manifest = update.PREFIX / 'share' / plan['component'].lower() / 'install-manifest'
                        if update.installed_revision(manifest, key) != plan['sha']:
                            raise RuntimeError('Installed component provenance does not match its staged payload')
                transaction.Transaction(update.PREFIX).install(
                    stages, verify, update.say, progress.files, managed_paths=managed_paths)
            else:
                progress.step(7, 'Finishing update')
        reboot = REBOOT.exists()
        persist(state, 'awaiting-reboot' if reboot else 'completed', component='all', reboot_required=reboot)
        completed = True
        update.say('Update completed' + ('; reboot required' if reboot else ''))
        if any(plan['component'] == 'SimpleWM' for plan in plans):
            update.say('SimpleWM passed an isolated startup check; use it at your next login. '
                       'Previous source files are retained: simpleupdate --rollback-sources')
    except BaseException as error:
        persist(state, 'manual-recovery-required' if isinstance(error, RecoveryRequired) else 'failed-recoverable',
                error=str(error))
        raise
    finally:
        progress.close(success=completed)
        update.PROGRESS = None
        update.QUIET = False
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


def healthcheck(binary, config, work, env, demote):
    """A short real startup probe; no personal config, hardware, or desktop services."""
    runtime = work / 'startup-check'; runtime.mkdir(mode=0o700)
    owner = work.stat(); os.chown(runtime, owner.st_uid, owner.st_gid)
    probe_config = runtime / 'config'
    probe_config.write_text('background none\n'); os.chown(probe_config, owner.st_uid, owner.st_gid)
    log = runtime / 'startup.log'
    with log.open('w') as output:
        process = subprocess.Popen([str(binary), '-c', str(probe_config)], stdout=output, stderr=output,
            env=env | {'XDG_RUNTIME_DIR':str(runtime),'WLR_BACKENDS':'headless','WLR_HEADLESS_OUTPUTS':'1',
                       'WLR_RENDERER':'pixman','WLR_LIBINPUT_NO_DEVICES':'1'}, preexec_fn=demote)
        try:
            until = time.monotonic()+10
            while time.monotonic()<until:
                if process.poll() is not None:
                    raise RuntimeError('SimpleWM failed its isolated startup check: '+log.read_text()[-1200:])
                endpoint = next(runtime.glob('simplewm-*.ctl'), None)
                if endpoint:
                    with socket.socket(socket.AF_UNIX) as peer:
                        peer.settimeout(3)
                        peer.connect(str(endpoint))
                        peer.sendall(b'status\n')
                        output = b''
                        while chunk := peer.recv(65536):
                            output += chunk
                            if len(output) > 1024 * 1024:
                                raise RuntimeError('Invalid compositor startup response')
                        if json.loads(output).get('outputs'):
                            return
                time.sleep(0.05)
            raise RuntimeError('SimpleWM did not initialize a headless output within ten seconds; '
                               'working compositor retained. ' + log.read_text()[-1200:])
        finally:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
