#!/usr/bin/env python3
"""Validate the packaged ARM wpa_passphrase output without changing network state."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rootfs', type=Path, required=True)
parser.add_argument('--qemu', type=Path, required=True)
args = parser.parse_args()
for ssid in ('Example network', "Example's network", 'Example café'):
    passphrase = 'test-only-fixture-passphrase'
    result = subprocess.run([str(args.qemu), '-L', str(args.rootfs),
                             str(args.rootfs / 'usr/bin/wpa_passphrase'), ssid],
                            input=passphrase + '\n', capture_output=True,
                            text=True, timeout=20, check=True)
    matches = re.findall(r'(?m)^\s*psk=([0-9a-f]{64})$', result.stdout)
    expected = hashlib.pbkdf2_hmac('sha1', passphrase.encode(), ssid.encode(), 4096, 32).hex()
    assert matches == [expected], 'ARM WPA derivation or PSK-only parsing differs'
print('PASS packaged ARM WPA derivation: spaces, apostrophe and UTF-8 SSIDs')
