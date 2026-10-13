setenv verify yes
if itest.l *0x14 -ne 0x034c5053; then echo PF_SPL_HEADER_INVALID; while true; do sleep 60; done; fi
if setexpr.l pf_ram_mb *0x24; then true; else while true; do sleep 60; done; fi
if itest 0x${pf_ram_mb} -lt 0x200; then echo PF_RAM_TOO_SMALL; while true; do sleep 60; done; fi
setenv pf_recovery 'setenv pf_boot_role recovery; setenv verify yes; if fatsize mmc 0:1 boot-maint/recovery.scr && itest 0x${filesize} -eq 0x1f56; then if fatload mmc 0:1 0x48000000 boot-maint/recovery.scr 0x1f56 && itest 0x${filesize} -eq 0x1f56; then if hash sha256 0x48000000 0x1f56 pf_actual_sha && test "${pf_actual_sha}" = "75f31b3a64dc6b84e28e94af89995820b1958b29497ed53266637b19cf7b14a4"; then source 0x48000000; fi; fi; fi; echo PF_RECOVERY_RETURNED_OR_INVALID; while true; do sleep 60; done'
setenv pf_trial_dir
setenv pf_trial_build
setenv pf_trial_script_sha
setenv pf_trial_script_size
setenv pf_armed 0
if fatsize mmc 0:1 boot-maint/trial-state.bin && itest 0x${filesize} -eq 1; then
    if fatload mmc 0:1 0x47400000 boot-maint/trial-state.bin 1 && itest 0x${filesize} -eq 1; then
        if itest.b *0x47400000 -eq 0xa5; then setenv pf_armed 1; fi
    fi
fi
if test "${pf_armed}" = 1; then
    if fatsize mmc 0:1 boot-maint/trial.env && itest 0x${filesize} -gt 0 && itest 0x${filesize} -le 0x200; then
        setenv pf_env_size ${filesize}
        if fatload mmc 0:1 0x47600000 boot-maint/trial.env 0x${pf_env_size} && itest 0x${filesize} -eq 0x${pf_env_size}; then
            if env import -t 0x47600000 0x${pf_env_size} pf_trial_dir pf_trial_build pf_trial_script_sha pf_trial_script_size; then
                setenv pf_valid 1
                if setexpr pf_bad sub '^arch-usb-[a-z0-9-]+$' '' "${pf_trial_dir}" && test -n "${pf_trial_dir}" && test -z "${pf_bad}"; then true; else setenv pf_valid 0; fi
                if setexpr pf_bad sub '^working-control-[0-9a-f]+$' '' "${pf_trial_build}" && test -n "${pf_trial_build}" && test -z "${pf_bad}"; then true; else setenv pf_valid 0; fi
                if setexpr pf_bad sub '^[0-9a-f]+$' '' "${pf_trial_script_size}" && test -n "${pf_trial_script_size}" && test -z "${pf_bad}"; then true; else setenv pf_valid 0; fi
                if test "${pf_valid}" = 1 && fatsize mmc 0:1 "${pf_trial_dir}/boot-control.scr"; then
                    if itest 0x${filesize} -gt 0 && itest 0x${filesize} -le 0x4000 && itest 0x${filesize} -eq 0x${pf_trial_script_size}; then
                        if fatload mmc 0:1 0x48000000 "${pf_trial_dir}/boot-control.scr" 0x${pf_trial_script_size} && itest 0x${filesize} -eq 0x${pf_trial_script_size}; then
                            if hash sha256 0x48000000 0x${pf_trial_script_size} pf_actual_sha && test "${pf_actual_sha}" = "${pf_trial_script_sha}"; then
                                mw.b 0x47400000 0 1
                                if fatwrite mmc 0:1 0x47400000 boot-maint/trial-state.bin 1 && fatload mmc 0:1 0x47400100 boot-maint/trial-state.bin 1 && itest 0x${filesize} -eq 1 && cmp.b 0x47400000 0x47400100 1; then
                                    setenv pf_boot_role candidate
                                    source 0x48000000
                                fi
                            fi
                        fi
                    fi
                fi
            fi
        fi
    fi
fi
setenv pf_archive_saved_trial_build "${pf_trial_build}"
setenv pf_archive_saved_build "${build}"
setenv pf_archive_saved_role "${pf_boot_role}"
setenv pf_trial_build
setenv pf_archive_expected_build
if fatsize mmc 0:1 boot-maint/trial.env && itest 0x${filesize} -gt 0 && itest 0x${filesize} -le 0x200; then
    setenv pf_archive_selector_size ${filesize}
    if fatload mmc 0:1 0x47600000 boot-maint/trial.env 0x${pf_archive_selector_size} && itest 0x${filesize} -eq 0x${pf_archive_selector_size}; then
        if env import -t 0x47600000 0x${pf_archive_selector_size} pf_trial_build; then
            if setexpr pf_bad sub '^working-control-[0-9a-f]+$' '' "${pf_trial_build}" && test -n "${pf_trial_build}" && test -z "${pf_bad}"; then
                setenv pf_archive_expected_build ${pf_trial_build}
            fi
        fi
    fi
fi
setenv build
setenv pf_boot_role
setenv pf_archive_uboot_saved 0
setenv pf_archive_linux_saved 0
if test -n "${pf_archive_expected_build}" && fatsize mmc 0:1 linux-sd/logs/uboot-last.txt && itest 0x${filesize} -gt 0 && itest 0x${filesize} -le 0x1000; then
    setenv pf_archive_uboot_size ${filesize}
    if fatload mmc 0:1 0x47800000 linux-sd/logs/uboot-last.txt 0x${pf_archive_uboot_size} && itest 0x${filesize} -eq 0x${pf_archive_uboot_size}; then
        if env import -t 0x47800000 0x${pf_archive_uboot_size} pf_boot_role build; then
            if test "${pf_boot_role}" = candidate && test "${build}" = "${pf_archive_expected_build}"; then
                if fatwrite mmc 0:1 0x47800000 boot-maint/failed-trial-uboot.txt 0x${pf_archive_uboot_size} && fatload mmc 0:1 0x47b00000 boot-maint/failed-trial-uboot.txt 0x${pf_archive_uboot_size} && itest 0x${filesize} -eq 0x${pf_archive_uboot_size} && cmp.b 0x47800000 0x47b00000 0x${pf_archive_uboot_size}; then
                    setenv pf_archive_uboot_saved 1
                    if fatsize mmc 0:1 linux-sd/logs/linux-last.txt && itest 0x${filesize} -gt 0 && itest 0x${filesize} -le 0x20000; then
                        setenv pf_archive_linux_size ${filesize}
                        if fatload mmc 0:1 0x47900000 linux-sd/logs/linux-last.txt 0x${pf_archive_linux_size} && itest 0x${filesize} -eq 0x${pf_archive_linux_size}; then
                            if fatwrite mmc 0:1 0x47900000 boot-maint/failed-trial-linux.txt 0x${pf_archive_linux_size} && fatload mmc 0:1 0x47b00000 boot-maint/failed-trial-linux.txt 0x${pf_archive_linux_size} && itest 0x${filesize} -eq 0x${pf_archive_linux_size} && cmp.b 0x47900000 0x47b00000 0x${pf_archive_linux_size}; then
                                setenv pf_archive_linux_saved 1
                            fi
                        fi
                    fi
                    if fatsize mmc 0:1 linux-sd/logs/dmesg.txt && itest 0x${filesize} -gt 0 && itest 0x${filesize} -le 0x10000; then
    setenv pf_archive_extra_size ${filesize}
    if fatload mmc 0:1 0x47900000 linux-sd/logs/dmesg.txt 0x${pf_archive_extra_size} && itest 0x${filesize} -eq 0x${pf_archive_extra_size}; then
        if fatwrite mmc 0:1 0x47900000 boot-maint/failed-trial-dmesg.txt 0x${pf_archive_extra_size} && fatload mmc 0:1 0x47b00000 boot-maint/failed-trial-dmesg.txt 0x${pf_archive_extra_size} && itest 0x${filesize} -eq 0x${pf_archive_extra_size} && cmp.b 0x47900000 0x47b00000 0x${pf_archive_extra_size}; then
            setenv pf_archive_dmesg_saved 1
        fi
    fi
fi
if fatsize mmc 0:1 linux-sd/logs/kernel.txt && itest 0x${filesize} -gt 0 && itest 0x${filesize} -le 0x4000; then
    setenv pf_archive_extra_size ${filesize}
    if fatload mmc 0:1 0x47900000 linux-sd/logs/kernel.txt 0x${pf_archive_extra_size} && itest 0x${filesize} -eq 0x${pf_archive_extra_size}; then
        if fatwrite mmc 0:1 0x47900000 boot-maint/failed-trial-kernel.txt 0x${pf_archive_extra_size} && fatload mmc 0:1 0x47b00000 boot-maint/failed-trial-kernel.txt 0x${pf_archive_extra_size} && itest 0x${filesize} -eq 0x${pf_archive_extra_size} && cmp.b 0x47900000 0x47b00000 0x${pf_archive_extra_size}; then
            setenv pf_archive_kernel_saved 1
        fi
    fi
fi
                fi
            fi
        fi
    fi
fi
setenv pf_trial_build "${pf_archive_saved_trial_build}"
setenv build "${pf_archive_saved_build}"
setenv pf_boot_role "${pf_archive_saved_role}"
run pf_recovery
