#!/usr/bin/bash
set -euo pipefail
[[ $EUID == 0 && $(uname -r) == 7.2.10-pf-console-r1 ]]
driver=$(basename "$(readlink -f /sys/class/drm/card1/device/driver)")
[[ $driver == sun4i-drm ]]
getty_pid=$(systemctl show getty@tty1.service -p MainPID --value)
[[ $(ps -p "$getty_pid" -o comm= | xargs) == agetty ]]
restore_console() { systemctl start getty@tty1.service; }
trap restore_console EXIT
systemctl stop getty@tty1.service
printf 'PF_GPU_BENCHMARK_BEGIN\n'
timeout -k 3 40 stdbuf -oL -eL glmark2-es2-drm \
    --winsys-options drm-device=/dev/dri/card1 --size 800x600 \
    --visual-config id=14 --swap-mode fifo --annotate \
    -b build:use-vbo=false:duration=5 \
    -b build:use-vbo=true:duration=5 \
    -b texture:texture-filter=linear:duration=5 \
    -b shading:shading=gouraud:duration=5 \
    -b shading:shading=phong:duration=5
printf 'PF_GPU_BENCHMARK_END\n'
