#!/usr/bin/env bash
set -euo pipefail
recipe="$(cd "$(dirname "$0")" && pwd)"
project="$(cd "$recipe/../../.." && pwd)"
kernel=$(realpath "${1:?usage: build.sh KERNEL-SOURCE ACCEPTED-BUILD NEW-WORK}")
accepted=$(realpath "${2:?accepted kernel build required}")
work=${3:?new module workspace required}
[[ ! -e "$work" && ! -L "$work" ]]
python3 - "$project" "$accepted" <<'PY'
import hashlib,re,sys
from pathlib import Path
project,accepted=map(Path,sys.argv[1:])
normalize=lambda text: re.sub(r'(?m)^CONFIG_EXTRA_FIRMWARE_DIR=.*$', 'CONFIG_EXTRA_FIRMWARE_DIR="firmware"', text)
assert normalize((accepted/'.config').read_text()) == (project/'kernel/config/config').read_text(), 'Accepted configuration differs'
assert hashlib.sha256((accepted/'Module.symvers').read_bytes()).hexdigest() == 'e2e04f8aa2b9be61e98bee7085466d47f5846e4cb83573a3ac844e2f7e83667a'
assert (accepted/'include/config/kernel.release').read_text().strip() == '7.2.10-pf-console-r1'
PY
mkdir -p "$work/evidence"
work=$(realpath "$work")
evidence="$work/evidence"
cp -a --reflink=auto "$accepted" "$work/build"
cp "$recipe/"{Makefile,axp20x-regulator.c} "$work/"
python3 "$recipe/test-provider.py" > "$evidence/test-provider.txt" 2>&1
export KBUILD_BUILD_USER=builder KBUILD_BUILD_HOST=pf1007l-console
export KBUILD_BUILD_TIMESTAMP='2026-10-12 00:00:00 UTC' KBUILD_BUILD_VERSION=1
timeout 300 make -j2 -C "$kernel" O="$work/build" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- M="$work" modules > "$evidence/build.log" 2>&1
cmp "$accepted/.config" "$work/build/.config"
cmp "$accepted/Module.symvers" "$work/build/Module.symvers"
install -m644 "$work/axp20x-regulator.ko" "$evidence/"
python3 "$recipe/audit-provider.py" --accepted-build "$accepted" --work "$work" --evidence "$evidence"
