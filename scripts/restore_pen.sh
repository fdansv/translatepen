#!/bin/sh
# Run ON THE PEN. Restores the saved original application; dictionary data stays.
set -eu
original=/userdata/translatepen/backups/scanpen.original
expected=606ba41856bbdc7b432d759a43c1ff786b17662d672bd44dacf3913cb644663c
actual=$(sha256sum "$original" | cut -d ' ' -f 1)
[ "$actual" = "$expected" ] || { echo 'Original backup checksum mismatch'; exit 1; }
cp -p "$original" /oem/scanpen.restore
chmod 777 /oem/scanpen.restore
mv /oem/scanpen.restore /oem/scanpen
sync
# The existing vendor watchdog restarts the application with its normal setup.
killall -KILL scanpen || true
echo 'Original application restored; vendor watchdog will restart it.'
