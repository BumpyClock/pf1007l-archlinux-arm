# Hardware-qualified overlay reference

This is the development frame's qualified kernel, standard Wi-Fi device tree
and root-overlay update set. Its original storage is a read-only base image
plus a writable state image on FAT, with a card-specific maintenance guard.
Automatic display at 65%, Wi-Fi, touch and quiet console passed software reboot;
Mali400 GLES2 rendering was tested separately.

The portable image builder uses these as pinned source inputs and creates a
different initramfs, storage guard and boot profile. Do not install this original
boot bundle as an update to the portable direct-root image. Use a bundle built
for the image's own storage layout and root UUID.

The manifest's hashes describe these preserved files. Runtime installers here
target the original overlay setup, not a fresh or portable card. The maintained
portable procedure is in [the build guide](../../docs/build.md).
