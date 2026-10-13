#!/usr/bin/env python3
"""Run in Linux/WSL; all account, network and filesystem writes use a sandbox."""
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "root-overlay/usr/local/sbin"

class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.root / "run").mkdir()
        self.log = self.root / "calls.log"
        self.env = dict(os.environ, PF_TEST_LOG=str(self.log), PF_TEST_FAIL="")
        self.mock("usermod", '#!/bin/sh\nprintf "usermod %s %s\n" "$1" "$2" >> "$PF_TEST_LOG"\n')
        self.mock("passwd", '#!/bin/sh\nif [ "$1" = -S ]; then echo "$2 P 2026-01-01 0 99999 7 -1"; else printf "passwd %s\n" "$1" >> "$PF_TEST_LOG"; [ "$PF_TEST_FAIL" != "$1" ]; fi\n')
        self.mock("systemctl", '#!/bin/sh\nprintf "systemctl %s %s\n" "$1" "$2" >> "$PF_TEST_LOG"\n')
        self.mock("wpa_passphrase", "#!/usr/bin/env python3\nimport hashlib,sys\np=sys.stdin.readline().rstrip('\\n')\nprint('network={')\nprint('    #psk='+p)\nprint('    psk='+hashlib.pbkdf2_hmac('sha1',p.encode(),sys.argv[1].encode(),4096,32).hex())\nprint('}')\n")
    def tearDown(self):
        self.temp.cleanup()
    def mock(self, name, contents):
        path = self.bin / name
        path.write_text(contents)
        path.chmod(0o755)
    def sandbox(self, name):
        original = SCRIPTS / name
        subprocess.run(["bash", "-n", str(original)], check=True)
        text = original.read_text().replace("/var/lib/pf-", str(self.root / "var/lib/pf-"))
        text = text.replace("/run/pf-", str(self.root / "run/pf-"))
        text = text.replace("export PATH=/usr/local/sbin:/usr/local/bin:/usr/bin", f"export PATH={self.bin}:/usr/bin")
        text = text.replace("/usr/local/sbin/pf-network-setup", str(self.bin / "pf-network-setup"))
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)
        return path
    def invoke(self, path, inputs=()):
        master, slave = pty.openpty()
        proc = subprocess.Popen(["bash", str(path)], stdin=slave, stdout=slave, stderr=slave, env=self.env)
        os.close(slave)
        output = b""
        deadline = time.monotonic() + 10
        pending = list(inputs)
        try:
            while time.monotonic() < deadline:
                if pending and pending[0][0].encode() in output:
                    _, answer = pending.pop(0)
                    os.write(master, answer.encode() + b"\n")
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        part = os.read(master, 65536)
                    except OSError:
                        break
                    if not part:
                        break
                    output += part
                elif proc.poll() is not None:
                    break
            else:
                proc.kill()
                self.fail("sandbox command timed out")
            result = proc.wait(timeout=2)
            return result, output.decode(errors="replace")
        finally:
            os.close(master)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    def test_completion_and_rerun_require_no_more_password_setup(self):
        path = self.sandbox("pf-firstboot")
        result, _ = self.invoke(path, [("Configure WPA2 Wi-Fi now?", "n")])
        self.assertEqual(result, 0)
        marker = self.root / "var/lib/pf-firstboot/complete"
        self.assertEqual(marker.read_text(), "version=1\n")
        calls = self.log.read_text()
        self.assertIn("passwd root", calls)
        self.assertIn("passwd diag", calls)
        self.assertEqual(self.invoke(path)[0], 0)
        self.assertEqual(self.log.read_text(), calls)
    def test_partial_password_failure_locks_both_and_creates_no_marker(self):
        path = self.sandbox("pf-firstboot")
        self.env["PF_TEST_FAIL"] = "diag"
        self.assertNotEqual(self.invoke(path)[0], 0)
        self.assertFalse((self.root / "var/lib/pf-firstboot/complete").exists())
        self.assertTrue(self.log.read_text().endswith("usermod -L root\nusermod -L diag\n"))
    def test_network_special_ssid_and_hidden_secret_psk_only(self):
        path = self.sandbox("pf-network-setup")
        ssid = "Example's access point"
        password = "temporary-test-secret"
        code, output = self.invoke(path, [("SSID (saved privately):", ssid), ("hexadecimal PSK:", password)])
        self.assertEqual(code, 0, output)
        target = self.root / "var/lib/pf-wifi/wpa_supplicant.conf"
        config = target.read_text()
        self.assertIn("ssid=" + ssid.encode().hex(), config)
        expected = hashlib.pbkdf2_hmac("sha1", password.encode(), ssid.encode(), 4096, 32).hex()
        self.assertIn("psk=" + expected, config)
        self.assertNotIn(password, config)
        self.assertNotIn(password, output)
        self.assertNotIn("#psk", config)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertIn("systemctl restart pf-wifi.service", self.log.read_text())
    def test_invalid_network_preserves_previous_configuration(self):
        path = self.sandbox("pf-network-setup")
        target = self.root / "var/lib/pf-wifi/wpa_supplicant.conf"
        target.parent.mkdir(parents=True)
        target.write_text("previous")
        code, _ = self.invoke(path, [("SSID (saved privately):", "example"), ("hexadecimal PSK:", "short")])
        self.assertNotEqual(code, 0)
        self.assertEqual(target.read_text(), "previous")
        self.assertFalse(self.log.exists())
    def test_keyring_failure_retry_and_success_are_idempotent(self):
        path = self.sandbox("pf-init-keyring")
        state = self.root / "var/lib/pf-firstboot"
        state.mkdir(parents=True)
        (state / "complete").write_text("version=1\n")
        self.mock("pacman-key", '#!/bin/sh\nprintf "pacman-key %s\n" "$1" >> "$PF_TEST_LOG"\n[ "$PF_TEST_FAIL" != "$1" ]\n')
        self.env["PF_TEST_FAIL"] = "--populate"
        self.assertNotEqual(self.invoke(path)[0], 0)
        self.assertFalse((state / "pacman-keyring-ready").exists())
        self.env["PF_TEST_FAIL"] = ""
        self.assertEqual(self.invoke(path)[0], 0)
        self.assertTrue((state / "pacman-keyring-ready").is_file())
        calls = self.log.read_text()
        self.assertEqual(self.invoke(path)[0], 0)
        self.assertEqual(self.log.read_text(), calls)
    def test_completed_setup_executes_normal_getty_for_both_terminals(self):
        path = self.sandbox("pf-console-login")
        path.write_text(path.read_text().replace("/usr/bin/agetty", str(self.bin / "agetty")))
        self.mock("agetty", '#!/bin/sh\nprintf "agetty %s\n" "$*" >> "$PF_TEST_LOG"\n')
        state = self.root / "var/lib/pf-firstboot"
        state.mkdir(parents=True)
        (state / "complete").write_text("version=1\n")
        for device in ("ttyGS0", "tty1"):
            subprocess.run(["bash", str(path), device], env=self.env, check=True)
        calls = self.log.read_text().splitlines()
        self.assertEqual(calls, ["agetty --noissue --keep-baud 115200,38400,9600 ttyGS0 vt100", "agetty --noreset - linux"])
        self.assertNotIn("passwd", self.log.read_text())
    def test_utf8_ssid_limit_is_bytes(self):
        path = self.sandbox("pf-network-setup")
        code, _ = self.invoke(path, [("SSID (saved privately):", "é" * 17)])
        self.assertNotEqual(code, 0)
        self.assertFalse((self.root / "var/lib/pf-wifi/wpa_supplicant.conf").exists())

if __name__ == "__main__":
    unittest.main()
