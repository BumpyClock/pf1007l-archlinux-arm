#!/usr/bin/env python3
"""Check loader isolation configuration and independent eGON/SPL boundaries."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("uboot_rebuild", Path(__file__).resolve().parents[1] / "rebuild.py")
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)

class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def config(self, replacements):
        text = (recipe.HERE / "accepted.config").read_text()
        for key, value in replacements.items():
            lines = [line for line in text.splitlines() if not line.startswith("CONFIG_" + key + "=") and line != "# CONFIG_" + key + " is not set"]
            lines.append("CONFIG_" + key + "=" + value)
            text = "\n".join(lines) + "\n"
        path = self.root / "test.config"
        path.write_text(text)
        return path
    def binary(self, size=0x9000, last_nonzero=0x300, length=0x6000):
        data = bytearray(size)
        struct.pack_into("<I", data, 0, 0xea000016)
        data[4:12] = b"eGON.BT0"
        struct.pack_into("<II", data, 12, 0x5f0a6c39, length)
        data[last_nonzero] = 7
        checksum = sum(struct.unpack("<%dI" % (length // 4), data[:length])) & 0xffffffff
        struct.pack_into("<I", data, 12, checksum)
        path = self.root / "test.bin"
        path.write_bytes(data)
        return path
    def test_complete_pinned_inputs_and_qualified_config(self):
        manifest = json.loads((recipe.HERE / "source-manifest.json").read_text())
        recipe.verify_inputs(recipe.HERE, manifest)
        self.assertEqual(recipe.check_config(recipe.HERE / "accepted.config")["CONFIG_DRAM_CLK"], "456")
    def test_unsafe_controller_environment_gadget_and_voltage_rejected(self):
        cases = [("MMC_SUNXI_SLOT_EXTRA", "2"), ("CMD_SAVEENV", "y"), ("USB_GADGET", "y"), ("AXP_DCDC2_VOLT", "999"), ("ENV_IS_IN_MMC", "y"), ("SPL_MMC_WRITE", "y")]
        for key, value in cases:
            with self.subTest(key=key), self.assertRaises(ValueError):
                recipe.check_config(self.config({key: value}))
    def test_valid_independent_egon_checksum_and_stack_boundary(self):
        output = recipe.validate_image(self.binary())
        self.assertTrue(output["egon_checksum_valid"])
        self.assertEqual(output["spl_last_nonzero_end"], 0x301)
    def test_checksum_corruption_rejected(self):
        path = self.binary()
        data = bytearray(path.read_bytes())
        data[0x100] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "checksum"):
            recipe.validate_image(path)
    def test_spl_stack_margin_overflow_rejected(self):
        with self.assertRaisesRegex(ValueError, "stack margin"):
            recipe.validate_image(self.binary(last_nonzero=0x5e01))
    def test_bootstrap_reserved_area_overflow_rejected(self):
        with self.assertRaisesRegex(ValueError, "bootstrap area"):
            recipe.validate_image(self.binary(size=1048576 - 8192 + 1))
    def test_non_arm_header_rejected(self):
        path = self.binary()
        data = bytearray(path.read_bytes())
        data[:4] = b"\0" * 4
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "ARM"):
            recipe.validate_image(path)
    def test_tar_traversal_rejected_before_external_write(self):
        import io
        archive = self.root / "malicious.tar"
        with tarfile.open(archive, "w") as package:
            item = tarfile.TarInfo("../escaped")
            item.size = 1
            package.addfile(item, io.BytesIO(b"x"))
        destination = self.root / "source"
        destination.mkdir()
        with self.assertRaisesRegex(ValueError, "escapes"):
            recipe.extract(archive, destination)
        self.assertFalse((self.root / "escaped").exists())

if __name__ == "__main__":
    unittest.main()
