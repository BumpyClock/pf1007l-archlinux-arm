# Arch Linux ARM on the PF1007L picture frame

Base Arch Linux ARM `armv7h` for an Allwinner A33 PF1007L frame with 1 GB RAM,
an 800×1280 DSI panel, Mali-400 GPU, Silead touchscreen and AIC8800DC Wi-Fi.
The development frame boots to a Linux console at 65% brightness with display,
GPU, Wi-Fi and touch working. USB serial remains available for setup and updates.
No desktop or Omarchy is installed.

The compact SD image uses a FAT boot partition and a writable ext4 root. It is
designed to expand the root partition to fill the card on first boot. The image
is a new storage and provisioning path: its offline checks do not establish a
successful hardware boot. See [validation](docs/validation.md) before flashing.
This project targets the described board and panel revision; another A33 frame
can require different firmware, GPIOs or display timings.

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
| [runtime](runtime/) | Qualified services and runtime configuration inputs |
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
