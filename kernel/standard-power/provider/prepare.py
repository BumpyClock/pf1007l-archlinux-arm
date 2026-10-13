#!/usr/bin/env python3
"""Derive the DT-gated regulator provider from the preserved baseline."""
import difflib
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
BASELINE = PROJECT / "kernel/overlay/drivers/regulator/axp20x-regulator.c"
assert hashlib.sha256(BASELINE.read_bytes()).hexdigest() == "d839e04530ab77596faad45750b36bf53742c48c187379eac0a8e4181e783cb5"
baseline = BASELINE.read_text()
declaration = "\tbool drivevbus = false;"
guard = "(i == AXP22X_DLDO1 || i == AXP22X_DLDO2 || i == AXP22X_LDO_IO1)) {"
assert baseline.count(declaration) == baseline.count(guard) == 1
updated = baseline.replace(declaration, declaration + '''
\tbool standard_wifi_power_sequence = of_property_read_bool(
\t\tpdev->dev.parent->of_node,
\t\t"photoframe,standard-wifi-power-sequence");''').replace(guard, '''(i == AXP22X_LDO_IO1 ||
\t\t     (!standard_wifi_power_sequence &&
\t\t      (i == AXP22X_DLDO1 || i == AXP22X_DLDO2)))) {''')
(HERE / "axp20x-regulator.c").write_text(updated, newline="\n")
(HERE / "0001-dt-gate-standard-wifi-rails.patch").write_text("".join(
    difflib.unified_diff(baseline.splitlines(True), updated.splitlines(True),
                        fromfile="a/drivers/regulator/axp20x-regulator.c",
                        tofile="b/drivers/regulator/axp20x-regulator.c")), newline="\n")
