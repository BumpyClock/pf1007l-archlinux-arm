"""Exercise overlay isolation, directory policy, and exported filesystem metadata."""

import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from build_image import copy_overlay, inventory, mounted, normalize_directories, validate_directories
from verify_assets import verify_archive_metadata


@unittest.skipUnless(os.geteuid() == 0, 'Linux root required for ownership checks')
class Metadata(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.root = self.work / 'root'
        self.source = self.work / 'overlay'
        for path in ('etc', 'usr/local/sbin', 'usr/local/lib', 'etc/systemd/system/multi-user.target.wants',
                     'var/lib/pf-wifi', 'var/lib/pf-firstboot', 'tmp', 'var/tmp', 'root',
                     'home/diag/pf-update', 'var/lib/service-private'):
            (self.root / path).mkdir(parents=True, exist_ok=True)
        (self.root / 'etc/passwd').write_text('diag:x:1000:1000::/home/diag:/bin/bash\n')
        self.service = self.root / 'var/lib/service-private'
        self.service.chmod(0o700)
        os.chown(self.service, 981, 982)
        executable = self.root / 'usr/local/lib/package-tool'
        executable.write_bytes(b'fixture package executable\n')
        os.chown(executable, 0, 982)
        executable.chmod(0o4755)
        target = self.source / 'usr/local/sbin/helper'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'#!/bin/sh\nexit 0\n')
        for directory in [self.source, *self.source.rglob('*')]:
            if directory.is_dir():
                os.chown(directory, 1000, 1000)
                directory.chmod(0o777)

    def tearDown(self):
        self.temp.cleanup()

    def test_overlay_does_not_import_directory_metadata(self):
        before = inventory(self.root)
        copy_overlay(self.source, self.root)
        after = inventory(self.root)
        for name, record in before.items():
            self.assertEqual(after[name], record)
        self.assertEqual(after['usr/local/sbin/helper']['uid'], 0)
        self.assertEqual(after['usr/local/sbin/helper']['mode'], '0o755')

    def repaired(self):
        for path in (self.root, self.root / 'usr', self.root / 'usr/local/sbin'):
            os.chown(path, 1000, 1000)
            path.chmod(0o777)
        copy_overlay(self.source, self.root)
        policy = normalize_directories(self.root, [self.source])
        validate_directories(self.root, policy)
        return policy

    def test_legacy_repair_preserves_service_ownership_and_setuid(self):
        self.repaired()
        result = inventory(self.root)
        self.assertEqual((result['.']['uid'], result['.']['mode']), (0, '0o755'))
        self.assertEqual((result['var/lib/service-private']['uid'], result['var/lib/service-private']['gid'],
                          result['var/lib/service-private']['mode']), (981, 982, '0o700'))
        self.assertEqual(result['usr/local/lib/package-tool']['mode'], '0o4755')
        self.assertEqual(result['usr/local/lib/package-tool']['gid'], 982)
        self.assertEqual(result['home/diag']['uid'], 1000)
        self.assertEqual(result['root']['mode'], '0o700')
        self.assertEqual(result['lost+found']['mode'], '0o700')
        self.assertEqual(result['tmp']['mode'], '0o1777')

    def test_unexpected_world_writable_directory_fails(self):
        policy = self.repaired()
        self.service.chmod(0o777)
        with self.assertRaisesRegex(ValueError, 'world-writable'):
            validate_directories(self.root, policy)

    def test_overlay_symlink_rejected(self):
        (self.source / 'escape').symlink_to('/tmp')
        with self.assertRaises(ValueError):
            copy_overlay(self.source, self.root)

    def test_tar_numeric_metadata_and_no_access_change_times(self):
        self.repaired()
        archive = self.work / 'root.tar.xz'
        subprocess.run(['tar', '--numeric-owner', '--format=pax', '--pax-option=delete=atime,delete=ctime',
                        '-cJpf', str(archive), '-C', str(self.root), '.'], check=True)
        self.assertEqual(verify_archive_metadata(archive, inventory(self.root)), len(inventory(self.root)))
        with tarfile.open(archive) as stream:
            for member in stream:
                self.assertFalse('atime' in member.pax_headers or 'ctime' in member.pax_headers)
                relative = member.name.removeprefix('./').rstrip('/') or '.'
                self.assertAlmostEqual(member.mtime, (self.root / relative).lstat().st_mtime, places=5)

    def test_archive_bad_owner_rejected(self):
        archive = self.work / 'bad.tar.xz'
        metadata = tarfile.TarInfo('.')
        metadata.type = tarfile.DIRTYPE
        metadata.mode = 0o777
        metadata.uid = metadata.gid = 1000
        with tarfile.open(archive, 'w:xz') as stream:
            stream.addfile(metadata)
        with self.assertRaisesRegex(ValueError, 'ownership'):
            verify_archive_metadata(archive, inventory(self.root))

    def test_archive_wrong_hard_link_target_rejected(self):
        self.repaired()
        original = self.root / 'usr/local/lib/package-tool'
        duplicate = self.root / 'usr/local/lib/duplicate'
        os.link(original, duplicate)
        wrong = self.root / 'usr/local/lib/wrong'
        wrong.write_bytes(b'different fixture content\n')
        os.chown(wrong, 0, 982)
        wrong.chmod(0o4755)
        archive = self.work / 'wrong-link.tar.xz'
        with tarfile.open(archive, 'w:xz') as stream:
            for name, record in inventory(self.root).items():
                member = stream.gettarinfo(str(self.root / name), arcname=name)
                member.uname = member.gname = ''
                if name == 'usr/local/lib/duplicate':
                    member.type = tarfile.LNKTYPE
                    member.linkname = 'usr/local/lib/wrong'
                    member.size = 0
                if member.isfile():
                    with (self.root / name).open('rb') as content:
                        stream.addfile(member, content)
                else:
                    stream.addfile(member)
        with self.assertRaisesRegex(ValueError, 'hard link'):
            verify_archive_metadata(archive, inventory(self.root))

    @unittest.skipUnless(shutil.which('mkfs.ext4'), 'ext4 tools required')
    def test_actual_ext4_root_inode_and_all_metadata(self):
        policy = self.repaired()
        image = self.work / 'root.ext4'
        with image.open('xb') as stream:
            stream.truncate(64 * 1024 ** 2)
        subprocess.run(['mkfs.ext4', '-q', '-F', str(image)], check=True)
        with mounted(image, self.work / 'mount') as target:
            subprocess.run(['cp', '-a', '-x', str(self.root) + '/.', str(target)], check=True)
        subprocess.run(['e2fsck', '-fn', str(image)], check=True, stdout=subprocess.DEVNULL)
        with mounted(image, self.work / 'inspect', True) as target:
            validate_directories(target, policy)
            self.assertEqual(inventory(target), inventory(self.root))


if __name__ == '__main__':
    unittest.main()
