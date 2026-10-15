#!/bin/sh
# Run ON THE PEN. Restores the saved original application; dictionary data stays.
set -eu
prefix=${TRANSLATEPEN_TEST_ROOT:-}
original=$prefix/userdata/translatepen/backups/scanpen.original
expected=606ba41856bbdc7b432d759a43c1ff786b17662d672bd44dacf3913cb644663c
if [ -n "$prefix" ]; then
    [ "$prefix" != / ] && [ -f "$prefix/.translatepen-test-root" ] || exit 1
    expected=${TRANSLATEPEN_TEST_EXPECTED:?Offline fixture checksum required}
else
    [ "$(id -u)" = 0 ] && [ "$(uname -m)" = aarch64 ] || { echo 'Run this on the MSE09.' >&2; exit 1; }
fi
[ ! -L "$original" ] || { echo 'Refusing a symlink as the original backup'; exit 1; }
actual=$(sha256sum "$original" | cut -d ' ' -f 1)
[ "$actual" = "$expected" ] || { echo 'Original backup checksum mismatch'; exit 1; }
cp -p "$original" "$prefix/oem/scanpen.restore"
chmod 755 "$prefix/oem/scanpen.restore"
mv "$prefix/oem/scanpen.restore" "$prefix/oem/scanpen"
sync
# The existing vendor watchdog restarts the application with its normal setup.
if [ -z "$prefix" ]; then killall -KILL scanpen || true; fi
echo 'Original application restored; vendor watchdog will restart it.'
