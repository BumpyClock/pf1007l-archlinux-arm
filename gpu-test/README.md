# GLES2 cube and benchmark

The pinned `kmscube-upstream.tar` contains unmodified upstream source and its
license notices at commit `f60e50e887d3c49e91ac9b06d8199b36152632fa`.
Build the cube locally; generated binaries, logs and receipts stay outside this
checkout.

To cross-build with an Arch Linux ARM sysroot and optional QEMU emulator:

```sh
python3 gpu-test/build-kmscube.py \
  --sysroot /work/arm-sysroot --work /work/cube-build \
  --output /work/cube-output --qemu /usr/bin/qemu-arm
```

Use new work and output paths. Omit `--qemu` if no compatible emulator is
available. The recipe omits optional GLES3, PNG and GStreamer support. It checks
the ARM hard-float ELF and runtime libraries; `--qemu` also executes the help
path. Neither check proves hardware rendering.

The output includes `kmscube.armv7h` and a local build receipt. Transfer the
binary to the frame over USB, then stage it at `/run/pf-kmscube` for the bounded
runner. See [GPU testing](../docs/gpu-test.md) for device mapping, RGB565 buffers
and measured frame rates. The demo does not start at boot.
