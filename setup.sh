#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

packages=(gcc pkgconf git meson ninja libusb libxml2 usbutils python)
if ! pacman -T "${packages[@]}" >/dev/null; then
    sudo pacman -S --needed "${packages[@]}"
fi

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
echo 'Preparing QDL for the Galaxy S23 Ultra…'
if ! (
    git -c advice.detachedHead=false clone -q --depth 1 --branch v2.9.1 \
        https://github.com/linux-msm/qdl.git "$work/source" &&
    meson setup "$work/build" "$work/source" -Dzip-container=disabled \
        -Dudev=enabled -Dtests=disabled -Dnbdkit=disabled &&
    meson compile -C "$work/build" qdl
) >"$work/build.log" 2>&1; then
    cat "$work/build.log" >&2
    exit 1
fi

rule=/etc/udev/rules.d/70-qdl.rules
if ! cmp -s "$work/build/70-qdl.rules" "$rule"; then
    sudo install -Dm644 "$work/build/70-qdl.rules" "$rule"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=05c6 --attr-match=idProduct=9008 --action=add
fi
install -Dm755 "$work/build/qdl" .tools/qdl
echo 'Ready. Connect the phone in EDL mode and run ./firehose.sh check.'
