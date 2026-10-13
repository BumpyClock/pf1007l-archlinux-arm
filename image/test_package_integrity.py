"""Reject damaged package payloads and invalid executable contents."""

import gzip
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from audit_packages import audit
from build_image import validate_executables


class PackageIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / 'var/lib/pacman/local/fixture-1-1'
        self.database.mkdir(parents=True)
        (self.root / 'usr/bin').mkdir(parents=True)
        (self.root / 'usr/include').mkdir()
        self.program = self.root / 'usr/bin/fixture'
        self.elf = bytearray(64)
        self.elf[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<H', self.elf, 18, 40)
        self.program.write_bytes(self.elf)
        self.program.chmod(0o755)
        sha = hashlib.sha256(self.elf).hexdigest()
        self.mtree = f'#mtree\n./usr/bin/fixture type=file sha256digest={sha}\n./.PKGINFO type=file sha256digest={sha}\n'
        (self.database / 'mtree').write_bytes(gzip.compress(self.mtree.encode()))

    def tearDown(self):
        self.temp.cleanup()

    def test_good_package_and_metadata_skip(self):
        result = audit(self.root)
        self.assertEqual(result['status'], 'PACKAGED_CONTENT_CHECKS_PASS')
        self.assertEqual(result['packaged_files_checked'], 1)
        self.assertEqual(validate_executables(self.root), 1)

    def test_changed_package_binary_rejected(self):
        self.program.write_bytes(gzip.compress(b'wrong artifact'))
        self.assertEqual(audit(self.root)['status'], 'PACKAGED_CONTENT_CHECKS_FAIL')
        with self.assertRaises(ValueError):
            validate_executables(self.root)

    def test_invalid_mtree_rejected(self):
        (self.database / 'mtree').write_bytes(b'not a gzip package manifest')
        self.assertEqual(audit(self.root)['unexpected'][0]['issue'], 'invalid_mtree')

    def test_traversal_rejected(self):
        text = './../../outside type=file sha256digest=' + '0' * 64 + '\n'
        (self.database / 'mtree').write_bytes(gzip.compress(text.encode()))
        self.assertEqual(audit(self.root)['unexpected'][0]['issue'], 'invalid_path')

    def test_wrong_architecture_rejected(self):
        struct.pack_into('<H', self.elf, 18, 62)
        self.program.write_bytes(self.elf)
        with self.assertRaises(ValueError):
            validate_executables(self.root)

    def test_wrong_dns_target_is_not_allowed(self):
        (self.root / 'etc').mkdir()
        (self.root / 'etc/resolv.conf').symlink_to('/run/foreign/resolv.conf')
        text = './etc/resolv.conf type=file sha256digest=' + '0' * 64 + '\n'
        (self.database / 'mtree').write_bytes(gzip.compress(text.encode()))
        self.assertEqual(audit(self.root)['status'], 'PACKAGED_CONTENT_CHECKS_FAIL')

    def test_unreviewed_tpm_config_rejected(self):
        text = './etc/tpm2-tss/fapi-profiles/P_ECCP384SHA384.json type=file sha256digest=' + '0' * 64 + '\n'
        (self.database / 'mtree').write_bytes(gzip.compress(text.encode()))
        self.assertEqual(audit(self.root)['status'], 'PACKAGED_CONTENT_CHECKS_FAIL')


if __name__ == '__main__':
    unittest.main()
