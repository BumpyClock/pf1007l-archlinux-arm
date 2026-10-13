# Arch Linux ARM on the PF1007L picture frame

Base Arch Linux ARM `armv7h` for an Allwinner A33 PF1007L frame with 1 GB RAM,
an 800×1280 DSI panel, Mali-400 GPU, Silead touchscreen and AIC8800DC Wi-Fi.
The development frame boots to a Linux console at 65% brightness with display,
GPU, Wi-Fi and touch working. USB serial remains available for setup and updates.
No desktop or Omarchy is installed.

## Current status

There are two installations to distinguish when reading the sources and results.

| Installation | Storage | Verification |
| --- | --- | --- |
| Development frame | Read-only base image with a writable overlay | Display, GPU, touch and Wi-Fi checked on hardware |
| Portable SD image | FAT boot partition and writable ext4 root partition | Host checks passed; hardware boot and first-time setup remain untested |

The portable image is designed to expand its root partition to fill the card
on first boot. Its recorded status is `HOST_VERIFIED_NOT_HARDWARE_BOOTED`.
Read [validation](docs/validation.md) and the
[saved verification receipts](docs/verification/README.md) before relying on a
hardware result. Vendor payloads also require distribution review before a
public release; see [firmware inputs](firmware/README.md).

This project targets the described board and panel revision. Another A33 frame
can require different firmware, GPIOs or display timings.

## Find the right guide

| Task | Start here |
| --- | --- |
| Flash a card and set passwords or Wi-Fi | [Flashing and first boot](docs/flashing.md) |
| Update a kernel over USB without removing the card | [Build and update](docs/build.md#prepare-a-usb-update), then [USB maintenance](tools/README.md) |
| Rebuild an image, kernel or bootloader | [Build guide](docs/build.md), [kernel recipe](kernel/README.md), [bootloader recipe](bootloader/README.md) |
| Understand display, touch, Wi-Fi and GPU configuration | [Hardware configuration](docs/hardware.md) |
| Run a GPU demo or compare results | [GPU tests](docs/gpu-test.md) |
| Prepare a public release | [Privacy and release review](docs/privacy-and-release.md) |

The [documentation index](docs/README.md) lists the complete guide set.

## Start here

1. Read [flashing and first boot](docs/flashing.md), including the current image
   qualification and firmware distribution notes.
2. Write the image to a spare microSD card with your image writer. Keep the
   working card and original Android backup.
3. Connect the frame's USB data/power port. Open its serial device at
   **115200 baud, 8N1**. First-time setup asks for new root and `diag`
   administrator passwords, then offers private WPA2 Wi-Fi setup.
4. After setup, log in normally. Run `pf-network-setup` as root to configure or
   replace the saved network. No network name or password is supplied by this repo.
5. Use the [USB maintenance tools](tools/README.md) to upload and select new
   kernel/initramfs/DT profiles without removing the card.

SSH is disabled by default. `diag` is a local administrator through the
maintenance helper; it is not a restricted guest account. The image has no
shared login password. Linux boots from SD, and this project does not install
to eMMC.

## What is included

| Directory | Purpose |
| --- | --- |
| [image](image/) | Image assembler, portable root guards, first-boot growth and tests |
| [firstboot](firstboot/) | USB password setup, private network provisioning and package keyring initialization |
| [tools](tools/) | Windows serial login, verified binary transfer and immutable profile installation |
| [kernel](kernel/) | Pinned configuration, source changes, production touch and standard Wi-Fi power provider |
| [bootloader](bootloader/) | Pinned SD-only U-Boot source, patches, configuration and rebuild recipe |
| [drivers](drivers/) | Pinned AIC8800 source and Linux compatibility patch |
| [hardware](hardware/) | Complete board device tree |
| [firmware](firmware/) | External firmware hashes and Android-module extraction tool |
| [runtime](runtime/) | Snapshot of qualified services and runtime configuration for lookup |
| [gpu-test](gpu-test/) | GLES2 cube source, binary and bounded performance checks |
| [reference](reference/) | Hardware-qualified original overlay baseline; not the portable image's update bundle |
| [docs](docs/) | Hardware, setup, rebuilding, maintenance, privacy and validation guides |

Large generated images stay outside Git. The private draft release is for
manual review. The image contains device firmware; firmware distribution
permission and a real boot test must be reviewed before a public release.
The extracted vendor panel and touch inputs are excluded from Git.

The private [review release](https://github.com/BumpyClock/pf1007l-archlinux-arm/releases)
contains the compressed image, sanitized rebuild root, matching portable USB
boot profile, file manifest and SHA256 checksums. The compressed image is
718 MiB; it expands to a 4.25 GiB image before writing.

## For maintainers and agents

Start with [hardware configuration](docs/hardware.md),
[validation](docs/validation.md) and [build and update](docs/build.md).
They record the board assumptions, what has been tested and how to produce
compatible artifacts. This repository contains the selected baseline and
rebuild inputs. Private session logs, Android backups and credentials are kept
outside Git.

Follow the build path before editing a configuration snapshot:

- `kernel/rebuild.py` checks the pinned sources and configuration, applies the
  baseline files in `kernel/overlay/`, then applies the production touch and
  standard-power provider overrides. It builds the matching kernel and modules
  and compiles the board DTS in `hardware/`.
- `image/build_image.py` starts with a prepared root tree or sanitized root
  archive. It applies `reference/qualified-overlay/root-overlay/` and
  `firstboot/root-overlay/`, then adapts storage, maintenance and startup helpers
  for the partition-based root. It uses the boot seeds in `image/inputs/`.
- `runtime/qualified/` is a configuration snapshot. The image builder does not
  copy that directory. Runtime edits must reach the prepared root or an overlay
  that the builder actually applies.
- `tools/make-boot-profile.py` prepares a new five-file boot bundle. The
  PowerShell tools validate, transfer, install and optionally select it.
  Building a bundle does not deploy it or reboot the frame.

Keep the kernel, matching module set, DTB and storage-specific initramfs
compatible. Each rebuilt image gets a new root UUID. Use its own portable
initramfs or generate one for the target card's recorded layout. The original
overlay reference initramfs is incompatible with the portable root partition.
The factory fallback shares the root filesystem; it does not restore changed
modules or repair root-filesystem corruption.

Source and installation manifests pin file hashes. If a maintained input
changes, update its corresponding pins and validate the resulting artifacts.
Preserve upstream license notices and `.gitattributes` rules for pinned files.
Saved receipts describe the artifacts that were checked; collect new evidence
for new artifacts instead of changing an old receipt to imply a pass.

Use Linux or Linux inside WSL for kernel and image builds. Kernel builds need
the ARM hard-float cross-toolchain; image assembly requires root and filesystem
tools. Use new work/output directories and a Linux filesystem for kernel work.
The Windows serial tools support Windows PowerShell 5.1 and PowerShell 7.
Each component's README lists its dependencies and checks.

These checks run on the host without opening a serial port or writing a real
SD card. Run the checks relevant to the files you change:

```sh
python3 firstboot/tests/test_provisioning.py
python3 kernel/tests/test_rebuild.py
python3 bootloader/tests/test_rebuild.py
python3 image/test_guard.py
python3 image/test_package_integrity.py
```

Use [the image checks](image/README.md#host-checks) for storage or packaging
changes and [the USB tool checks](tools/tests/test-serial-tools.ps1) for host
transfer changes. Record hardware results separately in
[validation](docs/validation.md).

Keep generated artifacts in ignored `dist/`, `out/` or `build/` directories.
Keep external firmware in `firmware/local/` or outside the repository, and
serial receipts in `tools/receipts/`. Do not commit network profiles, passwords,
private keys, device backups or session transcripts. Review embedded payloads
as well as tracked files before publishing an image.

## Hardware results

Measured on the development frame: automatic startup passed software reboot;
Wi-Fi enumerated on its first attempt using kernel-owned power sequencing,
without the old MMC1 rebind. Mesa reports `Mali400` and OpenGL ES 2.0.
`kmscube` rendered at 58.8 FPS; the Phong scene in `glmark2` ran at 32–33 FPS.
The faster demos can be limited by the display refresh rate.

These results apply to the qualified development setup. The new portable
image and first-boot expansion remain separate hardware qualification steps.
Bluetooth and audio are not qualified by this release.

## Credits and licenses

The standard regulator/MMC Wi-Fi sequence was adapted from
[pangoleen/ormarch-picture-frame](https://github.com/pangoleen/ormarch-picture-frame).
This project uses [Arch Linux ARM](https://archlinuxarm.org/), Linux,
U-Boot, Mesa Lima and the pinned Radxa AIC8800 driver source.
See [licensing and firmware inputs](firmware/README.md).
Original scripts and documentation use the MIT license. Upstream code retains
its own notices and licenses; the MIT license does not cover vendor firmware,
extracted panel data or their embedded copies in compiled artifacts.
