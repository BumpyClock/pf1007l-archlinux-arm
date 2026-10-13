#!/usr/bin/env python3
"""Rebuild the pinned SD-only PF1007L U-Boot loader in a new workspace."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
BOOTCOMMAND = '"if fatload mmc 0:1 0x43100000 boot-control.scr; then source 0x43100000; fi; while true; do sleep 60; done"'
ENABLED = {"DRAM_CLK": "456", "DRAM_ZQ": "15291", "AXP221_POWER": "y", "SYS_CLK_FREQ": "1008000000",
           "AXP_DCDC1_VOLT": "3000", "AXP_DCDC2_VOLT": "1100", "AXP_DCDC3_VOLT": "1200",
           "AXP_DCDC4_VOLT": "0", "AXP_DCDC5_VOLT": "1500", "MMC_SUNXI_SLOT_EXTRA": "-1",
           "SYS_MMC_MAX_BLK_COUNT": "128", "ENV_IS_NOWHERE": "y", "BOOTDELAY": "-2",
           "PREBOOT": '""', "BOOTCOMMAND": BOOTCOMMAND, "CMD_SOURCE": "y", "CMD_FAT": "y",
           "FAT_WRITE": "y", "CMD_HASH": "y", "SHA256": "y", "CMD_SETEXPR": "y", "CMD_GETTIME": "y",
           "CMD_SLEEP": "y", "HUSH_PARSER": "y", "NO_NET": "y", "SPL_STACK": "0x8000",
           "SPL_MAX_SIZE": "0x5fa0", "DEFAULT_DEVICE_TREE": '"sun8i-a33-sinlinx-sina33"'}
DISABLED = ("DRAM_ODT_EN", "SUNXI_NO_PMIC", "CMD_SAVEENV", "CMD_ERASEENV", "MMC_HW_PARTITIONING",
            "SUPPORT_EMMC_BOOT", "CMD_MMC_RPMB", "CMD_BKOPS_ENABLE", "CMD_MMC_SWRITE", "SPL_MMC_WRITE",
            "BOOTCOUNT_LIMIT", "USB_EHCI_HCD", "USB_OHCI_HCD", "USB_KEYBOARD", "CMD_FASTBOOT",
            "FASTBOOT", "EXT4_WRITE", "USB_GADGET", "VIDEO", "NET")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def config_values(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            require(key not in values, "Duplicate config key")
            values[key] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            values[line[2:-11]] = "n"
    return values


def check_config(path):
    values = config_values(path)
    for name, value in ENABLED.items():
        require(values.get("CONFIG_" + name) == value, "Required loader configuration differs: " + name)
    for name in DISABLED:
        require(values.get("CONFIG_" + name, "n") == "n", "Unsafe loader feature enabled: " + name)
    require(not any("_ENV_IS_IN_" in key and value == "y" for key, value in values.items()), "Persistent environment enabled")
    return values


def validate_image(path):
    data = path.read_bytes()
    require(len(data) >= 0x6000 and len(data) + 8192 <= 1048576, "Loader image exceeds reserved bootstrap area")
    branch, checksum, length = struct.unpack_from("<I8xII", data)
    require(branch & 0xff000000 == 0xea000000 and data[4:12] == b"eGON.BT0", "Invalid ARM eGON SPL header")
    require(512 <= length <= 0x6000 and length % 512 == 0, "Unexpected SPL padded length")
    words = list(struct.unpack("<%dI" % (length // 4), data[:length]))
    words[3] = 0x5f0a6c39
    require(sum(words) & 0xffffffff == checksum, "Invalid eGON SPL checksum")
    end = max(index for index, byte in enumerate(data[:0x6000]) if byte) + 1
    require(end <= 0x5e00, "SPL exceeds the qualified safe stack margin")
    return {"bytes": len(data), "sha256": sha(path), "spl_padded_length": length, "spl_last_nonzero_end": end,
            "spl_stack_margin_check_passed": True, "egon_checksum_valid": True}


def verify_inputs(here, manifest):
    for item in manifest["files"]:
        relative = PurePosixPath(item["path"])
        require(not relative.is_absolute() and ".." not in relative.parts, "Manifest path escapes source inputs")
        path = here.joinpath(*relative.parts)
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == item["bytes"] and sha(path) == item["sha256"], "Pinned loader input differs: " + item["path"])
    check_config(here / "accepted.config")


def download_archive(work, manifest):
    upstream = manifest["upstream"]
    checkout = work / "upstream-git"
    subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1", "--branch", "v2025.10", upstream["repository"], str(checkout)], check=True)
    commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "v2025.10^{commit}"], text=True).strip()
    require(commit == upstream["commit"], "Upstream release tag differs from the pinned commit")
    archive = work / "u-boot-v2025.10.tar"
    subprocess.run(["git", "-C", str(checkout), "archive", "--format=tar", "--output=" + str(archive), commit], check=True)
    return archive


def extract(archive, destination):
    with tarfile.open(archive, "r:") as source:
        for item in source.getmembers():
            path = PurePosixPath(item.name)
            require(not path.is_absolute() and ".." not in path.parts, "Archive path escapes source root")
            require(item.isdir() or item.isfile() or item.issym() or item.islnk(), "Archive contains a special device")
        source.extractall(destination, filter="data")


def prepare_source(archive, work, here, manifest):
    require(archive.is_file() and sha(archive) == manifest["upstream"]["archive_sha256"], "Pinned git archive differs")
    source = work / "src"
    source.mkdir()
    extract(archive, source)
    for name in ("boot-control-sd-only.patch", "a33-gettime-env.patch"):
        subprocess.run(["git", "-C", str(source), "apply", "--check", str(here / name)], check=True)
        subprocess.run(["git", "-C", str(source), "apply", str(here / name)], check=True)
    board = source / "arch/arm/dts/sun8i-a33-sinlinx-sina33.dts"
    with board.open("a") as stream:
        stream.write("\n" + (here / "board-isolation.dtsi").read_text())
    mmc = (source / "drivers/mmc/sunxi_mmc.c").read_text()
    for guard in ("sdc_no != 0", "dev_read_addr(dev) != SUNXI_MMC0_BASE", "(ulong)priv->reg != SUNXI_MMC0_BASE || !IS_SD(mmc)", "cmd->cmdidx == MMC_CMD_ERASE"):
        require(guard in mmc, "SD controller/write isolation guard missing")
    require('return env_set_hex(argv[1], val);' in (source / "cmd/gettime.c").read_text(), "Candidate timer command patch missing")
    return source


def configure_and_build(source, work, here, manifest, jobs, prepare_only):
    build = work / "build"
    build.mkdir()
    environment = dict(os.environ, CROSS_COMPILE="arm-linux-gnueabihf-", ARCH="arm", SOURCE_DATE_EPOCH=str(manifest["source_date_epoch"]), TZ="UTC", LC_ALL="C")
    make = ["make", "-C", str(source), "O=" + str(build), "CROSS_COMPILE=arm-linux-gnueabihf-"]
    def run(command, name, cwd=None):
        with (work / name).open("a") as log:
            subprocess.run(command, env=environment, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
    run(make + ["Sinlinx_SinA33_defconfig"], "configure.log")
    run([str(source / "scripts/kconfig/merge_config.sh"), "-m", "-O", str(build), str(build / ".config"), str(here / "base.config")], "configure.log", source)
    command = [str(source / "scripts/config"), "--file", str(build / ".config")]
    for name, value in (("DRAM_CLK", "456"), ("DRAM_ZQ", "15291"), ("MMC_SUNXI_SLOT_EXTRA", "-1"), ("SYS_MMC_MAX_BLK_COUNT", "128"), ("BOOTDELAY", "-2")):
        command += ["--set-val", name, value]
    command += ["--enable", "CMD_GETTIME"]
    for name in DISABLED:
        command += ["--disable", name]
    command += ["--set-str", "PREBOOT", "", "--set-str", "BOOTCOMMAND", BOOTCOMMAND[1:-1]]
    run(command, "configure.log")
    run(make + ["olddefconfig"], "configure.log")
    accepted = check_config(here / "accepted.config")
    actual = check_config(build / ".config")
    require(actual == accepted, "Configured options differ from the complete accepted configuration")
    receipt = {"status": "PINNED_LOADER_CONFIGURED", "upstream_commit": manifest["upstream"]["commit"],
               "archive_sha256": manifest["upstream"]["archive_sha256"], "input_files": manifest["files"],
               "configuration_sha256": sha(build / ".config"), "accepted_configuration_options_match": True,
               "source_date_epoch": manifest["source_date_epoch"], "hardware_verified": False, "deployed": False,
               "kernel_provides_usb_serial": True, "uboot_usb_gadget_enabled": False, "mmc1_mmc2_disabled": True,
               "sd_only_write_guard_enabled": True, "reference_binary": manifest["reference_binary"]}
    if not prepare_only:
        run(make + ["-j" + str(jobs)], "build.log")
        binary = work / "u-boot-sunxi-with-spl.bin"
        shutil.copyfile(build / binary.name, binary)
        receipt.update(status="LOADER_BUILT_AND_SAFETY_CHECKED", output=validate_image(binary),
                       compiler=subprocess.check_output(["arm-linux-gnueabihf-gcc", "--version"], text=True).splitlines()[0])
        receipt["matches_reference_binary_sha256"] = receipt["output"]["sha256"] == manifest["reference_binary"]["sha256"]
        for controller in ("mmc@1c10000", "mmc@1c11000"):
            value = subprocess.check_output(["fdtget", "-t", "s", str(build / "u-boot.dtb"), "/soc/" + controller, "status"], text=True).strip()
            require(value == "disabled", "U-Boot enabled a non-SD controller")
        receipt["compiled_mmc1_mmc2_disabled"] = True
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--archive", type=Path)
    inputs.add_argument("--download", action="store_true")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--prepare-only", action="store_true", help="prepare source and qualify configuration without compiling the loader")
    args = parser.parse_args()
    require(args.jobs > 0, "Jobs must be positive")
    work = args.work.absolute()
    require(not work.exists() and not work.is_symlink(), "Use a new workspace; existing builds are never overwritten")
    require(re.fullmatch(r'[A-Za-z0-9_./-]+', str(work)), "Use a simple native build path without spaces or shell metacharacters")
    manifest = json.loads((HERE / "source-manifest.json").read_text())
    verify_inputs(HERE, manifest)
    for tool in ("git", "make", "arm-linux-gnueabihf-gcc", "fdtget"):
        require(shutil.which(tool), "Build tool missing: " + tool)
    if args.archive:
        archive = args.archive.resolve()
        require(archive.is_file() and sha(archive) == manifest["upstream"]["archive_sha256"], "Pinned git archive differs")
    work.mkdir(parents=True)
    if args.download:
        archive = download_archive(work, manifest)
    source = prepare_source(archive, work, HERE, manifest)
    receipt = configure_and_build(source, work, HERE, manifest, args.jobs, args.prepare_only)
    print(json.dumps({"status": receipt["status"], "hardware_verified": False, "deployed": False}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        raise SystemExit(str(error)) from error
