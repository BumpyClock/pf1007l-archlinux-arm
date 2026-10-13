# AXP223 provider for standard Wi-Fi power sequencing

The replacement `axp20x_regulator` module keeps the accepted
`pf1007l,axp223-active` PMIC behavior. The PMIC node at
`/soc/rsb@1f03400/pmic@3a3` can opt in with:

```dts
photoframe,standard-wifi-power-sequence;
```

For that node and AXP223 only, DLDO1 and DLDO2 use their original regulator
descriptors and regulator-core initialization. Their device-tree constraints
can therefore set 3,300,000 µV and `regulator-always-on`. LDO_IO1 keeps the
existing demand-only guard. Without the property, all three rails keep the
accepted demand-only behavior. Other PMIC variants and compatible strings
receive no new regulator behavior.

This does not replace the custom MFD or AXP GPIO provider. Their cold-start,
interrupt, GPIO-cell, and frequency protections remain in place. The external
module has the same name and kernel release as the installed provider; it
must replace the existing file at boot, not load alongside it. Do not unload
the live regulator provider.

## Build and checks

The full [kernel rebuild](../../README.md) installs this provider source into the kernel tree before compilation. Use that recipe for a matched kernel and module set.

For a provider-only experiment against an existing accepted build:

```sh
python3 kernel/standard-power/provider/prepare.py
python3 kernel/standard-power/provider/test-provider.py
bash kernel/standard-power/provider/build.sh /path/to/linux-7.2.10 /path/to/accepted-build /path/to/new-provider-work
```

`prepare.py` verifies the baseline at `kernel/overlay/drivers/regulator/axp20x-regulator.c` and reproduces the saved source and two-hunk patch. `build.sh` requires the accepted configuration and export table; its only configuration normalization is the external firmware directory. It copies the accepted build into a new workspace, without changing the original build, then compiles the provider as an external module. Evidence is written under the new workspace's `evidence/` directory.

`test-provider.py` compiles the actual guard and checks 40 cases: both flag values, both compatible states, AXP223 and another variant, the two Wi-Fi rails, LDO_IO1, and unrelated rails. Demand init, demand enable, and active-PMIC frequency protections must remain unchanged. `audit-provider.py` checks module identity, vermagic, resolved imports, export table, unchanged configuration, and clean modpost output.

The build receipt reports `hardware_verified: false` and `deployed: false`. These checks do not establish a hardware boot. Install a replacement only as part of a reviewed update; never unload the live regulator provider.
