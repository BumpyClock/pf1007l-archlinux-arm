"""Verify release asset hashes and the decompressed image without mounting it."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(folder):
    manifest = json.loads((folder / 'image-manifest.json').read_text())
    if manifest['status'] != 'HOST_VERIFIED_NOT_HARDWARE_BOOTED' or manifest.get('packaged_content_audit') != 'PACKAGED_CONTENT_CHECKS_PASS':
        raise ValueError('This export did not pass the required image and package checks')
    for name, record in manifest['files'].items():
        if Path(name).name != name:
            raise ValueError('Manifest filename is not a basename')
        path = folder / name
        if not path.exists() and name.endswith('.img'):
            continue
        if path.is_symlink() or path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            raise ValueError(f'Asset differs: {name}')
    compressed = folder / 'pf1007l-archlinux-arm.img.xz'
    subprocess.run(['xz', '-t', compressed], check=True)
    process = subprocess.Popen(['xz', '-dc', compressed], stdout=subprocess.PIPE)
    try:
        actual = hashlib.file_digest(process.stdout, 'sha256').hexdigest()
    finally:
        process.stdout.close()
    if process.wait() != 0 or actual != manifest['files']['pf1007l-archlinux-arm.img']['sha256']:
        raise ValueError('Decompressed image differs from raw image hash')
    return {'result': 'PASS', 'all_asset_hashes_verified': True, 'compressed_image_matches_raw_sha256': True,
            'image_status': manifest['status'], 'hardware_boot_tested': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.dist), indent=2))
