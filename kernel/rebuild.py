#!/usr/bin/env python3
"""Prepare and build the pinned PF1007L kernel without deploying it."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile

REPO = Path(__file__).resolve().parents[1]
RELEASE = "7.2.10-pf-console-r1"
PINS = {
    "kernel/config/config": "b1bd0b240f5bfe72a3d7a6844211658deb11f1d0c81a17d4dd9d778061dfd555",
    "kernel/config/Module.symvers": "e2e04f8aa2b9be61e98bee7085466d47f5846e4cb83573a3ac844e2f7e83667a",
    "kernel/production-touch/silead.c": "da36d66d13546695ed1d8be1df385a14990807b330ab3bbac000670d5c95cdaf",
    "kernel/standard-power/provider/axp20x-regulator.c": "5e466eedca1d784611d28938f7e630495f7924ac02f74acefbe789a85cb82ec7",
    "hardware/pf1007l-standard-wifi.dts": "500ba59e3b4ba4bf7fcfceed10772e0d89b38b86a6b86a82768332f3da4ec8ed",
    "drivers/aic8800-port.patch": "9c5fa23bc1133eca35bbaec7703359b1e19e73b2c28b7749fcb86de3898cc7bc",
}
AIC_TREE_SHA256 = "31c4edc1c7b3e2ac8cbe8ea425f4ffa2a49cd0d8b8342a6bb1275b712a3dc536"
AIC_FLAGS = [
    "CONFIG_AIC8800_BTLPM_SUPPORT=n", "CONFIG_AIC8800_WLAN_SUPPORT=m", "CONFIG_AIC_WLAN_SUPPORT=m",
    "CONFIG_PLATFORM_ALLWINNER=n", "CONFIG_PLATFORM_ROCKCHIP=n", "CONFIG_PLATFORM_ROCKCHIP2=n",
    "CONFIG_PLATFORM_AMLOGIC=n", "CONFIG_PLATFORM_UBUNTU=y", "CONFIG_USE_FW_REQUEST=y",
    "CONFIG_RESV_MEM_SUPPORT=n", "CONFIG_OOB=n", "CONFIG_GPIO_WAKEUP=n", "CONFIG_SDIO_BT=n",
    "CONFIG_USB_BT=n", "CONFIG_RFTEST=n", "CONFIG_DPD=y", "CONFIG_FORCE_DPD_CALIB=y",
    "CONFIG_SDIO_PWRCTRL=y", "CONFIG_PREALLOC_RX_SKB=n", "CONFIG_PREALLOC_TXQ=n",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree_sha(directory):
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*"), key=lambda path: path.relative_to(directory).as_posix()):
        require(not path.is_symlink(), "AIC source contains a symlink")
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode() + b"\0" + bytes.fromhex(sha(path)) + b"\n")
    return digest.hexdigest()


def relative_path(value):
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and str(path) == value, "Invalid manifest path")
    return Path(*path.parts)


def validate_inputs(repo, archive, panel_header, firmware_dir, manifest, pins=PINS, aic_pin=AIC_TREE_SHA256):
    require(manifest["archive"]["version"] == "7.2.10", "Kernel version differs")
    require(len(manifest["delta"]) == 12, "Expected all twelve measured source deltas")
    firmware_manifest = json.loads((repo / "firmware/required-inputs.json").read_text())
    firmware = []
    private_headers = 0
    for entry in firmware_manifest["files"]:
        relative = relative_path(entry["path"])
        if relative.parts[0] == "firmware":
            path = firmware_dir.joinpath(*relative.parts[1:])
            firmware.append((Path(*relative.parts[1:]), path))
        else:
            require(entry["path"] == "kernel-overlay/drivers/gpu/drm/panel/sq9365-private-table.h", "Unknown external input")
            path = panel_header
            private_headers += 1
        require(path.is_file() and not path.is_symlink(), "Required external firmware input missing: " + entry["path"])
        require(path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"], "External firmware input differs: " + entry["path"])
    require(private_headers == 1, "Expected one external panel header")
    for name, expected in pins.items():
        path = repo / relative_path(name)
        require(path.is_file() and sha(path) == expected, "Pinned repository input differs: " + name)
    require(tree_sha(repo / "drivers/aic8800") == aic_pin, "Pinned AIC driver tree differs")
    saved = {}
    for entry in manifest["delta"]:
        relative = relative_path(entry["path"])
        require(relative not in saved, "Duplicate source delta")
        path = panel_header if entry.get("private") else repo / "kernel/overlay" / relative
        require(path.is_file() and sha(path) == entry["sha256"], "Pinned baseline delta differs: " + entry["path"])
        require(entry["kind"] in ("modified", "added"), "Unknown source delta kind")
        saved[relative] = path
    require(archive.is_file() and sha(archive) == manifest["archive"]["archive_sha256"], "Authenticated upstream archive differs")
    return saved, firmware


def extract_source(archive, work):
    with tarfile.open(archive, "r:xz") as package:
        for member in package.getmembers():
            path = PurePosixPath(member.name)
            require(not path.is_absolute() and ".." not in path.parts and path.parts[0] == "linux-7.2.10", "Archive path escapes source root")
            require(member.isdir() or member.isfile() or member.issym() or member.islnk(), "Archive contains a special device")
        package.extractall(work, filter="data")
    source = work / "linux-7.2.10"
    require(source.is_dir(), "Kernel source root missing")
    return source


def prepare(repo, archive, work, panel_header, firmware_dir, manifest, pins=PINS, aic_pin=AIC_TREE_SHA256):
    require(not work.exists(), "Use a new workspace; existing build directories are never overwritten")
    saved, firmware = validate_inputs(repo, archive, panel_header, firmware_dir, manifest, pins, aic_pin)
    work.mkdir(parents=True)
    source = extract_source(archive, work)
    records = []
    for entry in manifest["delta"]:
        relative = relative_path(entry["path"])
        target = source / relative
        if entry["kind"] == "modified":
            require(target.is_file() and sha(target) == entry["upstream_sha256"], "Upstream source differs: " + entry["path"])
        else:
            require(not target.exists(), "Added source unexpectedly exists upstream: " + entry["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(saved[relative], target)
        records.append({"path": entry["path"], "baseline_sha256": sha(target)})
    overrides = {
        "drivers/input/touchscreen/silead.c": manifest["production_touch_override"],
        "drivers/regulator/axp20x-regulator.c": manifest["standard_power_override"],
    }
    for target, stored in overrides.items():
        require(stored in pins, "Override is not pinned")
        shutil.copyfile(repo / relative_path(stored), source / relative_path(target))
    shutil.copytree(repo / "drivers/aic8800", work / "aic8800")
    for relative, stored in firmware:
        target = work / "firmware" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stored, target)
    build = work / "build"
    build.mkdir()
    configuration = (repo / "kernel/config/config").read_text()
    require(configuration.count('CONFIG_EXTRA_FIRMWARE_DIR="firmware"') == 1, "Portable firmware config entry differs")
    configuration = configuration.replace('CONFIG_EXTRA_FIRMWARE_DIR="firmware"', 'CONFIG_EXTRA_FIRMWARE_DIR="' + str(work / "firmware") + '"')
    require('CONFIG_LOCALVERSION="-pf-console-r1"' in configuration, "Kernel release suffix differs")
    require('# CONFIG_LOCALVERSION_AUTO is not set' in configuration, "Automatic local version must be disabled")
    (build / ".config").write_text(configuration, newline="\n")
    shutil.copyfile(repo / "hardware/pf1007l-standard-wifi.dts", work / "pf1007l-standard-wifi.dts")
    receipt = {
        "status": "PINNED_SOURCE_PREPARED", "kernel_release": RELEASE, "hardware_verified": False, "deployed": False,
        "archive_sha256": sha(archive), "baseline_deltas": records,
        "overrides": {target: {"source": stored, "sha256": sha(source / target)} for target, stored in overrides.items()},
        "aic_tree_sha256": tree_sha(work / "aic8800"),
        "external_inputs": [{"path": relative.as_posix(), "sha256": sha(stored)} for relative, stored in firmware],
        "panel_header_sha256": sha(panel_header), "repository_input_pins": pins,
    }
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return source, build, receipt


def build_kernel(repo, work, source, build, receipt, jobs, cross):
    for tool in ("make", "dtc", "depmod", cross + "gcc", cross + "nm"):
        require(shutil.which(tool), "Build tool missing: " + tool)
    environment = dict(os.environ, ARCH="arm", CROSS_COMPILE=cross, KBUILD_BUILD_USER="builder",
                       KBUILD_BUILD_HOST="pf1007l-console", KBUILD_BUILD_TIMESTAMP="2026-10-12 00:00:00 UTC",
                       KBUILD_BUILD_VERSION="1")
    make = ["make", "-C", str(source), "O=" + str(build), "ARCH=arm", "CROSS_COMPILE=" + cross]
    def run(command, logfile):
        with (work / logfile).open("w") as output:
            subprocess.run(command, env=environment, stdout=output, stderr=subprocess.STDOUT, check=True)
    run(make + ["olddefconfig"], "configure.log")
    release = subprocess.check_output(make + ["-s", "kernelrelease"], env=environment, text=True).strip().splitlines()[-1]
    require(release == RELEASE, "Configured kernel release differs")
    run(make + ["-j" + str(jobs), "zImage", "modules"], "kernel-build.log")
    require(sha(build / "Module.symvers") == PINS["kernel/config/Module.symvers"], "Built export table differs from the accepted ABI")
    staging = work / "module-staging"
    run(make + ["INSTALL_MOD_PATH=" + str(staging), "modules_install"], "modules-install.log")
    driver = work / "aic8800/src/SDIO/driver_fw/driver/aic8800"
    run(make + ["M=" + str(driver), "-j" + str(jobs)] + AIC_FLAGS + ["modules"], "aic-build.log")
    modules = work / "root-overlay/usr/lib/modules" / RELEASE
    modules.parent.mkdir(parents=True)
    shutil.move(str(staging / "lib/modules" / RELEASE), modules)
    for name in ("build", "source"):
        link = modules / name
        if link.is_symlink():
            link.unlink()
    shutil.rmtree(staging)
    extra = modules / "extra"
    extra.mkdir()
    for name in ("aic8800_bsp", "aic8800_fdrv"):
        shutil.copyfile(driver / name / (name + ".ko"), extra / (name + ".ko"))
    run(["depmod", "-b", str(work / "root-overlay"), "-m", "/usr/lib/modules", "-e", "-F", str(build / "System.map"), RELEASE], "depmod.log")
    require(not (work / "depmod.log").read_text().strip(), "depmod reported unresolved module dependencies")
    run(["dtc", "-I", "dts", "-O", "dtb", "-o", str(work / "sun8i-a33-pf1007l-stage1.dtb"), str(work / "pf1007l-standard-wifi.dts")], "dtc.log")
    shutil.copyfile(build / "arch/arm/boot/zImage", work / "zImage")
    artifacts = [work / "zImage", work / "sun8i-a33-pf1007l-stage1.dtb"] + sorted(modules.rglob("*.ko"))
    receipt.update(status="KERNEL_AND_MATCHING_MODULES_BUILT", compiler=subprocess.check_output([cross + "gcc", "--version"], text=True).splitlines()[0],
                   accepted_exports_match=True, custom_manual_pwrseq_built=False,
                   artifacts=[{"path": path.relative_to(work).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in artifacts])
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--panel-header", type=Path, required=True)
    parser.add_argument("--firmware-dir", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--cross-compile", default="arm-linux-gnueabihf-")
    args = parser.parse_args()
    require(args.jobs > 0, "Jobs must be positive")
    args.work = args.work.absolute()
    require(not args.work.is_symlink(), "Workspace must not be a symlink")
    require(re.fullmatch(r'[A-Za-z0-9_./-]+', str(args.work)) is not None, "Use a native workspace path containing only letters, digits, slash, dot, underscore or hyphen")
    manifest = json.loads((REPO / "kernel/source-manifest.json").read_text())
    source, build, receipt = prepare(REPO, args.archive.resolve(), args.work, args.panel_header.resolve(), args.firmware_dir.resolve(), manifest)
    if not args.prepare_only:
        build_kernel(REPO, args.work, source, build, receipt, args.jobs, args.cross_compile)
    print(json.dumps({"status": receipt["status"], "kernel_release": RELEASE, "hardware_verified": False, "deployed": False}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
