# Hardware configuration

The measured development board is PF1007L with an Allwinner A33, 1 GB RAM,
Mali-400, an 800×1280 four-lane DSI panel, Silead touch and AIC8800DC Wi-Fi.
The complete [device tree](../hardware/pf1007l-standard-wifi.dts) is the board
reference. Numeric phandles belong to that full tree; do not copy isolated
numeric supply references into another board tree.

## Display and console

| Item | Qualified setting |
| --- | --- |
| Panel compatible | `yhk,zr789-sq9365-101` |
| Native mode | 800×1280 portrait, four DSI lanes, RGB888 |
| Pixel clock | 67,000 kHz |
| Horizontal display/sync start/sync end/total | 800 / 818 / 836 / 854 |
| Vertical display/sync start/sync end/total | 1280 / 1300 / 1304 / 1314 |
| Panel reset | PH7, active low |
| Backlight enable | PH6, active high |
| PWM | PWM0 on PH0, 20,000 ns period |
| Default brightness | 65%, corresponding to 13,000 ns PWM duty |
| Display supply | DC1SW with its enabled 3.0 V DCDC1 upstream supply |
| Panel supply | ELDO3 at 3.3 V |

The panel module executes the matched 204-record Android initialization table.
The table is an external input, not public source; see
[firmware extraction](../firmware/README.md). The DSI patch preserves a real
supply provider, and the backlight enable is acquired low during activation.
The framebuffer console then owns the native portrait display.

`kernel.printk = 4 4 1 4` restricts visible kernel messages to errors and more
severe levels. Full messages remain in `dmesg` and the journal. The login clears
earlier boot text. The kernel's forced `loglevel=7` command line is unchanged;
the sysctl applies in userspace before the display is brought up.

## Wi-Fi power

The device tree uses the standard regulator/MMC sequence adopted from
[the reference project](https://github.com/pangoleen/ormarch-picture-frame):

1. DLDO1 and DLDO2 remain at 3.3 V with `regulator-always-on`.
2. An AXP GPIO0 hog requests the external switch high.
3. A fixed regulator drives PL2 high and waits 150 ms.
4. `mmc-pwrseq-simple` releases active-low PL6 reset and waits 200 ms.
5. MMC1 enumerates the SDIO radio; the runtime loads the AIC modules.

The current PMIC module's `photoframe,standard-wifi-power-sequence` flag enables
stock DLDO1/DLDO2 regulator behavior while preserving the touch LDO_IO1 guard
and the accepted PMIC cold-start behavior. This path does not use the earlier
custom Wi-Fi power module or MMC1 unbind/rebind retry.

Measured: the development frame enumerated SDIO on its first attempt and
passed Wi-Fi association, DHCP and gateway communication after software reboot.
The AXP debug GPIO input readback can report low despite the output-high control;
the helper validates ownership, output direction, regulator voltage and SDIO
readiness. Physical pad voltage was not measured.

## Touch and GPU

Silead is at I2C0 address `0x40`, with the qualified clock at 400 kHz. The
production `silead` module uses the matched Android startup sequence and the
external `gsl_m86_hd` firmware. Raw coordinates are 1024×600; the saved libinput
rule maps them to the display orientation. Raw evdev coordinates do not change,
and a desktop calibration has not been tested.

Lima is the Mali-400 rendering driver; sun4i DRM controls the display. Mesa
reports OpenGL ES 2.0. Vulkan is unsupported on this GPU. See the
[GPU tests](gpu-test.md) for renderer checks and frame rates.
