# First boot and local administration

The image contains locked `root` and `diag` accounts, no default password, and no saved Wi-Fi credentials. Connect the frame by USB and open its USB serial port at **115200 baud, 8 data bits, no parity, 1 stop bit**, with flow control off. On Windows the port appears as `COMx`; Linux normally uses `/dev/ttyACM0`, and macOS `/dev/cu.usbmodem*`.

First boot asks for a root password and a separate `diag` password. Password input is hidden. You can then configure WPA2 Wi-Fi or skip it. The frame display waits for USB setup to finish; subsequent boots show ordinary password-protected logins on USB and the display. There is no automatic root login or enabled SSH daemon.

`diag` is an administrator. Its existing Polkit policy permits `/usr/local/sbin/pf-maintenance`, including its root shell operation. Treat its password like the root password. The host update tools use `diag`.

## Files installed in the image

Copy `root-overlay/` to the root filesystem with ownership and modes from [install-manifest.json](install-manifest.json). Enable `pf-init-keyring.service`. Keep the proven USB gadget and `serial-getty@ttyGS0.service` enabled. Initial accounts must remain locked, and both completion markers listed in the manifest must be absent.

`pf-console-login` replaces the two getty commands. It runs the setup wizard on USB until `/var/lib/pf-firstboot/complete` exists. A lock prevents concurrent setup. The marker is written only after both passwords succeed. Script failure relocks both accounts; an interrupted setup starts by relocking both on the next attempt. The wizard completes password setup before optional networking, so an unavailable access point cannot prevent login.

Package signing keys are generated locally after password setup by `pf-init-keyring.service`, with a 180-second timeout. The service retries on later boots until its completion marker exists. Check or retry it after login:

```sh
systemctl status pf-init-keyring.service
systemctl restart pf-init-keyring.service
```

Pacman signature checks remain enabled. This kernel lacks the Landlock feature required by the current pacman download sandbox. Use its per-command option:

```sh
pacman --disable-sandbox -Syu
```

Do not copy a private pacman keyring from another installation.

## Configure Wi-Fi after setup

Log in as root and run:

```sh
pf-network-setup
```

The helper prompts for the SSID and a hidden passphrase. It accepts a 1–32-byte SSID and an 8–63-byte WPA2 passphrase, or a 64-digit hexadecimal PSK. It **replaces** the saved network configuration. The SSID is encoded as hexadecimal, and only the derived PSK is saved; plaintext passphrases and `wpa_passphrase` comments are discarded. The config is written atomically as root with mode `0600` at `/var/lib/pf-wifi/wpa_supplicant.conf`. It then starts the existing Wi-Fi and DHCP services in the background.

```sh
systemctl status pf-wifi.service pf-wifi-dhcp.service
ip -br address
```

Saved configuration and logs stay on your device. Do not include them in a public repository or a redistributed image.

## Tests

Run on Linux, or in WSL:

```sh
python3 firstboot/tests/test_provisioning.py
```

Tests execute the scripts in a temporary filesystem and mock account/service commands. They cover completed setup, repeated setup, failed second password, private PSK-only Wi-Fi writes, failure preserving the old config, SSID byte limits, package-keyring retry, and normal getty execution on both terminals after completion. They do not qualify a hardware boot.

To check vendor-unit TTY and restart settings against an assembled image root tree:

```sh
python3 firstboot/tests/check_getty_units.py --rootfs /private/builds/root-tree
```
