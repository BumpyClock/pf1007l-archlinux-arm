# Privacy and release review

The original session archive was reviewed by a separate Luna agent. Its
confirmed publication findings were local user/profile paths and card-reader
serial numbers. Credential-like heuristic matches were inspected separately;
no actual static credentials or private keys were confirmed in those docs.

This repository is a curated copy. Session transcripts, private reports,
Android/eMMC backups, saved Wi-Fi profiles and the full personal persistent
state are excluded. Local paths were removed from the retained build evidence.
Public upstream author and license notices are preserved. The complete audit
report remains private because it describes locations in the original archive.

The new image is assembled into fresh filesystems from a sanitized file tree.
It does not distribute the raw private state image, including unused filesystem
blocks. Password fields are replaced with locked values; personal homes, logs,
network state, SSH keys, machine IDs and private package keyring state are removed.
First-time setup generates account credentials and package keyring state locally.

## Before making the repository public

1. Review the tracked files and draft release assets separately. Git exclusions
   do not exclude data embedded inside an image.
2. Confirm that the image privacy and filesystem checks passed, including locked
   accounts, no saved networks and fresh host identity.
3. Review firmware distribution permissions. Extracted vendor inputs stay outside
   Git, but the draft image contains required device firmware.
4. Boot the new image on a spare card. Test first USB setup, root growth, normal
   password login, display/touch/GPU and private Wi-Fi provisioning.
5. Test a new immutable boot profile upload over USB and its rollback. Do not
   use the original overlay reference bundle as a portable-image update.
6. Update [validation](validation.md) with actual hardware results before marking
   a release as hardware-qualified.

The GitHub repository and draft release remain private for manual review.
