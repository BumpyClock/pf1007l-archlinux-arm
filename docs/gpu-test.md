# GPU tests

Measured on the development frame: Mesa `26.2.4-arch1.1` reports `Mali400` and
OpenGL ES 2.0. A nonroot shader probe checked all 256 rendered pixels.
The rotating GLES2 cube rendered 599 frames in 10.185 seconds, or 58.815 FPS,
at the native 800×1280 display mode.

| Short glmark2 scene | FPS |
| --- | ---: |
| Build without VBO | 57 |
| Build with VBO | 59 |
| Linear texture | 59 |
| Gouraud shading | 59 |
| Phong shading | 32–33 |

These are individual scenes, not a full default benchmark score. Vertical sync
can limit the faster scenes to panel refresh. Vulkan is unsupported by Mali-400;
use GLES2 demos, as described in [Mesa Lima's documentation](https://docs.mesa3d.org/drivers/lima.html).

## Run glmark2

```sh
# As root, after package signing-key initialization.
pacman --disable-sandbox -S --needed glmark2
glmark2-es2-drm \
  --winsys-options drm-device=/dev/dri/card1 --size 800x600 \
  --visual-config id=14 --swap-mode fifo --annotate \
  -b shading:shading=gouraud:duration=10 \
  -b shading:shading=phong:duration=10
```

Confirm the device mapping first: `card1` was `sun4i-drm`, and `card0` was Lima.
The DRM demo still renders at 800×1280 despite the non-native requested size.
That size avoids the [glmark2 initialization issue](https://github.com/glmark2/glmark2/issues/259)
observed with `--fullscreen` or an exact native-size request in version 2023.01.

EGL config `id=14` selected RGB565 color and 16-bit depth on the tested Mesa
version. Config IDs can change; confirm its printed surface configuration.
Default 32-bit color failed display-buffer allocation with the kernel's 16 MiB
CMA reservation. Inferred: RGB565 reduced contiguous buffer use enough to pass.

The [bounded runner](../gpu-test/run-gpu-benchmark.sh) checks for an idle display
login before stopping it and restores the login after the demo. The USB console
remains available. Do not stop someone else's active display session.

## Run the cube

Build the pinned cube source with the [cross-build recipe](../gpu-test/README.md):

```sh
python3 gpu-test/build-kmscube.py \
  --sysroot /work/arm-sysroot --work /work/cube-build \
  --output /work/cube-output
```

The source commit is `f60e50e887d3c49e91ac9b06d8199b36152632fa`. Copy
`/work/cube-output/kmscube.armv7h` to the frame through the USB transfer tool,
then stage it at `/run/pf-kmscube`. Generated outputs belong outside this
checkout. On the frame, the direct invocation is:

```sh
timeout -k 5 45 /run/pf-kmscube \
  -D /dev/dri/card1 -M smooth -x -m 0 -f RG16 -v 800x1280 -N -c 600
```

`-x` scans out two color buffers, `RG16` selects RGB565, `-m 0` selects linear
buffers and `-N` prevents remote stdin ending the test. Upstream does not restore
the previous CRTC. The [cube runner](../gpu-test/run-kmscube.sh) restores the login
and switches virtual consoles. Stage the binary at `/run/pf-kmscube` before using
that runner. These demos are optional and do not start at boot.
