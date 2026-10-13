# Component notices

Original project scripts, documentation and configuration are provided under
the repository's MIT license. Imported code and binary inputs retain their
existing licenses; this statement does not relicense them.

- Linux kernel and modified kernel drivers: existing GPL/SPDX notices in each
  source file. The pinned upstream source archive and all local changes are
  described in `kernel/`.
- U-Boot: upstream GPL notices; pinned source and local changes in `bootloader/`.
- AIC8800 driver: pinned Radxa/AIC source with its original source notices.
- kmscube: upstream source archive includes its license and copyright notices.
- Arch Linux ARM packages: individual package licenses, also present in the
  assembled filesystem's package metadata and license files.
- Firmware and extracted panel data: separate vendor terms. Standalone extracted
  inputs are excluded from Git. Compiled boot/reference artifacts and image
  assets can embed device payloads and require distribution review too.

The private review repository does not establish public distribution rights
for vendor payloads. Review those terms before making it public or publishing
its image assets.
