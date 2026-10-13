# GLES2 cube and benchmark

The pinned `kmscube-upstream.tar` contains unmodified upstream source and its
license notices at commit `f60e50e887d3c49e91ac9b06d8199b36152632fa`.
The saved binary and [hardware receipt](artifacts/hardware-receipt.json) record
the later Mali400 frame test. The [build receipt](artifacts/build-receipt.json)
records source and binary hashes; local build paths have been removed.

To cross-build with an Arch Linux ARM sysroot and optional QEMU emulator:

```sh
python3 gpu-test/build-kmscube.py \
  --sysroot /work/arm-sysroot --work /work/cube-build \
  --qemu /usr/bin/qemu-arm
```

Output defaults to ignored `out/gpu-test/`. The recipe omits optional GLES3,
PNG and GStreamer support. It checks the ARM hard-float ELF and runtime libraries;
`--qemu` also executes the help path. Neither check proves hardware rendering.

See [GPU testing](../docs/gpu-test.md) for bounded demos, device mapping,
RGB565 buffers and measured frame rates. The demo does not start at boot.
