# USB serial maintenance

Complete [first-time setup](../firstboot/README.md) first. Open a serial terminal to set passwords or configure Wi-Fi interactively. Close that terminal before running these tools; one process must own the USB serial port.

The Windows scripts work in Windows PowerShell 5.1 or PowerShell 7. They prompt for your `diag` password instead of reading a machine-specific credential file. To reuse a secure credential during one session:

```powershell
$frameCredential = Get-Credential -UserName diag
./tools/capture-frame.ps1 -Port COM3 -Credential $frameCredential -CommandsFile ./commands.txt -OutputPath ./tools/receipts/console.txt
./tools/pf-usb-transfer.ps1 -Port COM3 -Credential $frameCredential -InputPath ./payload.bin -ReceiptPath ./tools/receipts/transfer.json -MaxBytes 16777216 -TransferTimeoutSeconds 120
```

Receipts and transcripts can contain local file paths and device output. Keep them private; `tools/receipts/` is excluded from Git and is the installer’s default receipt location.

Choose the actual `COMx` port shown by Device Manager. `capture-frame.ps1` runs one shell command per nonblank line. Never put passwords or private network configuration in its commands file: commands appear in the console transcript. Use an interactive terminal for secret entry.

`pf-usb-transfer.ps1` uploads a length-framed binary file to a generated path under `/home/diag/pf-update`, checks its exact byte count and SHA-256, and restores terminal settings. It does not install or select a boot profile. Its default 64 KiB limit is intentional; set `-MaxBytes` for a larger payload.

## Install an immutable boot bundle

A bundle contains exactly `zImage`, `initramfs.cpio.gz`, `sun8i-a33-pf1007l-stage1.dtb`, `boot-control.scr`, and `SHA256SUMS`. Its launcher must reference the new profile ID and one `working-control-` build ID. Choose a new profile ID for each update. The bundle must match the installed kernel modules and this frame's DT.

Use [the profile generator](../docs/build.md#prepare-a-usb-update) to prepare
those files. Preserve the portable initramfs for the installed image's root
UUID. The original overlay reference bundle is not compatible with the new
partition-based root filesystem.

Validate locally before connecting to the frame:

```powershell
./tools/pf-usb-install.ps1 -BundlePath ./my-bundle -ProfileId arch-usb-my-build-r1 -ValidateOnly
```

Upload and install without selecting:

```powershell
./tools/pf-usb-install.ps1 -Port COM3 -Credential $frameCredential -BundlePath ./my-bundle -ProfileId arch-usb-my-build-r1
```

Add `-Select -BuildId working-control-0123456789abcdef` with the **actual** build ID embedded in your launcher to select that profile. Selection never reboots the frame or overwrites its root filesystem. Review the receipts, then use an interactive terminal and the maintenance command to reboot when ready. An unsuccessful upload stays unselected; use a new profile ID after correcting a failed install.

Kernel updates require matching `/usr/lib/modules/<kernel-release>` content. `pacman` alone does not rebuild this board's custom kernel or boot shim. Do not replace the recovery dispatcher while experimenting.

## Linux and macOS

Use any serial terminal, for example:

```sh
# Linux; your account needs permission to access this device.
screen /dev/ttyACM0 115200
# macOS; substitute the actual device name.
screen /dev/cu.usbmodemXXXX 115200
```

After logging in as `diag`, the same maintenance interface is available:

```sh
pkexec --disable-internal-agent /usr/local/sbin/pf-maintenance status
pkexec --disable-internal-agent /usr/local/sbin/pf-maintenance install /home/diag/pf-update/bundle-example arch-usb-my-build-r1
pkexec --disable-internal-agent /usr/local/sbin/pf-maintenance select arch-usb-my-build-r1 working-control-0123456789abcdef
```

The example bundle path must already contain the five validated files. The PowerShell tools automate their binary upload; the manual commands alone do not transfer them. You can use `pwsh` on another host only if its serial-port implementation supports your device; this repository qualifies the host scripts on Windows.

The boot bundle protocol is proven on the development frame. The portable image changes card-layout guards to support other card capacities; offline tests cover those guards, and the new image still needs hardware qualification.
