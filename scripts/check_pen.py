#!/usr/bin/env python3
"""Read-only SSH compatibility and storage check. Never installs or changes pen files."""
import argparse
import json
from pathlib import Path
import re
import subprocess

EXPECTED = '606ba41856bbdc7b432d759a43c1ff786b17662d672bd44dacf3913cb644663c'
PROBE = r'''
printf 'uid=%s\n' "$(id -u)"
printf 'architecture=%s\n' "$(uname -m)"
if [ -f /oem/scanpen ]; then printf 'application=%s\n' "$(sha256sum /oem/scanpen | cut -d ' ' -f 1)"; fi
if [ -f /userdata/translatepen/backups/scanpen.original ]; then
  printf 'original_backup=%s\n' "$(sha256sum /userdata/translatepen/backups/scanpen.original | cut -d ' ' -f 1)"
fi
for name in oem userdata; do
  printf '%s_available_kib=%s\n' "$name" "$(df -Pk /$name | awk 'END {print $4}')"
done
for name in sha256sum tar cp mv sync killall; do
  command -v "$name" >/dev/null 2>&1 || printf 'missing_command=%s\n' "$name"
done
'''


def assess(output):
    values = {}
    missing = []
    for line in output.splitlines():
        key, separator, value = line.partition('=')
        if separator:
            if key == 'missing_command':
                missing.append(value)
            else:
                values[key] = value
    failures, warnings = [], []
    if values.get('uid') != '0':
        failures.append('The SSH account is not root.')
    if values.get('architecture') != 'aarch64':
        failures.append('Expected an AArch64 MSE09 running Buildroot Linux.')
    if values.get('application') != EXPECTED:
        if values.get('original_backup') == EXPECTED:
            warnings.append('The application is modified; a supported original backup exists. This is not a fresh-install approval.')
        else:
            failures.append('The original application checksum is unsupported or no verified original backup is available.')
    for name, minimum in [('oem', 32768), ('userdata', 786432)]:
        try:
            available = int(values.get(name + '_available_kib', ''))
        except ValueError:
            failures.append(f'Could not determine free space on /{name}.')
            continue
        if available < minimum:
            failures.append(f'/{name} needs at least {minimum // 1024} MiB free for the documented staging and backups.')
    if missing:
        failures.append('Missing device tools: ' + ', '.join(missing))
    return {'compatible_original': values.get('application') == EXPECTED,
            'fresh_install_checks_passed': not failures and not warnings,
            'observed': values, 'failures': failures, 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='SSH target, e.g. root@192.168.1.123')
    parser.add_argument('--identity', type=Path, help='Optional existing private SSH key; passwords are entered in SSH itself')
    args = parser.parse_args()
    if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9_.:-]*', args.target):
        parser.error('Use a hostname/IP with an optional user@ prefix, not SSH options or a URL.')
    command = ['ssh', '-T', '-o', 'ConnectTimeout=8']
    if args.identity:
        command += ['-i', str(args.identity)]
    command += [args.target, 'sh -s']
    result = subprocess.run(command, input=PROBE, text=True, stdout=subprocess.PIPE)
    if result.returncode:
        return result.returncode
    report = assess(result.stdout)
    print(json.dumps(report, indent=2))
    return 0 if report['fresh_install_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
