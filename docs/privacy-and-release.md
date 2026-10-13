# Privacy and release review

Keep personal device backups, saved networks, credentials, private keys and
session logs outside this checkout. Build outputs and local verification
reports also belong in an external work directory. Preserve public upstream
author and license notices.

The image builder exports a sanitized file tree into fresh filesystems. It
locks account passwords and removes personal homes, logs, saved networks, SSH
keys, machine identity and the private pacman keyring. First-time setup creates
passwords and package-signing state locally. Private filesystem blocks are not
copied into the generated image.

The builder checks file contents, directory ownership and permissions against
the assembled ext4 filesystem. Its exported root archive uses numeric owners
and omits PAX access/change timestamps. Release assets carry their own
`image-manifest.json`, `root-file-manifest.json` and `SHA256SUMS`; review the
actual assets, not only the files tracked in Git.

## Before publication

1. Check repository content and image payloads for personal information. A
   pattern scan cannot prove that every encoded or unexpected secret is absent.
2. Confirm locked accounts, no saved networks, fresh machine identity and
   correct filesystem ownership and permissions in the generated image.
3. Review firmware distribution permissions. The vendor panel and touch inputs
   stay outside Git, but the image contains required device payloads. See
   [firmware inputs](../firmware/README.md).
4. Boot on a spare SD card. Test USB password setup, root expansion, normal
   login, display, touch, GPU and private Wi-Fi provisioning.
5. Test an immutable boot profile upload over USB and its fallback. Use the
   portable image's matching initramfs, not the original overlay reference.
6. Record actual hardware results in [validation](validation.md), and compare
   uploaded asset digests with the local release checksums before publishing.

The repository and draft release remain private for manual review. Host checks
alone do not qualify a device boot or clear firmware distribution rights.
