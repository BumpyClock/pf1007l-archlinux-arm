"""Verify online ext4 growth using a newly created disposable loop image."""

from pathlib import Path
import os
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def run(*args):
    return subprocess.run([str(arg) for arg in args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    if os.geteuid() != 0:
        raise ValueError('Linux root required for new disposable loop files')
    with tempfile.TemporaryDirectory(prefix='pf-growth-loop-') as folder:
        work = Path(folder)
        image = work / 'fixture.img'
        header = bytearray(512)
        for n, (kind, start, size) in enumerate(((12, 8192, 65536), (131, 73728, 131072))):
            header[446 + 16 * n:462 + 16 * n] = struct.pack('<B3sB3sII', 0, b'\xfe\xff\xff', kind, b'\xfe\xff\xff', start, size)
        header[510:] = b'\x55\xaa'
        with image.open('xb') as stream:
            stream.write(header)
            stream.truncate(100 * 1024 ** 2)
        loop = run('losetup', '--find', '--show', '--partscan', image)
        root = loop + 'p2'
        target = work / 'mount'
        target.mkdir()
        mounted = False
        try:
            run('mkfs.ext4', '-q', '-F', root)
            run('mount', root, target)
            mounted = True
            (target / 'preserved').write_text('unchanged during online growth\n')
            initial = os.statvfs(target).f_blocks * os.statvfs(target).f_frsize
            with image.open('r+b') as stream:
                stream.truncate(256 * 1024 ** 2)
            run('losetup', '--set-capacity', loop)
            run('bash', '-c', 'source "$1"; pf_grow_partition "$2" 524288 65536 73728 131072',
                'test', HERE / 'pf-grow-root', loop)
            run('partx', '--update', '--nr', '2', loop)
            run('resize2fs', root)
            grown = os.statvfs(target).f_blocks * os.statvfs(target).f_frsize
            assert grown > initial * 3
            assert (target / 'preserved').read_text() == 'unchanged during online growth\n'
            run('sync', '-f', target)
            run('umount', target)
            mounted = False
            run('e2fsck', '-fn', root)
            print('PASS: mounted ext4 grew from 64 MiB to SD remainder; file preserved; e2fsck -fn passed.')
        finally:
            if mounted:
                run('umount', target)
            run('losetup', '--detach', loop)


if __name__ == '__main__':
    main()
