"""Verify account cleanup and DNS wiring on a new disposable root tree."""

import os
from pathlib import Path
import tempfile
import unittest

from build_image import sanitize


@unittest.skipUnless(os.geteuid() == 0, 'Linux root required to verify exported file ownership')
class Sanitize(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        files = {'etc/passwd': 'root:x:0:0:Fixture Root:/root:/bin/bash\ndiag:x:1000:1000:Fixture User:/home/diag:/bin/bash\nalarm:x:1001:1001:Default User:/home/alarm:/bin/bash\n',
            'etc/shadow': 'root:test-only-secret:1:0:99999:7:::\ndiag:test-only-secret:1:0:99999:7:::\nalarm:test-only-secret:1:0:99999:7:::\n',
            'etc/gshadow': 'root:test-only-secret::\ndiag:test-only-secret::\n',
            'etc/shadow-': 'test-only-old-secret\n', 'etc/pacman.d/gnupg/private-key': 'fixture key\n',
            'var/lib/pf-wifi/wpa_supplicant.conf': 'fixture private network\n',
            'root/.bash_history': 'fixture private history\n', 'var/log/journal/old': 'fixture log\n',
            'etc/resolv.conf': 'nameserver 192.0.2.53\n'}
        for relative, value in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        for relative in ('dev', 'proc', 'sys', 'run', 'etc/ssh', 'etc/systemd/system', 'var/lib/pacman/local'):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        sanitize(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_accounts_have_no_hashes_or_personal_gecos(self):
        for line in (self.root / 'etc/shadow').read_text().splitlines():
            self.assertEqual(line.split(':')[1], '!')
        for line in (self.root / 'etc/passwd').read_text().splitlines():
            self.assertEqual(line.split(':')[4], '')
        self.assertFalse((self.root / 'etc/shadow-').exists())

    def test_private_state_absent(self):
        self.assertFalse((self.root / 'etc/pacman.d/gnupg').exists())
        self.assertFalse((self.root / 'var/lib/pf-wifi/wpa_supplicant.conf').exists())
        self.assertFalse((self.root / 'root/.bash_history').exists())
        self.assertEqual(list((self.root / 'var/log').iterdir()), [])
        self.assertEqual((self.root / 'etc/machine-id').read_bytes(), b'')

    def test_dns_uses_resolved_stub_and_ssh_is_masked(self):
        self.assertEqual(os.readlink(self.root / 'etc/resolv.conf'), '/run/systemd/resolve/stub-resolv.conf')
        self.assertEqual(os.readlink(self.root / 'etc/systemd/system/sshd.service'), '/dev/null')
        self.assertEqual((self.root / 'etc/hostname').read_text(), 'pf1007l-arch\n')


if __name__ == '__main__':
    unittest.main()
