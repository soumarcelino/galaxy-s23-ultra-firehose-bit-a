#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
export LC_ALL=C
umask 077

action=${1:-check}
if (( $# > 1 )) || [[ "$action" != check && "$action" != backup-init-boot ]]; then
    echo 'Usage: ./firehose.sh [check|backup-init-boot]' >&2
    exit 2
fi
if [[ ! -x .tools/qdl ]]; then
    echo 'Run ./setup.sh first.' >&2
    exit 1
fi
device_count=$(lsusb | awk '$6 == "05c6:9008" {n++} END {print n+0}')
if [[ "$device_count" != 1 ]]; then
    echo "Connect one Galaxy in EDL mode. Devices found: $device_count." >&2
    exit 1
fi

qdl=(timeout 90s .tools/qdl --quiet --backend=usb --storage=ufs --skip-reset loader/sm-s918b-bit-a-firehose.elf)
if [[ "$action" == check ]]; then
    reply=$("${qdl[@]}" sha256 0/0+1)
    if [[ ! "$reply" =~ ^[[:xdigit:]]{64}$ ]]; then
        echo 'The phone did not confirm the connection.' >&2
        exit 1
    fi
    echo 'Firehose is ready.'
    exit 0
fi

mkdir -p backups
backup=$(mktemp -d "backups/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
partial="$backup/init_boot.part"
trap 'rm -f -- "$partial"; rmdir -- "$backup" 2>/dev/null || true' EXIT
echo 'Reading init_boot…'
reply=$("${qdl[@]}" read 0/init_boot "$partial" sha256 0/init_boot)
expected=$(sed -nE '/^[[:xdigit:]]{64}$/p' <<< "$reply")
actual=$(sha256sum "$partial")
if [[ ! "$expected" =~ ^[[:xdigit:]]{64}$ || "${expected,,}" != "${actual%% *}" ]]; then
    echo 'The backup could not be verified.' >&2
    exit 1
fi
mv -- "$partial" "$backup/init_boot.img"
echo "Saved and verified $backup/init_boot.img"
