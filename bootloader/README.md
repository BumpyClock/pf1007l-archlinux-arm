# SD-only U-Boot loader

This is the corresponding source recipe for the PF1007L loader shipped in the image: U-Boot `2025.10`, commit `e50b1e8715011def8aff1588081a2649a2c6cd47`, with the two local patches and board/configuration inputs in this directory. The qualified reference binary is `443104` bytes with SHA-256 `13784fc9960ce4de553ca166432b17b78116ecff23e9a8bdeaa09596eb1560a6`.

The loader initializes the qualified A33 DRAM and PMIC, loads `boot-control.scr` from SD FAT partition `mmc 0:1`, and runs it. FAT writes remain enabled for diagnostic checkpoints and the candidate/acknowledgement handshake. The MMC driver permits writes only through MMC0 to an SD card, rejects erase commands, and refuses MMC1/MMC2 initialization. Both non-SD controllers are also disabled in its compiled board DT.

There is **no U-Boot USB gadget**, networking or display output. Linux supplies the USB serial `ttyGS0` interface, display and Wi-Fi after the loader hands over. A blank screen or missing COM port before Linux starts is not a U-Boot serial terminal. These patches do not alter the SoC Boot ROM or the Android system on internal eMMC.

## Source inputs

[Source manifest](source-manifest.json) pins:

- The upstream commit and its unprefixed `git archive --format=tar` SHA-256: `1b2ef9bdc0d43518cc78f3be369897791bc8556c77f81cd09973768670a4a098`.
- `boot-control-sd-only.patch`, which limits controller access and SD writes.
- `a33-gettime-env.patch`, which lets the dispatcher store timer ticks in a volatile environment variable.
- `base.config`, merged over `Sinlinx_SinA33_defconfig`.
- `accepted.config`, the complete qualified configuration.
- `board-isolation.dtsi`, appended to the board DTS to disable MMC1/MMC2.

Upstream source is available from [U-Boot](https://source.denx.de/u-boot/u-boot) and its [GitHub mirror at the pinned commit](https://github.com/u-boot/u-boot/tree/e50b1e8715011def8aff1588081a2649a2c6cd47). Upstream license texts are preserved under [Licenses](Licenses/). Keep each source file's original SPDX and copyright notices. The local changes modify GPL-covered U-Boot files; publishing a loader binary must also provide its matching source and build inputs. Do not treat firmware licenses from the Linux image as applying to U-Boot.

The large upstream source tree is downloaded or supplied outside Git. For a release, retain the exact upstream source archive and these local inputs alongside the build evidence; a compressed patched-source archive can accompany the binary release asset.

## Rebuild

Use Linux or Linux inside WSL, Python 3.12 or newer, GNU make, host GCC, Git, flex, bison, OpenSSL development headers, `arm-linux-gnueabihf-gcc`/binutils and `fdtget`. The accepted configuration records GCC 15.2.0; the recipe compares all generated configuration options with that snapshot. A different compiler or configuration needs a reviewed update to the accepted snapshot.

Use a new workspace on a Linux filesystem, with a simple path containing letters, digits, slash, dot, underscore or hyphen. Existing workspaces are rejected. No package installation, SD write or frame access is performed.

With an authenticated existing git archive:

```sh
python3 bootloader/rebuild.py \
  --archive /private/downloads/u-boot-v2025.10.tar \
  --work /private/builds/pf1007l-uboot \
  --jobs 4
```

Or fetch the pinned tag, check its commit and generate the pinned archive:

```sh
python3 bootloader/rebuild.py \
  --download \
  --work /private/builds/pf1007l-uboot \
  --jobs 4
```

`--prepare-only` applies the source changes and qualifies the generated configuration without compiling the loader. The downloaded Git repository and source archive stay in the new workspace; they are not added to this project repository.

The generated configuration must match the complete accepted option set. Explicit checks also require DRAM clock `456 MHz`, ZQ `15291`, ODT disabled, CPU clock `1008000000`, the qualified AXP221 voltages, `MMC_SUNXI_SLOT_EXTRA=-1`, no saved environment, no eMMC partition commands and no U-Boot gadget/network/video features. `BOOTDELAY=-2` runs only the dispatcher command rather than entering interactive autoboot selection.

The recipe uses `SOURCE_DATE_EPOCH=1791827164` and UTC for repeatable build timestamps. The reference binary was built with a local timezone timestamp, recorded in the manifest. A new build can therefore have a different binary hash even with identical source/configuration. Its receipt records whether the output matches the reference; do not call a new binary hardware-qualified based on compilation alone.

## Outputs and safety checks

| Workspace path | Purpose |
| --- | --- |
| `u-boot-sunxi-with-spl.bin` | Combined SPL and U-Boot loader |
| `src/` | Upstream source with both patches and board isolation applied |
| `build/.config` | Generated configuration, checked against `accepted.config` |
| `build/u-boot.dtb` | Compiled U-Boot board DT; MMC1/MMC2 must be disabled |
| `build/spl/u-boot-spl.map` | SPL link map for inspection |
| `configure.log`, `build.log` | Build evidence |
| `receipt.json` | Pins, output checksum, header/stack checks and qualification status |

The combined image must have an ARM `eGON.BT0` SPL header and a valid eGON checksum. Its SPL padded length must be aligned and bounded, its last nonzero byte before `0x6000` must not exceed the qualified `0x5e00` limit, and the combined image plus the `8192`-byte SD offset must fit within the first `1 MiB`. The full accepted configuration and compiled MMC1/MMC2 disable properties are checked as well.

The image assembler places the qualified loader at byte offset `8192`; this recipe never writes a device. A rebuilt loader is a separate qualification step. Keep the working card and Android backup, and test updates on a spare card. The image builder pins the qualified reference loader and intentionally rejects a different binary until its reviewed input pin is updated.

Run focused host checks:

```sh
python3 bootloader/tests/test_rebuild.py
```

Host checks and successful compilation do not establish a boot. Receipts report `hardware_verified: false` and `deployed: false`.
