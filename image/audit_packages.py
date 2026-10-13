#!/usr/bin/env python3
"""Check installed package file contents before assembling an SD image."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zlib

CONFIG_OVERRIDES = {
    'etc/fstab', 'etc/group', 'etc/gshadow', 'etc/hosts', 'etc/issue',
    'etc/passwd', 'etc/shadow', 'etc/shells', 'etc/subuid', 'etc/subgid',
    'etc/pacman.conf', 'etc/pacman.d/mirrorlist', 'var/lib/krb5kdc/kdc.conf',
}
PACKAGE_METADATA = {'.BUILDINFO', '.PKGINFO', '.INSTALL', '.MTREE'}


def audit(root):
    failures = []
    expected_configuration = []
    checked = 0
    databases = sorted((root / 'var/lib/pacman/local').iterdir())
    for package in databases:
        if not package.is_dir():
            continue
        mtree = package / 'mtree'
        if not mtree.is_file():
            failures.append({'package': package.name, 'path': 'package-mtree', 'issue': 'missing_mtree'})
            continue
        try:
            data = gzip.decompress(mtree.read_bytes()).decode()
        except (OSError, EOFError, UnicodeError, zlib.error):
            failures.append({'package': package.name, 'path': 'package-mtree', 'issue': 'invalid_mtree'})
            continue
        for line in data.splitlines():
            if not line.startswith('./'):
                continue
            tokens = line.split()
            relative = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), tokens[0][2:])
            if relative in PACKAGE_METADATA:
                continue
            parts = PurePosixPath(relative)
            if parts.is_absolute() or '..' in parts.parts:
                failures.append({'package': package.name, 'path': 'package-mtree', 'issue': 'invalid_path'})
                continue
            fields = dict(token.split('=', 1) for token in tokens[1:] if '=' in token)
            expected = fields.get('sha256digest')
            if not expected:
                continue
            path = root / relative
            issue = None
            if path.is_symlink():
                issue = 'regular_file_replaced_by_symlink'
            elif not path.is_file():
                issue = 'missing'
            else:
                with path.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                        issue = 'content_mismatch'
            checked += 1
            if issue:
                row = {'package': package.name, 'path': relative, 'issue': issue}
                resolved_stub = relative == 'etc/resolv.conf' and path.is_symlink() and str(path.readlink()) == '/run/systemd/resolve/stub-resolv.conf'
                if relative in CONFIG_OVERRIDES or relative.startswith('etc/netctl/examples/') or resolved_stub:
                    expected_configuration.append(row)
                else:
                    failures.append(row)
    return {'status': 'PACKAGED_CONTENT_CHECKS_PASS' if not failures else 'PACKAGED_CONTENT_CHECKS_FAIL',
            'packaged_files_checked': checked, 'unexpected': failures,
            'reviewed_configuration_overrides': expected_configuration}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root.resolve())
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'packaged_files_checked': result['packaged_files_checked'],
                      'unexpected_count': len(result['unexpected'])}))
    if result['unexpected']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
