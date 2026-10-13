"""Exercise partition growth against disposable regular files, never block devices."""

import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class Growth(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.image = Path(self.temp.name) / 'fixture.img'
        self.header = bytearray(512)
        for index, values in enumerate(((12, 8192, 524288), (131, 532480, 8388608))):
            self.header[446 + 16 * index:462 + 16 * index] = struct.pack('<B3sB3sII', 0, b'\xfe\xff\xff', values[0], b'\xfe\xff\xff', values[1], values[2])
        self.header[510:] = b'\x55\xaa'
        self.image.write_bytes(self.header + b'preserved boot payload')

    def tearDown(self):
        self.temp.cleanup()

    def grow(self, capacity=16777216):
        return subprocess.run(['bash', '-c', 'source "$1"; pf_grow_partition "$2" "$3" 524288 532480 8388608',
            'test', str(HERE / 'pf-grow-root'), str(self.image), str(capacity)], capture_output=True)

    def test_growth_changes_only_root_size_and_is_repeatable(self):
        old = self.image.read_bytes()
        self.assertEqual(self.grow().returncode, 0)
        new = self.image.read_bytes()
        self.assertEqual(struct.unpack_from('<I', new, 474)[0], 16244736)
        self.assertEqual(old[:474], new[:474])
        self.assertEqual(old[478:], new[478:])
        self.assertEqual(self.grow().returncode, 0)
        self.assertEqual(self.image.read_bytes(), new)

    def test_rejects_extra_partition_without_write(self):
        original = bytearray(self.image.read_bytes())
        original[482] = 131
        self.image.write_bytes(original)
        self.assertNotEqual(self.grow().returncode, 0)
        self.assertEqual(self.image.read_bytes(), original)

    def test_rejects_wrong_start_without_write(self):
        original = bytearray(self.image.read_bytes())
        struct.pack_into('<I', original, 470, 532481)
        self.image.write_bytes(original)
        self.assertNotEqual(self.grow().returncode, 0)
        self.assertEqual(self.image.read_bytes(), original)

    def test_rejects_smaller_card_without_write(self):
        original = self.image.read_bytes()
        self.assertNotEqual(self.grow(8000000).returncode, 0)
        self.assertEqual(self.image.read_bytes(), original)

    def test_rejects_card_over_mbr_limit_without_write(self):
        original = self.image.read_bytes()
        self.assertNotEqual(self.grow(4294967296).returncode, 0)
        self.assertEqual(self.image.read_bytes(), original)

    def test_rejects_invalid_signature_without_write(self):
        original = bytearray(self.image.read_bytes())
        original[510] = 0
        self.image.write_bytes(original)
        self.assertNotEqual(self.grow().returncode, 0)
        self.assertEqual(self.image.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
