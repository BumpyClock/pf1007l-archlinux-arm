#!/usr/bin/env python3
"""Compile the actual provider guard and exercise its opt-in boundary."""
import re
import subprocess
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent
source = (here / "axp20x-regulator.c").read_text()
baseline = (here.parents[2] / "kernel/overlay/drivers/regulator/axp20x-regulator.c").read_text()
guard = re.search(r"\t\tif \((axp20x->variant == AXP223_ID &&.*?)\) \{\n\t\t\tstruct regulator_ops \*ops;", source, re.S).group(1)
body = '''
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define AXP223_ID 223
#define AXP22X_DLDO1 1
#define AXP22X_DLDO2 2
#define AXP22X_LDO_IO1 3
struct node { bool compatible; };
struct device { struct node *of_node; };
struct platform_device { struct { struct device *parent; } dev; };
struct axp20x_dev { int variant; };
static bool of_device_is_compatible(struct node *node, const char *name) {
    return strcmp(name, "pf1007l,axp223-active") == 0 && node->compatible;
}
static bool uses_guard(int variant, bool compatible, bool standard_wifi_power_sequence, int i) {
    struct node node = { compatible };
    struct device parent = { &node };
    struct platform_device dev = { { &parent } }, *pdev = &dev;
    struct axp20x_dev chip = { variant }, *axp20x = &chip;
    return GUARD;
}
int main(void) {
    int checks = 0;
    for (int variant = 222; variant <= 223; ++variant)
    for (int compatible = 0; compatible <= 1; ++compatible)
    for (int standard = 0; standard <= 1; ++standard)
    for (int rail = 0; rail <= 4; ++rail) {
        const bool legacy[] = { false, true, true, true, false };
        const bool opted_in[] = { false, false, false, true, false };
        bool expected = variant == 223 && compatible &&
                        (standard ? opted_in[rail] : legacy[rail]);
        if (uses_guard(variant, compatible, standard, rail) != expected)
            return 1;
        ++checks;
    }
    printf("PASS: %d compiled guard cases; LDO_IO1 remains guarded.\\n", checks);
    return 0;
}
'''.replace("GUARD", guard)
for name in ("pf1007l_demand_regulator_init", "pf1007l_demand_regulator_enable"):
    pattern = rf"static int {name}\(.*?\n\}}"
    assert re.search(pattern, source, re.S).group() == re.search(pattern, baseline, re.S).group()
assert 'pdev->dev.parent->of_node,\n\t\t"photoframe,standard-wifi-power-sequence"' in source
assert source[source.index("\t/* Preserve the measured bootloader frequency"):source.index("\tfor (i = 0;")] == baseline[baseline.index("\t/* Preserve the measured bootloader frequency"):baseline.index("\tfor (i = 0;")]
with tempfile.TemporaryDirectory() as work:
    fixture = Path(work) / "guard.c"
    fixture.write_text(body)
    executable = Path(work) / "guard"
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(fixture), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print("PASS: demand init/enable and active-PMIC frequency protections unchanged.")
