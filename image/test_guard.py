"""Reject foreign cards while accepting the original and enlarged owned layout."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
UUID = '18cd35d6-4bfa-46be-a832-91e13b6b87f9'


class Guard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        values = {'sys/class/block/mmcblk0/device/type': 'SD', 'sys/class/block/mmcblk0/size': '16777216',
            'sys/class/block/mmcblk0p1/start': '8192', 'sys/class/block/mmcblk0p1/size': '524288',
            'sys/class/block/mmcblk0p2/partition': '2', 'sys/class/block/mmcblk0p2/start': '532480',
            'sys/class/block/mmcblk0p2/size': '8388608', 'etc/pf-direct-root': 'PF1007L_PUBLIC_ROOT_V1 uuid=' + UUID,
            'run/pf-sd/linux-sd/direct-root.marker': 'PF1007L_PUBLIC_ROOT_V1 uuid=' + UUID}
        for relative, value in values.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value + '\n')
        source = (HERE / 'portable-root-guard.sh.in').read_text()
        for old, value in {'@ROOT_UUID@': UUID, '@FAT_SECTORS@': '524288', '@ROOT_START@': '532480', '@ROOT_SECTORS@': '8388608'}.items():
            source = source.replace(old, value)
        (self.root / 'guard').write_text(source)

    def tearDown(self):
        self.temp.cleanup()

    def check(self, root_uuid=UUID):
        wrapper = '''
findmnt() {
  local field= target=
  while (( $# )); do case $1 in -o) field=$2; shift;; -T) target=$2; shift;; esac; shift; done
  case "$target:$field" in
    /:TARGET) echo /;; /:FSTYPE) echo ext4;; /:UUID) echo "$PF_TEST_UUID";; /:OPTIONS) echo rw,noatime;; /:SOURCE) echo /dev/mmcblk0p2;;
    /run/pf-sd:SOURCE) echo /dev/mmcblk0p1;; /run/pf-sd:TARGET) echo /run/pf-sd;; /run/pf-sd:FSTYPE) echo vfat;; /run/pf-sd:LABEL) echo A33BACKUP;;
    *) return 1;;
  esac
}
source "$1/guard"
pf_require_direct_root "$1"
'''
        return subprocess.run(['bash', '-c', wrapper, 'test', str(self.root)],
            env=os.environ | {'PF_TEST_UUID': root_uuid}, capture_output=True).returncode

    def test_owned_original_and_expanded(self):
        self.assertEqual(self.check(), 0)
        (self.root / 'sys/class/block/mmcblk0p2/size').write_text('16244736\n')
        self.assertEqual(self.check(), 0)

    def test_foreign_uuid(self):
        self.assertNotEqual(self.check('18cd35d6-4bfa-46be-a832-91e13b6b87f0'), 0)

    def test_reject_emmc(self):
        (self.root / 'sys/class/block/mmcblk0/device/type').write_text('MMC\n')
        self.assertNotEqual(self.check(), 0)

    def test_reject_extra_partition(self):
        (self.root / 'sys/class/block/mmcblk0p3').mkdir()
        self.assertNotEqual(self.check(), 0)

    def test_reject_bad_marker(self):
        (self.root / 'etc/pf-direct-root').write_text('foreign\n')
        self.assertNotEqual(self.check(), 0)

    def test_reject_root_outside_capacity(self):
        (self.root / 'sys/class/block/mmcblk0p2/size').write_text('16777216\n')
        self.assertNotEqual(self.check(), 0)


if __name__ == '__main__':
    unittest.main()
