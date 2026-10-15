#!/bin/sh
# Run ON THE PEN from a directory created by stage_pen.py. Stock application required.
# No partitions or vendor startup scripts are flashed/modified. Backups are retained.
set -eu
umask 077
prefix=${TRANSLATEPEN_TEST_ROOT:-}
expected=606ba41856bbdc7b432d759a43c1ff786b17662d672bd44dacf3913cb644663c
if [ -n "$prefix" ]; then
    [ "$prefix" != / ] && [ -f "$prefix/.translatepen-test-root" ] || exit 1
    expected=${TRANSLATEPEN_TEST_EXPECTED:?Offline fixture checksum required}
else
    [ "$(id -u)" = 0 ] && [ "$(uname -m)" = aarch64 ] || { echo 'Run this on the root-accessible MSE09, not the build computer.' >&2; exit 1; }
fi
stage=$(pwd)
base=$prefix/userdata/translatepen
native=$prefix/usr/qml/TranslatePen/Native
application=$prefix/oem/scanpen
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
[ "$(hash "$application")" = "$expected" ] || { echo 'Current application is not the supported original. Restore stock first; refusing an unknown or live modified application.' >&2; exit 1; }
for item in app Native dictionary.sqlite deinflect.json scanpen ocr.json restore_pen.sh; do
    [ -e "$stage/$item" ] || { echo "Missing staging item: $item" >&2; exit 1; }
done
sha256sum -c SHA256SUMS
for path in "$base" "$base/app" "$native" "$base/dictionary.sqlite" "$base/ocr.json" "$base/migaku.json"; do
    [ ! -L "$path" ] || { echo 'Refusing a symlink at an installation destination.' >&2; exit 1; }
done
if [ -e "$base/backups/scanpen.original" ]; then
    [ "$(hash "$base/backups/scanpen.original")" = "$expected" ] || { echo 'Existing original backup has the wrong checksum.' >&2; exit 1; }
fi
# Allow the staged payload, a complete backup of existing managed files, and
# extra metadata space. Staging has already consumed its own disk space.
needed=$(du -sk "$stage" | awk '{print $1}')
set -- oem/scanpen
for item in app dictionary.sqlite deinflect.json ocr.json migaku.json restore_pen.sh ATTRIBUTION.txt YOMICHAN-LICENSE LICENSE; do
    if [ -e "$base/$item" ]; then
        needed=$((needed + $(du -sk "$base/$item" | awk '{print $1}')))
        set -- "$@" "userdata/translatepen/$item"
    fi
done
if [ -e "$native" ]; then
    needed=$((needed + $(du -sk "$native" | awk '{print $1}')))
    set -- "$@" usr/qml/TranslatePen/Native
fi
available=$(df -Pk "$prefix/userdata" | awk 'END {print $4}')
[ "$available" -ge $((needed + 32768)) ] || { echo 'Insufficient /userdata space for installation and retained backups.' >&2; exit 1; }
binary_kib=$(du -k "$stage/scanpen" | awk '{print $1}')
available=$(df -Pk "$prefix/oem" | awk 'END {print $4}')
[ "$available" -ge $((binary_kib + 2048)) ] || { echo 'Insufficient /oem space for atomic executable replacement.' >&2; exit 1; }
available=$(df -Pk "$prefix/usr/qml" | awk 'END {print $4}')
native_kib=$(du -sk "$stage/Native" | awk '{print $1}')
[ "$available" -ge $((native_kib + 2048)) ] || { echo 'Insufficient native-module filesystem space.' >&2; exit 1; }
mkdir -p "$base/backups" "$(dirname "$native")"
backup=$base/backups/install-$(date +%Y%m%dT%H%M%S)-$$
mkdir "$backup"
tar -cf "$backup/files.tar" -C "${prefix:-/}" "$@"
if [ ! -e "$base/backups/scanpen.original" ]; then
    cp -p "$application" "$base/backups/scanpen.original.new"
    [ "$(hash "$base/backups/scanpen.original.new")" = "$expected" ]
    mv "$base/backups/scanpen.original.new" "$base/backups/scanpen.original"
fi
printf 'Backup: %s\n' "$backup/files.tar"
trap 'echo "Installation stopped. Retained backup: $backup/files.tar. The executable is replaced only after all data is installed." >&2' 0
# The stock application does not use these trees, so stage each directory
# completely before switching it. Keep previous directories for recovery.
for pair in app Native; do
    if [ "$pair" = app ]; then destination=$base/app; else destination=$native; fi
    cp -a "$stage/$pair" "$destination.new.$$"
    if [ -e "$destination" ]; then mv "$destination" "$destination.previous.$$"; fi
    mv "$destination.new.$$" "$destination"
done
for item in dictionary.sqlite deinflect.json ocr.json migaku.json restore_pen.sh ATTRIBUTION.txt YOMICHAN-LICENSE LICENSE; do
    if [ -f "$stage/$item" ]; then
        cp "$stage/$item" "$base/$item.new.$$"
        case "$item" in *.json) chmod 600 "$base/$item.new.$$";; *) chmod 644 "$base/$item.new.$$";; esac
        mv "$base/$item.new.$$" "$base/$item"
    fi
done
cp "$stage/scanpen" "$application.new.$$"
chmod 755 "$application.new.$$"
[ "$(hash "$application.new.$$")" = "$(hash "$stage/scanpen")" ]
sync
mv "$application.new.$$" "$application"
sync
trap - 0
if [ -z "$prefix" ]; then killall -KILL scanpen || true; fi
echo 'Files installed. The existing vendor watchdog restarts scanpen. Verify a physical scan before calling installation successful.'
