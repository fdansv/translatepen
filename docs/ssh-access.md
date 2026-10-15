# Root SSH access on your own MSE09

On the author's V2.2.83 pen, the SSH server was already running before any
application patches. Root login worked over Wi-Fi using the platform's
[documented default login](https://rockchip.wikidot.com/linux-develop-guide#toc8).
No firmware flashing, case opening, serial adapter or custom hardware was
needed to obtain that access. This was verified on **one unit**, not across
retail batches. The linked guide describes a Rockchip development board;
it is evidence for the credential we tried, not an MSE09 compatibility promise.

## Check access before installing anything

1. Connect your own pen to your Wi-Fi using its stock settings.
2. Find its IP in your router's client list. Keep the pen awake during testing.
3. From the same LAN, try the SSH connection with the root credentials applicable
   to your unit. SSH prompts for the password; do not put it in command arguments.

```sh
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@YOUR_PEN_IP
```

Confirm the first host-key prompt only after checking you are contacting your
own device. A changed key on an existing address needs investigation; this
guide does not disable host-key verification.

After logging in, these commands only read system state:

```sh
id
uname -m
sha256sum /oem/scanpen
df -h /oem /userdata
```

The supported original executable hash is
`606ba41856bbdc7b432d759a43c1ff786b17662d672bd44dacf3913cb644663c`.
`id` must show root and the architecture must be `aarch64`.
The version label alone does not establish compatibility.

Exit the shell, then run the read-only host check from the repository:

```sh
python3 scripts/check_pen.py root@YOUR_PEN_IP
```

It checks identity, architecture, executable/backup hashes, basic device tools,
and a conservative free-space minimum. It does not enable SSH, change files,
or approve an already modified installation as a fresh unit.

## If access fails

- Timeout: check power, Wi-Fi address and whether your network isolates clients.
- Connection refused: SSH is not listening at that address. We have no verified
  enable-SSH procedure for that firmware/unit.
- Authentication rejected: we have no verified password-reset procedure for
  that unit. Do not assume that the author's credential applies to it.
- Wrong executable hash: stop before patching; a different version needs a new
  compatibility review.

The project cannot currently guarantee root access before buying a new retail
pen. Keep its SSH service on your trusted network; do not publish it through
the OCR/Migaku gateway or router port forwarding.
