# Rebuild the qualified kernel and drivers

This recipe rebuilds Linux `7.2.10-pf-console-r1` for the qualified PF1007L board. It uses the pinned upstream archive, all twelve measured source deltas, the production Silead touch driver, the standard-power AXP223 provider, and the pinned AIC8800 source tree. It does not deploy files, change an SD card, or access a live frame.

The [source manifest](source-manifest.json) records the Linux archive and baseline source hashes. `rebuild.py` also pins the portable config, accepted export table, final touch/provider overrides, complete board DTS, and AIC driver tree. The standard MMC/regulator power path replaces the old custom power-sequence module; that obsolete module is not built.

## Inputs and tools

Run on Linux or Linux inside WSL. Use a Linux filesystem for the build workspace, with a simple path containing letters, digits, slash, dot, underscore or hyphen. Required tools include Python 3.12 or newer, GNU make, GCC host tools, `arm-linux-gnueabihf-gcc`, binutils, flex, bison, OpenSSL development headers, `dtc`, and `depmod` with the `-m` modules-directory option. The development build used GCC 15.2.0. Changing the compiler can change binary hashes even when source and configuration match.

Supply these inputs outside Git:

- The authenticated `linux-7.2.10.tar.xz` archive with SHA-256 `2feaa70453e91f541be6a5c9078d8168e081af45a3d9718054850538cff2ebf3`.
- The matching `sq9365-private-table.h` with SHA-256 `d7412abb703bdd7927b610f36f1451c6ceafdf6ad6fc8cc7476d6e8efdf3cc72`.
- A firmware directory containing every `firmware/` entry in [required-inputs.json](../firmware/required-inputs.json). Pass the directory **inside** which files such as `regulatory.db` and `silead/pf1007l-gsl-m86-hd.fw` reside; do not add an extra `firmware/` nesting level.

See [external firmware extraction](../firmware/README.md) for obtaining the panel and touch inputs from your own matching Android modules. The saved panel source says “do not redistribute”; the external header stays outside this repository. Review radio firmware permissions separately. The kernel archive's URL, signature URL and signer fingerprints are recorded in the source manifest; authenticate the download against trusted upstream information before using it.

All declared firmware inputs are checked before extraction, including the radio firmware and regulatory files. Missing or changed firmware, source overlays, final overrides or the AIC tree cause a failure. Existing workspaces are rejected, so an earlier build cannot be overwritten.

## Prepare and inspect

```sh
python3 kernel/rebuild.py \
  --archive /private/downloads/linux-7.2.10.tar.xz \
  --panel-header /private/pf1007l-inputs/sq9365-private-table.h \
  --firmware-dir /private/pf1007l-firmware \
  --work /private/builds/pf1007l-source-check \
  --prepare-only
```

This extracts a new source tree, verifies each upstream file before applying its baseline delta, applies the final touch and power-provider overrides, copies the pinned AIC tree and external firmware, and prepares the accepted configuration. Only `CONFIG_EXTRA_FIRMWARE_DIR` changes to the new workspace's firmware directory. No kernel compilation or installation occurs in this mode.

Inspect `receipt.json`, `linux-7.2.10/`, `build/.config` and `firmware/` in that workspace. The workspace contains private hardware inputs; do not commit it or publish its source tree without reviewing those inputs.

## Build a matching kernel and module set

Use another new workspace:

```sh
python3 kernel/rebuild.py \
  --archive /private/downloads/linux-7.2.10.tar.xz \
  --panel-header /private/pf1007l-inputs/sq9365-private-table.h \
  --firmware-dir /private/pf1007l-firmware \
  --work /private/builds/pf1007l-kernel \
  --jobs 4
```

The recipe uses `ARCH=arm` and `CROSS_COMPILE=arm-linux-gnueabihf-`, with the qualified build identity (`builder`, `pf1007l-console`, version `1`, timestamp `2026-10-12 00:00:00 UTC`). It runs `olddefconfig`, verifies the exact kernel release, compiles `zImage` and every configured module, then builds both AIC8800 modules with the accepted flags. The complete hardware DTS is compiled with `dtc`.

The built export table must match the accepted [Module.symvers](config/Module.symvers). `depmod` must report no unresolved module dependencies. This configuration has `CONFIG_MODVERSIONS` disabled; the export-table check does not provide CRC-based compatibility with an arbitrary different kernel. Build and install the complete matching set.

Outputs include:

| Path inside the new workspace | Purpose |
| --- | --- |
| `zImage` | Rebuilt kernel |
| `sun8i-a33-pf1007l-stage1.dtb` | Complete standard-power board DT |
| `root-overlay/usr/lib/modules/7.2.10-pf-console-r1/` | Matching kernel, touch, regulator, display, GPU, USB and AIC modules with dependency metadata |
| `receipt.json` | Input pins, output hashes, compiler and qualification status |
| `*.log` | Configuration, compilation, module install, DT compilation and dependency checks |

These outputs are not a complete boot bundle. Preserve the portable image's own initramfs, root UUID and storage guards when preparing a new update; the original overlay reference initramfs is incompatible with the portable ext4 root. A new launcher must reference its new profile directory and updated payload lengths/hashes. The [serial installer](../tools/README.md) requires the four boot payloads and `SHA256SUMS`, and verifies them before selection. Never substitute a kernel without its matching module set.

## Checks and limits

```sh
python3 kernel/tests/test_rebuild.py
python3 kernel/standard-power/provider/test-provider.py
```

The source-preparation tests cover all twelve deltas, final overrides, external firmware, missing/changed input rejection, upstream-content checks, archive traversal rejection and preservation of existing workspaces. Provider tests exercise forty compiled regulator-guard cases. See [provider-only builds](standard-power/provider/README.md) for a bounded replacement-module experiment against an accepted existing build.

The preserved complete DTS uses numeric phandle values, so `dtc` emits reference-format warnings; they are retained in `dtc.log`. The rebuilt DT was compared property by property with the qualified DT and had no semantic changes.

A host rebuild is separate from a hardware boot. Its receipt always reports `hardware_verified: false` and `deployed: false`. The portable image's first-boot wizard, filesystem expansion and USB update path still need qualification on a spare card before a public release is called hardware-tested.
