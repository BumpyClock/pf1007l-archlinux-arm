"""Verify release asset hashes and the decompressed image without mounting it."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def verify_archive_metadata(archive, inventory):
    checked = set()
    with tarfile.open(archive, 'r:xz') as stream:
        for member in stream:
            name = member.name.removeprefix('./').rstrip('/') or '.'
            if name in checked or name not in inventory:
                raise ValueError('Archive has unexpected or duplicate filesystem entries')
            checked.add(name)
            expected = inventory[name]
            kind = ('directory' if member.isdir() else 'symlink' if member.issym()
                    else 'file' if member.isfile() or member.islnk() else None)
            if (kind, member.uid, member.gid, oct(member.mode)) != (
                    expected['type'], expected['uid'], expected['gid'], expected['mode']):
                raise ValueError('Archive ownership or permissions differ from filesystem inventory')
            if member.uname or member.gname or any(key in member.pax_headers for key in ('atime', 'ctime')):
                raise ValueError('Archive exposes owner names or access/change timestamps')
            if member.issym() and member.linkname != expected['symlink']:
                raise ValueError('Archive symbolic link differs from filesystem inventory')
            if member.islnk():
                target = inventory.get(member.linkname.removeprefix('./').rstrip('/'))
                if not target or target.get('type') != 'file' or any(
                        target[key] != expected[key] for key in ('bytes', 'sha256', 'uid', 'gid', 'mode')):
                    raise ValueError('Archive hard link differs from filesystem inventory')
    if checked != set(inventory):
        raise ValueError('Archive lacks filesystem inventory entries')
    return len(checked)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(folder):
    manifest = json.loads((folder / 'image-manifest.json').read_text())
    if manifest['status'] != 'HOST_VERIFIED_NOT_HARDWARE_BOOTED' or manifest.get('packaged_content_audit') != 'PACKAGED_CONTENT_CHECKS_PASS':
        raise ValueError('This export did not pass the required image and package checks')
    if not manifest.get('ownership_and_modes_verified_readonly'):
        raise ValueError('This export did not verify filesystem ownership and permissions')
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
    inventory = json.loads((folder / 'root-file-manifest.json').read_text())
    for name in ('.', 'etc', 'usr', 'usr/local', 'usr/local/sbin'):
        record = inventory[name]
        if (record['type'], record['uid'], record['gid'], record['mode']) != ('directory', 0, 0, '0o755'):
            raise ValueError('Protected system directory has unsafe metadata')
    if any(record['type'] == 'directory' and int(record['mode'], 8) & 0o002
           and name not in ('tmp', 'var/tmp') for name, record in inventory.items()):
        raise ValueError('Export has an unexpected world-writable directory')
    metadata_count = verify_archive_metadata(folder / 'pf1007l-sanitized-root.tar.xz', inventory)
    return {'result': 'PASS', 'all_asset_hashes_verified': True, 'compressed_image_matches_raw_sha256': True,
            'archive_metadata_entries_checked': metadata_count, 'numeric_archive_owners': True,
            'archive_access_change_timestamps_removed': True,
            'image_status': manifest['status'], 'hardware_boot_tested': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.dist), indent=2))
