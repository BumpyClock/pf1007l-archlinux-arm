#!/usr/bin/env python3
"""Exercise source preparation with a small archive and private-input fixtures."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("rebuild", Path(__file__).resolve().parents[1] / "rebuild.py")
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)

class SourcePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.firmware = self.base / "private-firmware"
        self.firmware.mkdir()
        self.panel = self.base / "private-panel.h"
        self.panel.write_bytes(b"private fixture panel")
        fw = self.firmware / "silead/example.fw"
        fw.parent.mkdir()
        fw.write_bytes(b"private fixture firmware")
        data = {"files": [self.record(fw, "firmware/silead/example.fw"), self.record(self.panel, "kernel-overlay/drivers/gpu/drm/panel/sq9365-private-table.h")]}
        self.write("firmware/required-inputs.json", json.dumps(data))
        original = json.loads((recipe.REPO / "kernel/source-manifest.json").read_text())
        self.manifest = copy.deepcopy(original)
        self.upstream = {}
        for entry in self.manifest["delta"]:
            path = entry["path"]
            if entry["kind"] == "modified":
                before = ("upstream fixture " + path).encode()
                self.upstream[path] = before
                entry["upstream_sha256"] = hashlib.sha256(before).hexdigest()
            payload = self.panel.read_bytes() if entry.get("private") else ("baseline fixture " + path).encode()
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            if not entry.get("private"):
                self.write("kernel/overlay/" + path, payload)
        self.write("kernel/config/config", 'CONFIG_LOCALVERSION="-pf-console-r1"\n# CONFIG_LOCALVERSION_AUTO is not set\nCONFIG_EXTRA_FIRMWARE_DIR="firmware"\n')
        self.write("kernel/config/Module.symvers", "fixture export table")
        self.write("kernel/production-touch/silead.c", "final production touch fixture")
        self.write("kernel/standard-power/provider/axp20x-regulator.c", "final standard power fixture")
        self.write("hardware/pf1007l-standard-wifi.dts", "/dts-v1/; / {};")
        self.write("drivers/aic8800-port.patch", "fixture driver patch")
        self.write("drivers/aic8800/src/SDIO/driver_fw/driver/aic8800/Makefile", "fixture driver Makefile")
        self.pins = {name: recipe.sha(self.repo / name) for name in recipe.PINS}
        self.driver_pin = recipe.tree_sha(self.repo / "drivers/aic8800")
        self.archive = self.base / "linux-7.2.10.tar.xz"
        self.create_archive()
        self.work = self.base / "new-work"
    def tearDown(self):
        self.temp.cleanup()
    def record(self, path, name):
        return {"path": name, "bytes": path.stat().st_size, "sha256": recipe.sha(path)}
    def write(self, name, data):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)
    def create_archive(self, extra=None):
        with tarfile.open(self.archive, "w:xz") as archive:
            members = {"Makefile": b"fixture Makefile", **self.upstream}
            for name, data in members.items():
                item = tarfile.TarInfo("linux-7.2.10/" + name)
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
            if extra:
                item = tarfile.TarInfo(extra)
                item.size = 1
                archive.addfile(item, io.BytesIO(b"x"))
        self.manifest["archive"]["archive_sha256"] = recipe.sha(self.archive)
    def prepare(self):
        return recipe.prepare(self.repo, self.archive, self.work, self.panel, self.firmware, self.manifest, self.pins, self.driver_pin)
    def test_all_deltas_private_inputs_and_final_overrides(self):
        source, build, receipt = self.prepare()
        self.assertEqual(len(receipt["baseline_deltas"]), 12)
        self.assertEqual((source / "drivers/input/touchscreen/silead.c").read_text(), "final production touch fixture")
        self.assertEqual((source / "drivers/regulator/axp20x-regulator.c").read_text(), "final standard power fixture")
        self.assertEqual((source / "drivers/gpu/drm/panel/sq9365-private-table.h").read_bytes(), self.panel.read_bytes())
        self.assertEqual((self.work / "firmware/silead/example.fw").read_bytes(), b"private fixture firmware")
        self.assertIn(str(self.work / "firmware"), (build / ".config").read_text())
        self.assertFalse(receipt["hardware_verified"])
        self.assertFalse(receipt["deployed"])
    def test_missing_firmware_fails_before_creating_workspace(self):
        (self.firmware / "silead/example.fw").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.prepare()
        self.assertFalse(self.work.exists())
    def test_wrong_panel_header_fails_before_creating_workspace(self):
        self.panel.write_bytes(b"wrong panel")
        with self.assertRaisesRegex(ValueError, "differs"):
            self.prepare()
        self.assertFalse(self.work.exists())
    def test_changed_final_driver_override_is_rejected(self):
        self.write("kernel/production-touch/silead.c", "unexpected source")
        with self.assertRaisesRegex(ValueError, "Pinned repository input differs"):
            self.prepare()
        self.assertFalse(self.work.exists())
    def test_upstream_file_content_checked_before_replacement(self):
        self.upstream["drivers/mfd/axp20x.c"] = b"unexpected upstream"
        self.create_archive()
        with self.assertRaisesRegex(ValueError, "Upstream source differs"):
            self.prepare()
    def test_tar_traversal_rejected_without_external_write(self):
        self.create_archive("linux-7.2.10/../../escaped")
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.prepare()
        self.assertFalse((self.base / "escaped").exists())
    def test_existing_workspace_never_overwritten(self):
        self.work.mkdir()
        marker = self.work / "keep"
        marker.write_bytes(b"retained")
        with self.assertRaisesRegex(ValueError, "new workspace"):
            self.prepare()
        self.assertEqual(marker.read_bytes(), b"retained")
    def test_changed_aic_tree_rejected_before_extract(self):
        self.write("drivers/aic8800/unexpected.c", "unqualified driver")
        with self.assertRaisesRegex(ValueError, "AIC driver tree differs"):
            self.prepare()
        self.assertFalse(self.work.exists())

if __name__ == "__main__":
    unittest.main()
