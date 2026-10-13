#!/usr/bin/env python3
"""Check the new getty drop-ins against the actual image's vendor units."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--rootfs", type=Path, required=True)
args = parser.parse_args()
firstboot = Path(__file__).resolve().parents[1]
for instance, template in (("serial-getty@ttyGS0.service", "serial-getty@.service"), ("getty@tty1.service", "getty@.service")):
    text = (args.rootfs / "usr/lib/systemd/system" / template).read_text()
    for setting in ("StandardInput=tty", "StandardOutput=tty", "TTYPath=/dev/%I", "Restart=always", "Type=idle"):
        assert setting in text.splitlines(), (template, setting)
    override = firstboot / "root-overlay/etc/systemd/system" / (instance + ".d/90-pf-firstboot.conf")
    lines = override.read_text().splitlines()
    assert lines == ["[Service]", "ExecStart=", "ExecStart=-/usr/local/sbin/pf-console-login " + ("ttyGS0" if template.startswith("serial") else "tty1")]
    assert "--autologin" not in override.read_text()
keyring = (firstboot / "root-overlay/etc/systemd/system/pf-init-keyring.service").read_text()
assert "ConditionPathExists=/var/lib/pf-firstboot/complete" in keyring.splitlines()
assert "ConditionPathExists=!/var/lib/pf-firstboot/pacman-keyring-ready" in keyring.splitlines()
assert "TimeoutStartSec=180" in keyring.splitlines()
print("PASS: vendor getty TTY/Restart inheritance, no autologin, keyring completion conditions and timeout")
