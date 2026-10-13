# Saved host verification

These receipts describe build-host checks for the review image. They do not
claim that the portable image has booted on a frame.

| Receipt | Evidence |
| --- | --- |
| [Image privacy](image-privacy.json) | Actual development credentials and identity absent; factory passwords locked |
| [Repository privacy](repository-privacy.json) | Separate Luna audit of the publication tree |
| [Kernel rebuild](kernel-rebuild.json) | Pinned inputs, matching exports and rebuilt artifact hashes |
| [Bootloader rebuild](bootloader-rebuild.json) | SD isolation, accepted configuration, checksum and SPL margin |
| [Image asset verification](../../image/asset-verification.json) | Native and Windows file hashes; decompression matches raw image |
| [Package integrity](../../image/package-integrity.json) | Packaged file-content checks with no unexpected differences |
| [Image tests](../../image/tests-receipt.json) | Storage guards, growth, sanitization and package-integrity tests |

The detailed original-session privacy reports remain outside the repository.
Public upstream authorship and build metadata are retained.
