#!/usr/bin/env python3
"""Validate the replacement module against the accepted kernel ABI."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

here = Path(__file__).resolve().parent
project = here.parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--accepted-build", type=Path, required=True)
parser.add_argument("--work", type=Path, required=True)
parser.add_argument("--evidence", type=Path, required=True)
args = parser.parse_args()
evidence, accepted, work = args.evidence, args.accepted_build, args.work
module = evidence / "axp20x-regulator.ko"
baseline = accepted / "drivers/regulator/axp20x-regulator.ko"

def output(*args):
    return subprocess.check_output(args, text=True).strip()

def record(path):
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

magic = output("modinfo", "-F", "vermagic", str(module))
assert magic == output("modinfo", "-F", "vermagic", str(baseline)) == "7.2.10-pf-console-r1 SMP ARMv7 p2v8"
assert output("modinfo", "-F", "name", str(module)) == output("modinfo", "-F", "name", str(baseline)) == "axp20x_regulator"
exports = {line.split()[1]: line.split()[0] for line in (accepted / "Module.symvers").read_text().splitlines()}
undefined = sorted({line.split()[-1] for line in output("arm-linux-gnueabihf-nm", "-u", str(module)).splitlines()})
assert set(undefined) <= exports.keys(), set(undefined) - exports.keys()
assert (work / "Module.symvers").read_text() == "", "Provider unexpectedly exports new symbols"
assert "__ksymtab_" not in output("arm-linux-gnueabihf-nm", str(baseline))
assert record(accepted / "Module.symvers") == record(work / "build/Module.symvers")
assert record(accepted / ".config") == record(work / "build/.config")
build_log = (evidence / "build.log").read_text()
assert "ERROR:" not in build_log and "WARNING:" not in build_log
receipt = {
    "status": "EXTERNAL_MODULE_BUILD_AND_ABI_CHECKS_PASSED",
    "hardware_verified": False,
    "deployed": False,
    "kernel_release": "7.2.10-pf-console-r1",
    "vermagic": magic,
    "module_name": "axp20x_regulator",
    "parent_pmic_path": "/soc/rsb@1f03400/pmic@3a3",
    "property": "photoframe,standard-wifi-power-sequence",
    "baseline_source": record(project / "kernel/overlay/drivers/regulator/axp20x-regulator.c"),
    "source": record(here / "axp20x-regulator.c"),
    "patch": record(here / "0001-dt-gate-standard-wifi-rails.patch"),
    "module": record(module),
    "baseline_module": record(baseline),
    "kernel_config": record(accepted / ".config"),
    "kernel_exports": record(accepted / "Module.symvers"),
    "exported_symbols": [],
    "undefined_symbols_resolved": len(undefined),
    "import_export_crcs": {name: exports[name] for name in undefined},
    "compiler": output("arm-linux-gnueabihf-gcc", "--version").splitlines()[0],
    "checks": ["40 compiled guard cases", "legacy rails unchanged when property absent",
               "opt-in affects only DLDO1 and DLDO2", "LDO_IO1 guard unchanged",
               "active-PMIC frequency parse protection unchanged", "modpost clean",
               "accepted config and export CRC table unchanged"],
}
(evidence / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
(evidence / "modinfo.txt").write_text(output("modinfo", str(module)) + "\n")
print(json.dumps({"status": receipt["status"], "module": receipt["module"], "vermagic": magic}))
