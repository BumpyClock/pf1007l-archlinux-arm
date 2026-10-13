# Flashing and first boot

The private draft image is a host-checked candidate. It has not booted on the
frame yet. Use a spare card until that qualification is complete; preserve your
working card and original Android backup.

## Image and card

The builder creates a compact image with a 4 MiB bootloader gap, a 256 MiB
FAT32 boot partition and a 4 GiB ext4 root partition. Use a card large enough
for the image, such as an 8 GB or larger microSD card. The image does not write
or install to the frame's eMMC.

Verify the download against the release `SHA256SUMS` before writing. Extract
the `.img.xz` if your image writer requires a raw `.img`; otherwise select the
compressed image directly in a writer that supports it. Select the correct
removable card. Writing an image replaces that card's existing contents.
After writing, eject the card, insert it in the frame and reconnect USB power.

On first boot, `pf-grow-root.service` validates the owned SD layout and expands
only the final root partition and ext4 filesystem. It preserves the bootloader
gap, boot partition and root partition start. If the kernel cannot refresh its
partition size, the service reports that a reboot is needed and retries later.
Its status and logs remain available over USB.

## First USB connection

The frame has one USB data/power port. Use a data-capable cable. On Windows,
find its COM device in Device Manager; on Linux it normally appears as
`/dev/ttyACM0`, and on macOS as `/dev/cu.usbmodem...`. Use the detected name,
115200 baud, 8 data bits, no parity, one stop bit and no flow control.

Open a serial terminal and press Enter. Before provisioning, USB displays the
setup wizard rather than a shared-password login. Set the root password and
then the `diag` administrator password. Password entry is hidden. The display
waits for USB setup because the bare console has no touchscreen keyboard.
If password setup is interrupted, both accounts are locked and the wizard can
be retried. After completion, both consoles require normal password login.

Wi-Fi setup is optional. It accepts a WPA2 passphrase or a hexadecimal PSK,
stores only the derived PSK in a root-owned mode-0600 configuration and starts
association in the background. The network can be configured later:

```sh
# Run interactively after logging in as root.
pf-network-setup
```

This command replaces the saved network. It does not require secrets on a
command line. WPA3-only, enterprise and captive-portal networks are outside
this provisioning helper's scope. Leaving Wi-Fi unconfigured preserves USB
administration and the display/touch hardware startup.

## Package management

First-time setup starts a fresh package signing-key initialization in the
background. Inspect or retry it if required:

```sh
systemctl status pf-init-keyring.service
systemctl restart pf-init-keyring.service
```

Package signatures remain required. The current custom kernel lacks Landlock,
so pacman downloads on that kernel need the per-command override:

```sh
pacman --disable-sandbox -Syu
pacman --disable-sandbox -S package-name
```

The board kernel, DTB and matching modules are custom artifacts. Preserve their
compatibility when updating packages; a normal pacman kernel package cannot
recreate the board-specific boot profile.

Use [USB maintenance](../tools/README.md) after first-time setup. Close your
terminal before starting an uploader so one process owns the serial port.
