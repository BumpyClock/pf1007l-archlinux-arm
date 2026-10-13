# Validation and limits

Saved host evidence is indexed in [verification](verification/README.md).

| Observation | Status |
| --- | --- |
| Development frame, original SD/overlay boot | Hardware verified |
| Automatic display at 65%, quiet kernel console | Passed software reboot |
| Standard Wi-Fi power and first SDIO enumeration | Passed without MMC1 rebind |
| Association, DHCP and gateway communication | Passed with privately supplied networks |
| Silead input device and visual calibration | Hardware checked; desktop calibration untested |
| Mali400 GLES2 shader rendering | Pixel check passed |
| GLES2 cube at 800×1280 | 599 frames, 58.815 FPS |
| Short glmark2 scenes | Passed; Phong 32–33 FPS |
| Portable image filesystem/partition/payload checks | See its generated image manifest |
| First-boot password and Wi-Fi scripts | Offline PTY tests; hardware setup untested |
| Packaged ARM WPA derivation | QEMU test passed for spaces, apostrophe and UTF-8 SSIDs |
| Portable kernel rebuild | Kernel byte hash and exports match the qualified inputs |
| SD-only U-Boot rebuild | Configuration, checksum, SPL margin and controller isolation checks passed |
| Root-partition expansion | Disposable partition/filesystem tests; real-card first boot untested |
| Portable image hardware boot and serial update | Not tested |
| Physical cold power cycle of new image | Not tested |
| Bluetooth and audio | Not qualified |

The portable image retains the qualified kernel, DTB and peripheral sources.
It changes root storage, capacity checks, first-time account setup and the
recovery image selection. Hardware results for the original overlay installation
do not prove those new paths. The image manifest uses
`HOST_VERIFIED_NOT_HARDWARE_BOOTED` until a real boot establishes more.

`sfdisk`, `e2fsck`, mounted-file inventories, loader readback and compression
checks establish properties of the assembled artifact. Mocked/PTY tests cover
script behavior without modifying a user's accounts or storage. They do not
replace a frame boot test.

The original runtime update protocol was exercised on the development frame.
The public tools retain length-framed transfers, remote SHA256 checks, immutable
profile installation and explicit selection. The new card-layout guards and
first-time serial provisioning need their own hardware qualification.
