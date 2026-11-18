#!/bin/sh
# Light is already on during the four-second Qt countdown. Restore it even if
# the parent application disappears. A photo-only full-size mode is journaled
# and restored before scanning resumes; sensor calibration/crop stays unchanged.
set -eu
prefix=$1
previous=$2
case "$prefix" in /mnt/sdcard/translatepen/photos/.capture-*|/userdata/translatepen/manga-stage/photos/.capture-*) ;; *) exit 2;; esac
case "$previous" in ''|*[!0-9]*) exit 2;; esac
led=${TRANSLATEPEN_LED_PATH:-/sys/class/leds/camera-led/brightness}
diag=${TRANSLATEPEN_DIAGNOSTICS_DIR:-/mnt/sdcard/translatepen/photo-diagnostics}
diagnostics=0
monitor=''
if [ -r "$diag/enabled-until" ]; then
    until=$(cat "$diag/enabled-until")
    case "$until" in ''|*[!0-9]*) ;; *)
        if [ "$(date +%s)" -lt "$until" ]; then diagnostics=1; fi;;
    esac
fi
trace() {
    if [ "$diagnostics" = 1 ]; then
        IFS=' ' read -r uptime rest < /proc/uptime
        printf '%s\t%s\tled=%s\n' "$uptime" "$1" "$(cat "$led" 2>/dev/null || echo unreadable)" >> "$diag/last.log" || true
    fi
    return 0
}
if [ "$diagnostics" = 1 ]; then
    printf 'capture=%s\n' "${prefix##*/}" > "$diag/last.log"
    trace helper_start
    (
        last='';ticks=0
        # Bounded even if the application/helper disappears unexpectedly.
        while [ "$ticks" -lt 600 ]; do
            value=$(cat "$led" 2>/dev/null || echo unreadable)
            if [ "$value" != "$last" ]; then trace light_transition;last=$value;fi
            ticks=$((ticks+1));sleep 0.02
        done
    ) & monitor=$!
fi
child=''
watchdog=''
old_exposure=''
old_format=''
journal=${prefix%/*}/.exposure-restore
format_journal=${prefix%/*}/.format-restore
cleanup() {
    result=$?
    if [ -n "$monitor" ]; then kill "$monitor" 2>/dev/null || true;wait "$monitor" 2>/dev/null || true; fi
    if [ -n "$watchdog" ]; then kill "$watchdog" 2>/dev/null || true; wait "$watchdog" 2>/dev/null || true; fi
    if [ -n "$child" ]; then kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi
    if [ -n "$old_format" ]; then
        if timeout 2 v4l2-ctl -d /dev/video0 "--set-fmt-video=$old_format"; then
            rm -f "$format_journal"
            trace format_restored
        else trace format_restore_failed;result=4; fi
    fi
    if [ -n "$old_exposure" ]; then
        if timeout 2 v4l2-ctl -d /dev/video0 "--set-ctrl=exposure=$old_exposure"; then
            rm -f "$journal"
            trace "exposure_restored_$old_exposure"
        else trace exposure_restore_failed;result=4; fi
    fi
    rm -f "$prefix.controls" "$prefix.original-format"
    trace before_light_restore
    printf '%s\n' "$previous" > "$led" || true
    trace after_light_restore
    trap - EXIT
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
bounded() {
    seconds=$1; shift
    "$@" & child=$!
    (sleep "$seconds"; kill "$child" 2>/dev/null || true) & watchdog=$!
    if wait "$child"; then status=0; else status=$?; fi
    child=''
    kill "$watchdog" 2>/dev/null || true; wait "$watchdog" 2>/dev/null || true; watchdog=''
    return "$status"
}
trace before_format_query
bounded 3 v4l2-ctl -d /dev/video0 --get-fmt-video > "$prefix.format"
trace after_format_query
full_resolution=${TRANSLATEPEN_PHOTO_FULL_RESOLUTION:-}
if [ -z "$full_resolution" ] && [ -r /userdata/translatepen/photo-full-resolution ]; then full_resolution=$(cat /userdata/translatepen/photo-full-resolution); fi
if [ "$full_resolution" = 1 ]; then
    width=$(sed -n 's/.*Width\/Height *: *\([0-9][0-9]*\) *\/ *[0-9][0-9]*.*/\1/p' "$prefix.format")
    height=$(sed -n 's/.*Width\/Height *: *[0-9][0-9]* *\/ *\([0-9][0-9]*\).*/\1/p' "$prefix.format")
    pixel=$(sed -n "s/.*Pixel Format *: *'\([A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9]\)'.*/\1/p" "$prefix.format")
    case "$width:$height:$pixel" in *[!A-Z0-9:]*|::*|*::*) exit 3;; esac
    case "$pixel" in NV21|NV12|YUYV) ;; *) exit 3;; esac
    if [ "$width" -lt 2 ] || [ "$width" -gt 528 ] || [ "$height" -lt 2 ] || [ "$height" -gt 360 ]; then exit 3; fi
    if [ "$width" != 528 ] || [ "$height" != 360 ]; then
        old_format="width=$width,height=$height,pixelformat=$pixel"
        printf '%s\n' "$old_format" > "$format_journal.pending"
        mv "$format_journal.pending" "$format_journal"
        cp "$prefix.format" "$prefix.original-format"
        if bounded 2 v4l2-ctl -d /dev/video0 "--set-fmt-video=width=528,height=360,pixelformat=$pixel"; then
            bounded 2 v4l2-ctl -d /dev/video0 --get-fmt-video > "$prefix.format"
            trace photo_full_resolution
        else
            # Unsupported/busy output resizing should retain normal capture.
            bounded 2 v4l2-ctl -d /dev/video0 "--set-fmt-video=$old_format"
            rm -f "$format_journal";old_format=''
            cp "$prefix.original-format" "$prefix.format"
            trace photo_full_resolution_unavailable
        fi
    fi
fi
wanted=${TRANSLATEPEN_PHOTO_EXPOSURE:-}
if [ -z "$wanted" ] && [ -r /userdata/translatepen/photo-exposure ]; then wanted=$(cat /userdata/translatepen/photo-exposure); fi
if [ "$diagnostics" = 1 ] && [ -r "$diag/exposure-test" ]; then wanted=$(cat "$diag/exposure-test"); fi
case "$wanted" in ''|*[!0-9]*) ;; *)
    if [ "$wanted" -ge 4 ] && [ "$wanted" -le 412 ]; then
        bounded 2 v4l2-ctl -d /dev/video0 --get-ctrl=exposure > "$prefix.controls"
        old_exposure=$(sed -n 's/^exposure: *\([0-9][0-9]*\).*$/\1/p' "$prefix.controls")
        case "$old_exposure" in ''|*[!0-9]*) exit 3;; esac
        printf '%s\n' "$old_exposure" > "$journal.pending"
        mv "$journal.pending" "$journal"
        bounded 2 v4l2-ctl -d /dev/video0 "--set-ctrl=exposure=$wanted"
        trace "photo_exposure_${old_exposure}_to_$wanted"
    fi;;
esac
trace before_stream
if [ "$diagnostics" = 1 ]; then bounded 2 v4l2-ctl -d /dev/video0 --list-ctrls > "$diag/capture-controls-before.txt"; fi
bounded 7 v4l2-ctl -d /dev/video0 --stream-mmap=3 --stream-skip=4 --stream-count=1 --stream-poll "--stream-to=$prefix.raw"
trace stream_returned
test -s "$prefix.raw"
trace raw_frame_complete
if [ "$diagnostics" = 1 ]; then bounded 2 v4l2-ctl -d /dev/video0 --list-ctrls > "$diag/capture-controls-after.txt"; fi
if [ "$diagnostics" = 1 ]; then
    # One bounded snapshot for a user-triggered shot; no photo history grows.
    if cp "$prefix.raw" "$diag/last.raw.pending" && mv "$diag/last.raw.pending" "$diag/last.raw" && cp "$prefix.format" "$diag/last.format"; then
        printf '%s\n' "${prefix##*/}" > "$diag/last-frame-id" || true
    else trace snapshot_failed; fi
fi
