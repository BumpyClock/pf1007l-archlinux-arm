#!/usr/bin/env python3
"""Prepare a new immutable boot profile without writing to a frame or card."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
LIMITS = {'zImage': 16777216, 'initramfs.cpio.gz': 16777216,
          'sun8i-a33-pf1007l-stage1.dtb': 65536}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--dtb', type=Path, required=True)
    storage = parser.add_mutually_exclusive_group(required=True)
    storage.add_argument('--initramfs', type=Path,
                         help='Portable initramfs from the same image/root UUID')
    storage.add_argument('--root-uuid', help='Target UUID from /etc/pf-image-layout.sh')
    parser.add_argument('--root-sectors', type=int, default=8388608,
                        help='PF_ROOT_SECTORS from the target layout; default 4 GiB')
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    args = parser.parse_args()
    if not re.fullmatch(r'arch-usb-[a-z0-9][a-z0-9-]{0,39}', args.profile_id):
        raise ValueError('Invalid profile ID')
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('Use a new output directory')
    paths = {'zImage': args.kernel, 'sun8i-a33-pf1007l-stage1.dtb': args.dtb}
    if args.initramfs:
        paths['initramfs.cpio.gz'] = args.initramfs
    data = {}
    for name, path in paths.items():
        if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= LIMITS[name]:
            raise ValueError('Invalid payload: ' + name)
        data[name] = path.read_bytes()
    if args.root_uuid:
        if str(uuid.UUID(args.root_uuid)) != args.root_uuid or not 1048576 <= args.root_sectors <= 4294434815:
            raise ValueError('Invalid target root UUID or minimum extent')
        sys.path.insert(0, str(REPO / 'image'))
        from build_image import adapt_initrd
        data['initramfs.cpio.gz'], _ = adapt_initrd(args.root_uuid, args.root_sectors)
    if data['zImage'][0x24:0x28] != bytes.fromhex('18286f01'):
        raise ValueError('Kernel is not an ARM zImage')
    if data['sun8i-a33-pf1007l-stage1.dtb'][:4] != bytes.fromhex('d00dfeed'):
        raise ValueError('Invalid flattened device tree')
    initrd = gzip.decompress(data['initramfs.cpio.gz'])
    if b'PF1007L_PUBLIC_ROOT_V1' not in initrd or b'etc/pf-storage-pin' not in initrd:
        raise ValueError('Use the portable initramfs from the target image, not the overlay reference initramfs')
    template = (REPO / 'image/inputs/boot-control.cmd').read_text()
    profiles = set(re.findall(r'(arch-usb-[a-z0-9-]+)/' , template))
    builds = re.findall(r'(?m)^setenv build (working-control-[0-9a-f]{16})$', template)
    if len(profiles) != 1 or len(builds) != 1:
        raise ValueError('Launcher template identity differs')
    original_profile = next(iter(profiles))
    template = template.replace(original_profile + '/', args.profile_id + '/')
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in data.items()}
    build = 'working-control-' + hashlib.sha256((args.profile_id + ''.join(hashes.values())).encode()).hexdigest()[:16]
    template = template.replace(builds[0], build)
    for name, value in data.items():
        original = (REPO / 'image/inputs/boot' / name).read_bytes()
        original_hash = hashlib.sha256(original).hexdigest()
        original_length = f'0x{len(original):x}'
        if original_hash not in template or original_length not in template:
            raise ValueError('Launcher payload contract differs: ' + name)
        template = template.replace(original_hash, hashes[name]).replace(original_length, f'0x{len(value):x}')
    args.output.mkdir(parents=True)
    bundle = args.output / 'bundle'
    bundle.mkdir()
    for name, value in data.items():
        (bundle / name).write_bytes(value)
    source = args.output / 'boot-control.cmd'
    source.write_text(template, newline='\n')
    subprocess.run(['mkimage', '-A', 'arm', '-O', 'linux', '-T', 'script', '-C', 'none',
                    '-n', build, '-d', source, bundle / 'boot-control.scr'], check=True)
    hashes['boot-control.scr'] = hashlib.sha256((bundle / 'boot-control.scr').read_bytes()).hexdigest()
    if (bundle / 'boot-control.scr').stat().st_size > 16384:
        raise ValueError('Launcher exceeds the update protocol limit')
    (bundle / 'SHA256SUMS').write_text(''.join(f'{hashes[name]}  {name}\n' for name in sorted(hashes)), newline='\n')
    receipt = {'profile': args.profile_id, 'build': build, 'payload_sha256': hashes,
               'installed': False, 'selected': False, 'root_storage_uuid_preserved': True}
    (args.output / 'profile.json').write_text(json.dumps(receipt, indent=2) + '\n', newline='\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
