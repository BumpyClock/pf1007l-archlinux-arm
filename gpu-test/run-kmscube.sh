#!/usr/bin/bash
set -euo pipefail
[[ $(systemctl show getty@tty1.service -p SubState --value) == running ]]
getty_pid=$(systemctl show getty@tty1.service -p MainPID --value)
[[ $(ps -p "$getty_pid" -o comm= | xargs) == agetty ]]
restore_console() {
    systemctl start getty@tty1.service
    chvt 2
    chvt 1
}
trap restore_console EXIT
systemctl stop getty@tty1.service
printf 'PF_KMSCUBE_BEGIN\n'
timeout -k 5 45 stdbuf -oL -eL /run/pf-kmscube \
    -D /dev/dri/card1 -M smooth -x -m 0 -f RG16 -v 800x1280 -N -c 600
printf 'PF_KMSCUBE_END\n'
