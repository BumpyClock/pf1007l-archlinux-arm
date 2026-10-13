# Build and update

## Rebuild an image

The [image builder](../image/README.md) accepts the sanitized root archive from
the same review release, or a separately prepared Arch Linux ARM root tree.
The archive contains a clean userspace and its required device payloads. Verify
its release checksum and review firmware distribution permissions before use.
It is separate from the original frame's private state backup.

Run on Linux, with new work and output directories outside the checkout:

```sh
sudo python3 image/build_image.py \
  --root-archive /downloads/pf1007l-sanitized-root.tar.xz \
  --work /var/tmp/pf-image-work \
  --output /var/tmp/pf-image-output
```

See the image guide for host dependencies, layout, output names and checks.
Rebuilds use a new filesystem UUID. Their matching initramfs and portable boot
profile must remain together; an initramfs from another image rejects that card.
The builder creates regular image files and does not flash a card.

## Rebuild the kernel and modules

Use the [kernel recipe](../kernel/README.md) with the authenticated source archive
and external panel/firmware inputs. It saves every kernel change, the production
touch replacement, the standard PMIC provider and the AIC driver source.
The recipe builds one compatible kernel/module export set and checks `depmod`.

Measured: the portable rebuild reproduced the qualified kernel hash
`abd477f74589516357511e00354246f588898b2c40e191c40a1acee7bd3ac186`.
The export table matched, all rebuilt module imports resolved, and the rebuilt
DT properties and boot metadata matched the qualified tree. A rebuilt kernel
is still a separate hardware trial.

The [SD-only bootloader recipe](../bootloader/README.md) preserves the matching
U-Boot source pin, configuration and both local patches. It also passed a native
rebuild and SPL/controller safety checks. The shipped, hardware-qualified loader
is retained; the rebuilt loader has a different timestamp-derived byte hash and
was not deployed.

## Prepare a USB update

For a same-release experiment, retain the portable initramfs from the exact
image installed on your card. Supply the new kernel and complete DTB:

```sh
python3 tools/make-boot-profile.py \
  --profile-id arch-usb-test-r1 \
  --kernel /new-build/zImage \
  --dtb /new-build/sun8i-a33-pf1007l-stage1.dtb \
  --initramfs /installed-image/portable-profile/initramfs.cpio.gz \
  --output ../pf1007l-work/test-r1
```

This creates `../pf1007l-work/test-r1/bundle/` with the five files required by
the uploader, and a separate `profile.json` recording the build ID. It does not install or
select anything. Choose a new profile ID for each experiment; the maintenance
helper refuses to overwrite an existing profile.

If the original portable initramfs is unavailable, read the target's
`/etc/pf-image-layout.sh` over serial. Use its `PF_ROOT_UUID` and original
minimum `PF_ROOT_SECTORS` values instead:

```sh
python3 tools/make-boot-profile.py \
  --profile-id arch-usb-test-r2 \
  --kernel /new-build/zImage --dtb /new-build/board.dtb \
  --root-uuid TARGET-ROOT-UUID --root-sectors 8388608 \
  --output ../pf1007l-work/test-r2
```

Substitute the actual UUID and minimum extent. The generator uses the current
portable initramfs source; this mode is for the supported storage/kernel layout,
not an arbitrary Linux distribution or kernel ABI.

Validate on Windows before opening serial:

```powershell
./tools/pf-usb-install.ps1 -BundlePath ../pf1007l-work/test-r1/bundle `
  -ProfileId arch-usb-test-r1 -ValidateOnly
```

Then follow [the USB tools guide](../tools/README.md) to upload, install and
explicitly select it with its actual build ID. Reboot through the maintenance
shell after checking the install receipt. The fixed dispatcher returns to its
factory kernel profile if a candidate fails to acknowledge its USB boot.

Kernel modules and runtime files are shared on the root filesystem. Back them
up before replacement; selecting a boot profile does not restore those files.
A kernel-release change also requires its matching module directory, initramfs
contents and reviewed runtime ABI checks. Uploading a new kernel file alone
does not establish those requirements.

This update path transfers boot/runtime files while preserving users' account
and network configuration. Writing an entire replacement SD image is a separate
card-reader operation, not an in-place write over the mounted root filesystem.
