"""Repair only a new root tree using signed packages of the same installed versions."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

from build_image import file_hash, run

PACKAGES = [('glmark2', '2023.01-2'), ('libjpeg-turbo', '3.2.0-2'), ('tpm2-tss', '4.2.0-2')]
SIGNER = '68B3537F39A313B3E574D06777193F152BDBE6A6'


def repair(source, packages, output):
    if os.geteuid() != 0 or output.exists() or output.resolve().is_relative_to(source.resolve()):
        raise ValueError('Linux root and a new output tree outside the source are required')
    output.mkdir(parents=True, mode=0o700)
    run('cp', '-a', '--reflink=auto', str(source) + '/.', output)
    home = packages / 'repair-gpg-home'
    home.mkdir(mode=0o700, exist_ok=True)
    ring = packages / 'repair-keyring.gpg'
    if not ring.exists():
        run('gpg', '--batch', '--homedir', home, '--dearmor', '--output', ring,
            source / 'usr/share/pacman/keyrings/archlinuxarm.gpg')
    receipts = []
    for name, version in PACKAGES:
        archive = packages / f'{name}-{version}-armv7h.pkg.tar.xz'
        signature = Path(str(archive) + '.sig')
        result = subprocess.run(['gpgv', '--homedir', str(home), '--keyring', str(ring),
            '--status-fd=1', str(signature), str(archive)], check=True, capture_output=True, text=True)
        if not any(line.startswith('[GNUPG:] VALIDSIG ' + SIGNER + ' ') for line in result.stdout.splitlines()):
            raise ValueError('Package signature was not made by the expected Arch Linux ARM build key')
        local = output / 'var/lib/pacman/local' / (name + '-' + version)
        if not local.is_dir():
            raise ValueError('Installed package version differs from the repair input')
        with tarfile.open(archive, 'r:xz') as tar:
            entries = {member.name.removeprefix('./'): member for member in tar.getmembers()}
            for path in entries:
                parts = PurePosixPath(path)
                if parts.is_absolute() or '..' in parts.parts:
                    raise ValueError('Invalid signed package member path')
            info = tar.extractfile(entries['.PKGINFO']).read().decode()
            if f'pkgname = {name}\n' not in info or f'pkgver = {version}\n' not in info or 'arch = armv7h\n' not in info:
                raise ValueError('Signed package identity differs')
            mtree = tar.extractfile(entries['.MTREE']).read()
            install = tar.extractfile(entries['.INSTALL']).read() if '.INSTALL' in entries else None
        run('tar', '--acls', '--xattrs', '--numeric-owner', '-xpf', archive, '-C', output,
            '--exclude=.PKGINFO', '--exclude=.BUILDINFO', '--exclude=.MTREE', '--exclude=.INSTALL')
        (local / 'mtree').write_bytes(mtree)
        if install is not None:
            (local / 'install').write_bytes(install)
        receipts.append({'package': name, 'version': version, 'architecture': 'armv7h',
            'archive_sha256': file_hash(archive), 'signature_sha256': file_hash(signature),
            'signature_verified': True, 'signer': SIGNER, 'complete_package_payload_replaced': True})
    return {'result': 'SIGNED_PACKAGE_REPAIR_COMPLETE', 'source_modified': False, 'packages': receipts,
            'device_modified': False, 'cause_of_original_content_error': 'UNPROVEN'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--packages', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    receipt = repair(args.source.resolve(), args.packages.resolve(), args.output.resolve())
    args.report.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
