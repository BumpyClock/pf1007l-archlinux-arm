# External firmware inputs

The extracted panel program and touch firmware are not stored in Git. The saved
panel source explicitly says "do not redistribute". The pinned hardware inputs
and hashes are listed in [required-inputs.json](required-inputs.json).

The private draft image and compiled boot/reference artifacts contain device
payloads already present in the qualified inputs.
It is prepared for manual review, not cleared for public firmware distribution.
Check the applicable firmware permissions before publishing that image. The
kernel and driver sources retain their upstream licenses; their license does
not assign a license to these separate payloads.

## Extract the matched Android modules

Obtain `lcd.ko` and `gslX680new.ko` from your own matching stock Android system
or Android backup. On stock Android with ADB access, locate the modules before
pulling them; these are read-only operations:

```sh
adb shell find /system -name lcd.ko
adb shell find /system -name gslX680new.ko
adb pull /actual/path/lcd.ko ./lcd.ko
adb pull /actual/path/gslX680new.ko ./gslX680new.ko
```

The paths printed by your frame determine the two `adb pull` arguments.
Alternatively, extract those modules from the matching system partition in
your private Android backup. Keep the backup outside the repository.

Run the extractor with a new private output directory outside Git:

```sh
python3 firmware/extract-stock-inputs.py \
  --lcd-module /private/android/lcd.ko \
  --touch-module /private/android/gslX680new.ko \
  --output /private/pf1007l-inputs
```

It validates the exact module hashes, selects the matching ELF32 symbols and
checks the generated header and firmware hashes. The panel symbol name occurs
in several stock panel variants; the pinned size and table hash disambiguate
the qualified one. A different module hash is rejected instead of guessing
which panel or touch variant it supports.

The outputs are `sq9365-private-table.h` and
`silead/pf1007l-gsl-m86-hd.fw`. The extractor was checked against the development
frame's owned Android modules, and both outputs match the qualified inputs.
It does not write to a frame or extract account/network data.

The remaining radio firmware and regulatory files must be supplied from an
appropriately licensed source and match the required hashes. The kernel build
checks those inputs before compiling. The AIC driver source is pinned to the
[Radxa repository](https://github.com/radxa-pkg/aic8800) at commit
`55d82dd8c78861cf034a22cc29ebdd21d93b7349`; firmware and software licenses must
be reviewed separately.
