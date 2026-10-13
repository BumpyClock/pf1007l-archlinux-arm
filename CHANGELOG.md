# Changelog

## Image metadata correction

- Install root overlays without copying Windows directory ownership or modes.
- Restore protected system directory ownership and permissions while preserving
  service-owned directories and the `diag` home.
- Verify directory, file and symlink ownership/modes in the assembled image.
- Omit archive access/change timestamps from the sanitized rebuild root.

The corrected image remains a private candidate awaiting a hardware boot test
and vendor firmware distribution review.

## Initial private review

- Preserve the hardware-qualified base Arch Linux ARM kernel, display, touch,
  Lima GPU and standard AIC8800 Wi-Fi power sequence.
- Add a compact direct-root SD image candidate and first-boot root expansion.
- Add USB password setup, private Wi-Fi provisioning and portable serial tools.
- Separate external firmware inputs and remove session-specific personal paths.
- Save GPU test results and distinguish offline image checks from hardware tests.

The image is an experimental private review candidate, not a hardware-qualified
public release.
