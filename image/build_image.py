#!/usr/bin/env python3
"""Build a fresh, credential-free image from a root tree or private snapshot seeds."""

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import uuid

from newc import members, entry
from audit_packages import audit

HERE = Path(__file__).resolve().parent
FAT_START = 8192
FAT_SECTORS = 524288
ROOT_START = FAT_START + FAT_SECTORS
BASE_SHA = 'bffb160014def7324560889539369cf1b29a67d06a7204c49be0d765084191ca'
LOADER_SHA = '13784fc9960ce4de553ca166432b17b78116ecff23e9a8bdeaa09596eb1560a6'
PINS = {
    'zImage': 'abd477f74589516357511e00354246f588898b2c40e191c40a1acee7bd3ac186',
    'initramfs.cpio.gz': '15728d2cb68511bb67f8968a6321e12af3e303afb16103f9fefc8213a18eebf7',
    'sun8i-a33-pf1007l-stage1.dtb': 'e3a644f7024bfaf38a057d818f01943140b61191f2fa4b88cc95971c4dc5b808',
}


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require_hash(path, expected):
    regular(path)
    if file_hash(path) != expected:
        raise ValueError(f'Qualified input changed: {path.name}')


def regular(path):
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('A regular input file is required')


def new_file(path, size):
    with path.open('xb') as stream:
        stream.truncate(size)


@contextmanager
def mounted(image, target, readonly=False):
    regular(image)
    target.mkdir()
    run('mount', '-o', 'loop,ro,noload' if readonly else 'loop,rw', image, target)
    try:
        yield target
    finally:
        run('umount', target)


def merge(base, state, work):
    require_hash(base, BASE_SHA)
    regular(state)
    if state.stat().st_size != 512 * 1024 ** 2:
        raise ValueError('Consistent state seed must be 512 MiB')
    root = work / 'root-tree'
    root.mkdir(mode=0o700)
    with mounted(base, work / 'base-mount', True) as lower:
        with mounted(state, work / 'state-mount', True) as upper:
            if (upper / 'base-image.sha256').read_text().strip() != BASE_SHA:
                raise ValueError('State does not belong to the base seed')
            merged = work / 'merged-mount'
            merged.mkdir()
            run('mount', '-t', 'overlay', '-o', f'ro,lowerdir={upper}/upper:{lower}', 'overlay', merged)
            try:
                producer = subprocess.Popen(['tar', '--acls', '--xattrs', '--numeric-owner',
                    '--one-file-system', '--exclude=./dev/*', '--exclude=./proc/*',
                    '--exclude=./sys/*', '--exclude=./run/*', '-cpf', '-', '-C', str(merged), '.'], stdout=subprocess.PIPE)
                result = subprocess.run(['tar', '--acls', '--xattrs', '--numeric-owner', '-xpf', '-', '-C', str(root)], stdin=producer.stdout)
                producer.stdout.close()
                if producer.wait() or result.returncode:
                    raise ValueError('Read-only merged export failed')
            finally:
                run('umount', merged)
    return root


def remove(root, relative):
    path = root / relative
    if not path.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError('Sanitization path escapes scratch root')
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def write(root, relative, data, mode=0o644):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError('Installed path escapes scratch root')
    if path.is_symlink():
        path.unlink()
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    path.chmod(mode)
    os.chown(path, 0, 0)


def copy_overlay(source, root):
    if not source.is_dir():
        raise ValueError(f'Required root overlay missing: {source.name}')
    run('cp', '-a', str(source) + '/.', root)
    for path in source.rglob('*'):
        if path.is_file() and not path.is_symlink():
            relative = path.relative_to(source)
            target = root / relative
            target.chmod(0o755 if relative.parts[:3] == ('usr', 'local', 'sbin') else 0o644)
            os.chown(target, 0, 0)


def sanitize(root):
    for relative in ['root', 'home', 'var/log', 'var/cache', 'var/tmp', 'tmp', 'var/spool',
            'etc/pacman.d/gnupg', 'etc/NetworkManager/system-connections', 'etc/iwd',
            'etc/netctl', 'etc/wpa_supplicant', 'etc/systemd/network', 'etc/dhcpcd.duid',
            'etc/dhcpcd.secret', 'etc/adjtime', 'etc/machine-info', 'etc/hostid',
            'etc/pf-direct-root', 'etc/pf-image-layout.json', 'etc/pf-image-layout.sh',
            'etc/shadow-', 'etc/gshadow-', 'etc/passwd-', 'etc/group-', 'etc/subuid-', 'etc/subgid-',
            'README.md', 'test_bringup.py', 'host-rootfs']:
        remove(root, relative)
    for path in list((root / 'var/lib').iterdir()):
        if path.name != 'pacman':
            remove(root, str(path.relative_to(root)))
    for path in (root / 'etc/ssh').glob('ssh_host_*'):
        remove(root, str(path.relative_to(root)))
    for directory in ['root', 'home/diag/pf-update', 'var/log', 'var/cache', 'var/tmp', 'tmp', 'var/lib/pf-wifi', 'var/lib/pf-firstboot']:
        path = root / directory
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700 if directory in ('root', 'var/lib/pf-wifi', 'var/lib/pf-firstboot') else 0o755)
    (root / 'tmp').chmod(0o1777)
    (root / 'var/tmp').chmod(0o1777)
    passwd = []
    for line in (root / 'etc/passwd').read_text().splitlines():
        fields = line.split(':')
        if fields[0] == 'root' or int(fields[2]) >= 1000:
            fields[4] = ''
        passwd.append(':'.join(fields))
    write(root, 'etc/passwd', '\n'.join(passwd) + '\n')
    for directory in ('etc', 'var'):
        for path in list((root / directory).rglob('*')):
            if path.is_file() and path.name.endswith(('.pacsave', '.pacnew', '.bak', '~')):
                remove(root, str(path.relative_to(root)))
    for name in ('shadow', 'gshadow'):
        lines = []
        for line in (root / 'etc' / name).read_text().splitlines():
            fields = line.split(':')
            fields[1] = '!'
            lines.append(':'.join(fields))
        write(root, 'etc/' + name, '\n'.join(lines) + '\n', 0o600)
    diag = next(line.split(':') for line in passwd if line.startswith('diag:'))
    for path in (root / 'home/diag', root / 'home/diag/pf-update'):
        os.chown(path, int(diag[2]), int(diag[3]))
    write(root, 'etc/hostname', 'pf1007l-arch\n')
    write(root, 'etc/machine-id', '')
    write(root, 'etc/hosts', '127.0.0.1 localhost\n::1 localhost\n')
    write(root, 'etc/issue', 'PF1007L Arch Linux ARM; USB serial at 115200 8N1.\n')
    write(root, 'etc/motd', 'PF1007L Arch Linux ARM. Changes persist on the SD ext4 root filesystem.\n')
    for path in list((root / 'etc/systemd/system').rglob('*')):
        if path.is_symlink() and (path.name.startswith(('pf-wifi', 'sshd', 'dhcpcd', 'wpa_supplicant', 'iwd')) or 'autologin' in path.name):
            path.unlink()
    for name in ('sshd.service', 'sshd.socket', 'sshd@.service'):
        path = root / 'etc/systemd/system' / name
        if path.exists() or path.is_symlink():
            remove(root, str(path.relative_to(root)))
        path.symlink_to('/dev/null')
    remove(root, 'etc/resolv.conf')
    (root / 'etc/resolv.conf').symlink_to('/run/systemd/resolve/stub-resolv.conf')
    for directory in ('dev', 'proc', 'sys', 'run'):
        path = root / directory
        if not path.is_dir() or path.is_symlink() or any(path.iterdir()):
            raise ValueError('Runtime directory is not empty')


def adapt_helpers(root, root_uuid, root_sectors):
    replacements = {'@ROOT_UUID@': root_uuid, '@FAT_SECTORS@': str(FAT_SECTORS),
                    '@ROOT_START@': str(ROOT_START), '@ROOT_SECTORS@': str(root_sectors)}
    guard = (HERE / 'portable-root-guard.sh.in').read_text()
    for old, new in replacements.items():
        guard = guard.replace(old, new)
    write(root, 'usr/local/lib/pf-direct-root.sh', guard)
    console = (root / 'usr/local/sbin/pf-console-boot').read_text()
    begin = console.index('    [[ $(findmnt -n -o FSTYPE -T /) == overlay ]]')
    end = console.index('    [[ $(findmnt -n -o TARGET -T "$PF_SD")', begin)
    console = (console[:begin] + '    pf_require_direct_root || return 1\n' + console[end:]).replace('PF_PERSIST=/run/pf-arch/state\n', '').replace('    local source options backing\n', '')
    console = console.replace('umask 077\n', 'umask 077\n. /usr/local/lib/pf-direct-root.sh\n', 1)
    console = console.replace('    if (( wifi_ready )); then pf_network || result=1; fi',
        '    if (( wifi_ready )) && [[ -f /var/lib/pf-firstboot/complete && -f /var/lib/pf-wifi/wpa_supplicant.conf ]]; then pf_network || result=1; fi')
    write(root, 'usr/local/sbin/pf-console-boot', console, 0o755)
    maintenance = (HERE / 'inputs/pf-maintenance').read_text()
    begin = maintenance.index('require_sd() {\n')
    end = maintenance.index('\n}\n', begin) + 3
    maintenance = maintenance[:begin] + 'require_sd() {\n    pf_require_direct_root || fail "portable SD root identity differs"\n}\n' + maintenance[end:]
    begin = maintenance.index('require_persistence() {\n')
    end = maintenance.index('\n}\n', begin) + 3
    maintenance = maintenance[:begin] + 'require_persistence() {\n    pf_require_direct_root || fail "portable ext4 root identity differs"\n}\n' + maintenance[end:]
    maintenance = maintenance.replace('umask 077\n', 'umask 077\n. /usr/local/lib/pf-direct-root.sh\n', 1).replace('for target in / "$SD" /run/pf-arch/state;', 'for target in / "$SD";')
    write(root, 'usr/local/sbin/pf-maintenance', maintenance, 0o755)
    marker = f'PF1007L_PUBLIC_ROOT_V1 uuid={root_uuid}\n'
    write(root, 'etc/pf-direct-root', marker)
    write(root, 'etc/pf-arch-image-id', root_uuid + '\n')
    write(root, 'etc/fstab', f'UUID={root_uuid} / ext4 defaults,noatime 0 0\n')
    write(root, 'etc/pf-image-layout.json', json.dumps({'root_uuid': root_uuid, 'fat_sectors': FAT_SECTORS, 'root_start': ROOT_START, 'root_sectors': root_sectors}) + '\n')
    write(root, 'etc/pf-image-layout.sh', f'PF_FAT_SECTORS={FAT_SECTORS}\nPF_ROOT_START={ROOT_START}\nPF_ROOT_SECTORS={root_sectors}\n')
    write(root, 'usr/local/sbin/pf-grow-root', (HERE / 'pf-grow-root').read_bytes(), 0o755)
    write(root, 'usr/local/sbin/pf-standard-power-check', (HERE / 'pf-standard-power-check').read_bytes(), 0o755)
    write(root, 'etc/systemd/system/pf-grow-root.service', (HERE / 'pf-grow-root.service').read_bytes())
    growth_link = root / 'etc/systemd/system/multi-user.target.wants/pf-grow-root.service'
    if growth_link.is_symlink():
        growth_link.unlink()
    growth_link.symlink_to('../pf-grow-root.service')


def adapt_initrd(root_uuid, root_sectors):
    source = HERE / 'inputs/boot/initramfs.cpio.gz'
    require_hash(source, PINS[source.name])
    records = list(members(gzip.decompress(source.read_bytes())))
    names = [name for name, _, _, _ in records]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate initramfs members')
    original = next(body.decode() for name, _, body, _ in records if name == 'init')
    begin = original.index('image="$PF_MOUNT/arch-gpu-r2/arch-rootfs.ext4"\n')
    end = original.index('stage diagnostic-mask-start\n', begin)
    init = original[:begin] + (HERE / 'direct-root-init.fragment').read_text() + original[end:]
    init = init.replace('. /etc/pf-image-pin\n', '. /etc/pf-storage-pin\n')
    pin = f'PF_ROOT_UUID={root_uuid}\nPF_FAT_SECTORS={FAT_SECTORS}\nPF_ROOT_START={ROOT_START}\nPF_ROOT_SECTORS={root_sectors}\n'.encode()
    output = bytearray()
    for name, fields, body, raw in records:
        if name == 'init':
            output.extend(entry(name, fields, init.encode()))
        elif name == 'etc/pf-image-pin':
            output.extend(entry('etc/pf-storage-pin', fields, pin))
        else:
            output.extend(raw)
    output.extend(b'\0' * (-len(output) % 512))
    return gzip.compress(output, compresslevel=9, mtime=0), init


def mk_script(source, destination, title):
    run('mkimage', '-A', 'arm', '-O', 'linux', '-T', 'script', '-C', 'none', '-n', title, '-d', source, destination)


def prepare_boot(work, root_uuid, root_sectors):
    fat = work / 'fat-tree'
    bundle = fat / 'arch-usb-factory-r1'
    bundle.mkdir(parents=True)
    for name in ('zImage', 'sun8i-a33-pf1007l-stage1.dtb'):
        require_hash(HERE / 'inputs/boot' / name, PINS[name])
        shutil.copyfile(HERE / 'inputs/boot' / name, bundle / name)
    initrd, init = adapt_initrd(root_uuid, root_sectors)
    (bundle / 'initramfs.cpio.gz').write_bytes(initrd)
    (work / 'init').write_text(init)
    build = 'working-control-' + hashlib.sha256(initrd + (bundle / 'zImage').read_bytes() + (bundle / 'sun8i-a33-pf1007l-stage1.dtb').read_bytes()).hexdigest()[:16]
    launcher = (HERE / 'inputs/boot-control.cmd').read_text()
    launcher = launcher.replace('arch-usb-wifi-upstream-r1/', 'arch-usb-factory-r1/').replace('working-control-1f8aa3b15359f8ec', build)
    launcher = launcher.replace(PINS['initramfs.cpio.gz'], hashlib.sha256(initrd).hexdigest()).replace('0xe2639', f'0x{len(initrd):x}')
    if 'arch-usb-wifi-upstream-r1/' in launcher or PINS['initramfs.cpio.gz'] in launcher:
        raise ValueError('Factory launcher adaptation failed')
    (work / 'factory.cmd').write_text(launcher)
    mk_script(work / 'factory.cmd', bundle / 'boot-control.scr', build)
    sums = {path.name: file_hash(path) for path in bundle.iterdir()}
    (bundle / 'SHA256SUMS').write_text(''.join(f'{sums[name]}  {name}\n' for name in sorted(sums)))
    (fat / 'boot-maint').mkdir()
    shutil.copyfile(bundle / 'boot-control.scr', fat / 'boot-maint/recovery.scr')
    recovery_sha = sums['boot-control.scr']
    recovery_bytes = (bundle / 'boot-control.scr').stat().st_size
    dispatcher = (HERE / 'inputs/dispatcher.cmd').read_text().replace('75f31b3a64dc6b84e28e94af89995820b1958b29497ed53266637b19cf7b14a4', recovery_sha).replace('0x1f56', f'0x{recovery_bytes:x}')
    (work / 'dispatcher.cmd').write_text(dispatcher)
    mk_script(work / 'dispatcher.cmd', fat / 'boot-control.scr', 'PF1007L portable dispatcher')
    (fat / 'boot-maint/trial.env').write_text(f'pf_trial_dir=arch-usb-factory-r1\npf_trial_build={build}\npf_trial_script_sha={recovery_sha}\npf_trial_script_size={recovery_bytes:x}\n')
    (fat / 'boot-maint/trial-state.bin').write_bytes(b'\xa5')
    (fat / 'linux-sd/logs').mkdir(parents=True)
    (fat / 'linux-sd/logging.marker').write_text('PF1007L_SD_LOG_V1\nstart=8192\n')
    (fat / 'linux-sd/direct-root.marker').write_text(f'PF1007L_PUBLIC_ROOT_V1 uuid={root_uuid}\n')
    return fat, bundle, build


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result[relative] = {'symlink': os.readlink(path)}
        elif path.is_file():
            result[relative] = {'bytes': path.stat().st_size, 'sha256': file_hash(path), 'mode': oct(stat.S_IMODE(path.stat().st_mode))}
    return result


def validate_executables(root):
    checked = 0
    for path in (root / 'usr/bin').iterdir():
        if path.is_symlink() or not path.is_file() or not path.stat().st_mode & 0o111:
            continue
        with path.open('rb') as stream:
            head = stream.read(64)
        if head.startswith(b'\x7fELF'):
            if len(head) < 20 or head[4:6] != b'\x01\x01' or struct.unpack_from('<H', head, 18)[0] != 40:
                raise ValueError(f'Executable is not ARM 32-bit little-endian ELF: {path.name}')
        elif not head.startswith(b'#!'):
            raise ValueError(f'Executable has invalid contents: {path.name}')
        checked += 1
    for path in (root / 'usr/include').rglob('*.h'):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                if stream.read(4).startswith((b'\x1f\x8b', b'\x28\xb5\x2f\xfd', b'PK\x03\x04')):
                    raise ValueError(f'C header has compressed contents: {path.name}')
    return checked


def region_hash(path, offset, length):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        stream.seek(offset)
        remaining = length
        while remaining:
            data = stream.read(min(8 * 1024 ** 2, remaining))
            if not data:
                raise ValueError('Assembled partition is truncated')
            sha.update(data)
            remaining -= len(data)
    return sha.hexdigest()


def build(args):
    if os.geteuid() != 0:
        raise ValueError('Run on Linux as root. Only newly created regular files are formatted.')
    work, output, repo = args.work.resolve(), args.output.resolve(), args.repo.resolve()
    if work.exists() or output.exists():
        raise ValueError('Work and output directories must be new')
    if work.is_relative_to(output) or output.is_relative_to(work):
        raise ValueError('Work and output must be separate directories')
    if args.root_tree and (work.is_relative_to(args.root_tree.resolve()) or output.is_relative_to(args.root_tree.resolve())):
        raise ValueError('Generated directories must be outside the root input tree')
    choices = bool(args.base or args.state) + bool(args.root_tree) + bool(args.root_archive)
    if choices != 1 or bool(args.base) != bool(args.state):
        raise ValueError('Choose one root input mode; private seeds require both --base and --state')
    if args.root_mib < 64 or ROOT_START + args.root_mib * 2048 > 4294967295:
        raise ValueError('Root size does not fit the DOS partition layout')
    for command in ('mkfs.vfat', 'mkfs.ext4', 'mount', 'umount', 'mkimage', 'dd', 'e2fsck', 'sfdisk', 'xz'):
        if not shutil.which(command):
            raise ValueError(f'Required tool unavailable: {command}')
    work.mkdir(parents=True, mode=0o700)
    output.mkdir(parents=True)
    if args.base and args.state:
        root = merge(args.base.resolve(), args.state.resolve(), work)
    elif args.root_tree:
        root = work / 'root-tree'
        root.mkdir(mode=0o700)
        run('cp', '-a', str(args.root_tree.resolve()) + '/.', root)
    elif args.root_archive:
        root = work / 'root-tree'
        root.mkdir(mode=0o700)
        run('tar', '--acls', '--xattrs', '--numeric-owner', '-xpf', args.root_archive.resolve(), '-C', root)
    else:
        raise ValueError('Supply --root-tree, --root-archive, or both private --base and --state')
    sanitize(root)
    copy_overlay(repo / 'reference/qualified-overlay/root-overlay', root)
    copy_overlay(repo / 'firstboot/root-overlay', root)
    firstboot = json.loads((repo / 'firstboot/install-manifest.json').read_text())
    for record in firstboot['files']:
        require_hash(root / record['path'], record['sha256'])
    wants = root / 'etc/systemd/system/multi-user.target.wants'
    wants.mkdir(parents=True, exist_ok=True)
    for name in ('pf-init-keyring.service', 'systemd-resolved.service'):
        path = wants / name
        if not path.is_symlink():
            path.symlink_to('/usr/lib/systemd/system/' + name if name == 'systemd-resolved.service' else '../' + name)
    root_uuid = str(uuid.uuid4())
    root_sectors = args.root_mib * 2048
    adapt_helpers(root, root_uuid, root_sectors)
    executable_count = validate_executables(root)
    package_audit = audit(root)
    (output / 'package-integrity.json').write_text(json.dumps(package_audit, indent=2) + '\n')
    if package_audit['unexpected']:
        raise ValueError('Installed package contents failed mtree checks; inspect package-integrity.json')
    for command in ('usr/bin/partx', 'usr/bin/resize2fs', 'usr/bin/bash', 'usr/bin/agetty', 'usr/bin/pacman-key', 'usr/local/sbin/pf-console-login'):
        if not (root / command).exists():
            raise ValueError(f'Required image command missing: {command}')
    if os.readlink(root / 'etc/resolv.conf') != '/run/systemd/resolve/stub-resolv.conf' or not (root / 'etc/systemd/system/multi-user.target.wants/systemd-resolved.service').is_symlink():
        raise ValueError('DNS stub and resolver service are not connected')
    if any('--autologin' in path.read_text(errors='ignore') for path in (root / 'etc/systemd/system').rglob('*.conf') if path.is_file()):
        raise ValueError('Autologin remains in factory image')
    fat, bundle, build_id = prepare_boot(work, root_uuid, root_sectors)
    root_manifest = inventory(root)
    (output / 'root-file-manifest.json').write_text(json.dumps(root_manifest, indent=2) + '\n')
    package_list = sorted(path.name for path in (root / 'var/lib/pacman/local').iterdir() if path.is_dir())
    (output / 'installed-packages.txt').write_text('\n'.join(package_list) + '\n')
    archive = output / 'pf1007l-sanitized-root.tar.xz'
    run('tar', '--acls', '--xattrs', '--numeric-owner', '--use-compress-program=xz -T2 -3', '-cpf', archive, '-C', root, '.')
    fat_image, root_image = work / 'boot.fat', work / 'root.ext4'
    new_file(fat_image, FAT_SECTORS * 512)
    new_file(root_image, root_sectors * 512)
    run('mkfs.vfat', '-F', '32', '-n', 'A33BACKUP', fat_image)
    run('mkfs.ext4', '-q', '-F', '-L', 'PFROOT', '-U', root_uuid, '-m', '1', '-E', 'lazy_itable_init=0,lazy_journal_init=0', root_image)
    with mounted(root_image, work / 'root-mount') as destination:
        run('cp', '-a', '-x', '--reflink=never', str(root) + '/.', destination)
        run('sync', '-f', destination)
    run('e2fsck', '-fn', root_image)
    with mounted(fat_image, work / 'boot-mount') as destination:
        run('cp', '-r', str(fat) + '/.', destination)
        run('sync', '-f', destination)
    image = output / 'pf1007l-archlinux-arm.img'
    new_file(image, (ROOT_START + root_sectors) * 512)
    table = bytearray(512)
    for n, (kind, start, sectors) in enumerate(((12, FAT_START, FAT_SECTORS), (131, ROOT_START, root_sectors))):
        table[446 + n * 16:462 + n * 16] = struct.pack('<B3sB3sII', 0, b'\xfe\xff\xff', kind, b'\xfe\xff\xff', start, sectors)
    table[510:] = b'\x55\xaa'
    loader = HERE / 'inputs/u-boot-sunxi-with-spl.bin'
    require_hash(loader, LOADER_SHA)
    with image.open('r+b') as stream:
        stream.write(table)
        stream.seek(8192)
        stream.write(loader.read_bytes())
    for source, start in ((fat_image, FAT_START), (root_image, ROOT_START)):
        run('dd', f'if={source}', f'of={image}', 'bs=4M', f'seek={start // 8192}', 'iflag=fullblock', 'conv=notrunc,sparse,fsync', 'status=none')
    partition_pins = {}
    for name, source, start in (('boot', fat_image, FAT_START), ('root', root_image, ROOT_START)):
        expected = file_hash(source)
        actual = region_hash(image, start * 512, source.stat().st_size)
        if actual != expected:
            raise ValueError('Assembled partition differs from checked filesystem source')
        partition_pins[name] = {'sha256': actual, 'bytes': source.stat().st_size, 'offset': start * 512}
    run('sfdisk', '--verify', image)
    with image.open('rb') as stream:
        stream.seek(8192)
        if stream.read(loader.stat().st_size) != loader.read_bytes():
            raise ValueError('SPL payload changed during assembly')
    with mounted(root_image, work / 'inspect-root', True) as inspected:
        if inventory(inspected) != root_manifest:
            raise ValueError('Installed root differs from sanitized file manifest')
        if (inspected / 'var/lib/pf-firstboot/complete').exists():
            raise ValueError('Factory image was provisioned')
    run('xz', '-T2', '-3', '-k', image)
    run('xz', '-t', str(image) + '.xz')
    shutil.copytree(bundle, output / 'portable-profile')
    receipt = {'status': 'HOST_VERIFIED_NOT_HARDWARE_BOOTED', 'distribution_status': 'DRAFT_VENDOR_PAYLOAD_REVIEW_REQUIRED',
        'profile': 'arch-usb-factory-r1', 'build': build_id, 'kernel': '7.2.10-pf-console-r1', 'root_uuid': root_uuid,
        'fat_start': FAT_START, 'fat_sectors': FAT_SECTORS, 'root_start': ROOT_START, 'root_sectors': root_sectors,
        'image_bytes': image.stat().st_size, 'firstboot_grows_last_root_partition': True,
        'USB_serial_preserved': True, 'factory_passwords_locked': True, 'saved_networks': 0, 'ssh_disabled': True,
        'private_filesystem_blocks_copied': False, 'file_manifest_verified_readonly': True,
        'ARM_ELF_or_script_executables_validated': executable_count,
        'packaged_content_audit': package_audit['status'],
        'packaged_files_checked': package_audit['packaged_files_checked'],
        'assembled_partition_hashes': partition_pins,
        'checks': ['e2fsck -fn', 'sfdisk --verify', 'SPL payload readback', 'assembled partition hashes', 'readonly root file inventory', 'xz -t'],
        'files': {path.name: {'bytes': path.stat().st_size, 'sha256': file_hash(path)} for path in (image, Path(str(image) + '.xz'), archive)}}
    (output / 'image-manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=HERE.parent)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--root-tree', type=Path)
    parser.add_argument('--root-archive', type=Path)
    parser.add_argument('--root-mib', type=int, default=4096)
    build(parser.parse_args())
