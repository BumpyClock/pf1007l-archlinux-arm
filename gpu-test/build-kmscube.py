#!/usr/bin/env python3
"""Cross-build the pinned upstream GLES2 cube using the existing ARM sysroot."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tarfile

PROJECT = Path(__file__).resolve().parent.parent
UPSTREAM = PROJECT / 'gpu-test/upstream'
COMMIT = 'f60e50e887d3c49e91ac9b06d8199b36152632fa'
ARCHIVE_SHA = '608240df61512f9423a63731b4eaff981ab6ba830364a4c90b63ddf57eb59833'
SYSROOT = None
WORK = None
OUTPUT = None
QEMU = None
SOURCES = ['common.c', 'cube-smooth.c', 'cube-gears.c', 'cube-tex.c', 'drm-atomic.c',
           'drm-common.c', 'drm-legacy.c', 'drm-offscreen.c', 'esTransform.c',
           'frame-512x512-NV12.c', 'frame-512x512-RGBA.c', 'kmscube.c', 'perfcntrs.c']


def run(*args):
    return subprocess.run([str(arg) for arg in args], check=True, capture_output=True, text=True).stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    git = ['git', '-c', 'safe.directory=' + str(UPSTREAM), '-C', UPSTREAM]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    archive = PROJECT / 'gpu-test/kmscube-upstream.tar'
    if not archive.exists():
        assert run(*git, 'rev-parse', 'HEAD').strip() == COMMIT
        run(*git, 'archive', '--format=tar', '--prefix=kmscube/', '-o', archive, COMMIT)
    assert sha(archive) == ARCHIVE_SHA, 'Pinned source archive changed'
    with tarfile.open(archive) as source:
        source.extractall(WORK, filter='data')
    source = WORK / 'kmscube'
    compiler = 'arm-linux-gnueabihf-gcc'
    binary = OUTPUT / 'kmscube.armv7h'
    command = [compiler, '--sysroot=' + str(SYSROOT), '-std=gnu99', '-O2', '-Wall', '-Wextra',
               '-fPIE', '-pie', '-nostartfiles', '-I' + str(SYSROOT / 'usr/include/libdrm'),
               str(SYSROOT / 'usr/lib/Scrt1.o'), str(SYSROOT / 'usr/lib/crti.o'),
               run(compiler, '-print-file-name=crtbeginS.o').strip()]
    command += [str(source / name) for name in SOURCES]
    command += ['-L' + str(SYSROOT / 'usr/lib'), '-Wl,-rpath-link,' + str(SYSROOT / 'usr/lib'),
                '-Wl,-z,relro,-z,now', '-lgbm', '-ldrm', '-lEGL', '-lGLESv2', '-lm', '-lpthread',
                '-lc', '-lgcc', '-lgcc_s', run(compiler, '-print-file-name=crtendS.o').strip(),
                str(SYSROOT / 'usr/lib/crtn.o'), '-o', str(binary)]
    result = subprocess.run(command, capture_output=True, text=True)
    (OUTPUT / 'build.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    run('arm-linux-gnueabihf-strip', binary)
    binary.chmod(0o755)
    elf = run('arm-linux-gnueabihf-readelf', '-hAlWd', binary)
    (OUTPUT / 'elf.txt').write_text(elf)
    assert 'Machine:                           ARM' in elf
    assert '/lib/ld-linux-armhf.so.3' in elf
    assert 'Tag_ABI_VFP_args: VFP registers' in elf
    assert all(name in elf for name in ('libgbm.so.1', 'libdrm.so.2', 'libEGL.so.1', 'libGLESv2.so.2'))
    imports = run('arm-linux-gnueabihf-readelf', '--dyn-syms', '-W', binary)
    (OUTPUT / 'imports.txt').write_text(imports)
    usage = None
    if QEMU:
        usage = subprocess.run([str(QEMU), '-L', str(SYSROOT), str(binary), '--help'],
                               capture_output=True, text=True, timeout=15)
        (OUTPUT / 'usage-qemu.txt').write_text(usage.stdout + usage.stderr)
        assert 'Usage:' in usage.stdout and '--count=N' in usage.stdout and '--nonblocking' in usage.stdout
        missing = [line for line in usage.stderr.splitlines() if 'not found' in line or 'symbol lookup error' in line]
        assert not missing, missing
    receipt = {'status': 'CROSS_BUILT_HELP_RUN_NOT_HARDWARE_TESTED' if QEMU else 'CROSS_BUILT_ELF_CHECKED_HELP_UNTESTED',
               'upstream': 'https://gitlab.freedesktop.org/mesa/kmscube', 'commit': COMMIT,
               'archive': archive.relative_to(PROJECT).as_posix(), 'archive_sha256': sha(archive),
               'binary': binary.name, 'binary_sha256': sha(binary),
               'binary_bytes': binary.stat().st_size, 'sources': {name: sha(source / name) for name in SOURCES},
               'compiler': run(compiler, '--version').splitlines()[0],
               'sysroot': str(SYSROOT), 'build_command': command,
               'runtime_libraries': ['libgbm.so.1', 'libdrm.so.2', 'libEGL.so.1', 'libGLESv2.so.2', 'libm.so.6', 'libc.so.6'],
               'optional_features': {'GLES3': False, 'libpng': False, 'GStreamer': False},
               'usage_exit_code': usage.returncode if usage else None,
               'suggested_command': 'timeout -k 5 90 ./kmscube.armv7h -D /dev/dri/card1 -M smooth -f RG16 -v 800x1280 -N -c 1800',
               'two_buffer_command': 'timeout -k 5 90 ./kmscube.armv7h -D /dev/dri/card1 -M smooth -f RG16 -v 800x1280 -x -m 0 -N -c 1800',
               'display_state_restored_by_upstream': False, 'hardware_tested': False}
    (OUTPUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({key: receipt[key] for key in ('status', 'binary', 'binary_sha256', 'binary_bytes')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sysroot', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qemu', type=Path)
    args = parser.parse_args()
    SYSROOT, WORK, OUTPUT, QEMU = args.sysroot.resolve(), args.work.resolve(), args.output.resolve(), args.qemu
    build()
