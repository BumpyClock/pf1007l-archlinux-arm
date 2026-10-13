# Portable SD image

The generated image is a **draft checked on the build host; it has not booted on a frame**. The kernel, panel device tree, power provider, touch driver and console settings come from the hardware-tested baseline. Moving the root filesystem from loop images to an SD partition changes the boot path and requires a separate device test.

The draft contains device-specific vendor firmware and panel data. Review the distribution terms described in [firmware](../firmware/README.md) before publishing image assets.

## Layout and first boot

The image uses a DOS partition table, preserves the Allwinner SPL at byte 8192 and leaves 4 MiB before the first partition. Partition 1 is a 256 MiB FAT32 boot volume. Partition 2 is a 4 GiB ext4 root filesystem. An 8 GB or larger SD card accommodates the default image.

On first boot, `pf-grow-root.service` extends only the last root partition and grows ext4 online. It checks the SD device type, filesystem UUID, two ownership markers and expected partition starts before writing. Other card capacities are accepted; eMMC devices and foreign layouts are rejected. If partition notification or resize fails, the USB setup console still starts. The operation retries next boot until its completion marker exists.

The USB gadget and `ttyGS0` serial service remain available. Initial account passwords are locked. Connect at **115200 8N1** and follow the USB setup wizard to set root and `diag` passwords, then optionally add Wi-Fi. No shared password or saved network is included. Display, touch and WLAN hardware load before network credentials are supplied. SSH is masked.

The fixed dispatcher boots a selected candidate once and falls back to the factory kernel profile if the candidate does not acknowledge its USB boot. The factory recovery profile shares the ext4 root. It can recover a failed kernel trial; it cannot repair a corrupt root filesystem. See [USB updates](../tools/README.md).

## Build

Run on Linux as root with `python3`, `e2fsprogs`, `dosfstools`, `util-linux`, `u-boot-tools`, `tar` and `xz-utils` installed. The builder creates new regular files and temporary loop mounts. It never opens a physical card for writing.

The maintained source and pinned boot seed are in this directory. A clean root archive is an input that can be redistributed separately from Git after privacy, licensing and hardware review. Rebuilding from that archive requires no private device backup:

`inputs/` contains the original tested boot seeds and storage-dependent maintenance template. They are build inputs. The builder replaces their loop-backed storage path before packaging. Use `dist/portable-profile/` or [make-boot-profile.py](../tools/make-boot-profile.py) for a portable card. Copying the raw seed initramfs onto that card would select the wrong root-storage mechanism.

```sh
sudo python3 image/build_image.py \
  --root-archive /path/to/pf1007l-sanitized-root.tar.xz \
  --work /var/tmp/pf-build-work \
  --output /var/tmp/pf-build-dist
```

Use new work and output paths each run. Verify the input archive against the release's `image-manifest.json` before using it. The builder also accepts `--root-tree` for a prepared Arch Linux ARM armv7 filesystem, or `--base` plus `--state` to import an immutable base and a consistent frozen overlay snapshot. Private seeds remain read-only and are never copied as filesystem blocks into the published image.

For an independent fresh userspace build, extract the official Arch Linux ARM armv7 root filesystem into a Linux directory, install the package set in `installed-packages.txt`, then build/install this repository's kernel, device modules, firmware inputs and runtime tools into that tree. Pass it using `--root-tree`. A plain upstream rootfs alone lacks the frame-specific modules and tools and is not a complete image input. The sanitized root archive provides the exact packaged userspace when old package versions have left rolling mirrors.

The builder clears accounts' password hashes, home directories, logs, caches, saved networks, SSH host keys, private package-signing keys and machine identity. It applies the maintained overlays, checks installed package contents against their mtree hashes, checks ARM executable headers, provisions the portable storage guards, and writes fresh FAT and ext4 filesystems. The exported root archive contains this clean tree rather than blocks from private snapshots. Each build uses a new filesystem UUID; repeated builds preserve configuration rather than producing identical image bytes.

Package content checks are mandatory. An initial private seed had mismatched `glmark2`, `libjpeg-turbo` and TPM configuration files. These were restored from signed packages of the same installed versions; [repair-receipt](seed-repair-receipt.json) records archive hashes and the verified public build key. This repair changed the exported userspace. The working frame was unchanged. The cause of the seed mismatch remains unproven. Filesystem consistency alone does not prove package contents are correct.

Outputs:

- `pf1007l-archlinux-arm.img` and `.img.xz`: burnable sparse image and compressed copy.
- `pf1007l-sanitized-root.tar.xz`: clean rebuild input, with the same vendor payload review requirement.
- `portable-profile/`: matching kernel/initramfs/DT/script bundle for this image's root UUID. A bundle made for another image UUID will reject this card.
- `image-manifest.json`: asset hashes, geometry and validation status.
- `root-file-manifest.json`, `installed-packages.txt`: packaged file hashes and package versions.

Use a normal image writer such as Raspberry Pi Imager's custom-image option, or decompress and write the complete image to the intended SD card. Writing an image replaces the card's existing data. Do not copy `.img` into a FAT volume as an ordinary file. No factory Android/eMMC write is required.

## Host checks

```sh
python3 image/test_growth.py
python3 image/test_guard.py
sudo python3 image/test_growth_loop.py
sudo python3 image/test_sanitize.py
python3 image/test_package_integrity.py
python3 image/verify_assets.py --dist /path/to/assets
```

The tests reject foreign UUIDs, eMMC, extra partitions, invalid starts, undersized cards and extents beyond MBR limits. The loop test grows a mounted ext4 filesystem on a new disposable image, verifies existing data and runs `e2fsck -fn`. The builder also checks filesystem consistency, the partition table, SPL readback, every installed root file and compressed-file integrity.

After a successful device boot, run as root:

```sh
pf-standard-power-check
pf-standard-power-check --network
```

The first check permits offline operation. The second checks association, an IPv4 address and gateway reachability after Wi-Fi setup. Neither prints saved network credentials.
