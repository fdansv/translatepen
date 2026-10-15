# Using the pen outside the home network

`scripts/pen_gateway.py` provides a small authenticated origin for Cloudflare
Tunnel. One device token covers OCR and the pen's Migaku operations. It is
separate from `MIGAKU_API_TOKEN`; the latter stays on the server. The gateway
requires authentication on every route, including health checks, and binds
only to loopback. Keep the original OCR service on a private network.

The gateway uses Python's standard library and does not require another
browser, extension profile or OCR model. The existing services continue to
handle inference, vocabulary status and durable card submission.

The author's MSE09 was verified against a published Cloudflare hostname on
2026-10-09 using its existing Qt 5.12.2 / OpenSSL 1.0.2n and CA bundle with
certificate verification enabled. Native OCR, analysis, invalid ingestion/
known validation and job polling passed. A physical scan through a phone
hotspot remains a separate unverified check.

## Server setup

The supplied [user service](../server/translatepen-gateway.service) assumes
checkouts at `~/repos/translatepen` and `~/repos/migaku-api`. It loads the
existing private Migaku `.runtime/service.env`, which must define
`MIGAKU_API_TOKEN`. Adjust these paths for your installation.

Generate a device token without displaying it:

```sh
python3 - <<'PY'
import os, secrets
from pathlib import Path
directory = Path('.runtime')
directory.mkdir(mode=0o700, exist_ok=True)
directory.chmod(0o700)
fd = os.open(directory / 'pen.token', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(secrets.token_urlsafe(32) + '\n')
PY
```

Create `.runtime/gateway.env` with mode `0600`:

```text
TRANSLATEPEN_GATEWAY_TOKEN_FILE=/absolute/path/to/translatepen/.runtime/pen.token
TRANSLATEPEN_OCR_ORIGIN=http://YOUR_PRIVATE_SERVER_IP:8193
TRANSLATEPEN_MIGAKU_ORIGIN=http://127.0.0.1:8766
```

The OCR origin must match its listening address. The gateway defaults to port
8196, OCR on `127.0.0.1:8193`, and Migaku on `127.0.0.1:8766`. Start it:

```sh
cp server/translatepen-gateway.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now translatepen-gateway.service
```

Add a published application to your existing Cloudflare tunnel:

| Setting | Value |
| --- | --- |
| Public hostname | `pen.example.com` (your domain) |
| Service type | HTTP |
| Origin URL | `http://127.0.0.1:8196` |
| Path | Empty |

The origin must be reachable from the tunnel connector's network namespace.
This example assumes `cloudflared` runs on the host. The public connection
uses HTTPS; the HTTP hop stays on loopback. No router port forwarding is
needed. A browser-based Cloudflare Access login would prevent the pen from
connecting; this route uses the gateway's bearer authentication.

See [Cloudflare's published application documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/).

## Pen setup

Build and install the current native plugin using the [setup guide](setup.md).
`ScanBridge` now reads `/userdata/translatepen/ocr.json`. Keep the default
`Native.ScanBridge { id: defaultScanner }` declaration in `Japanese.qml`;
an explicit QML `endpoint` overrides the JSON address.

Create these two files privately, copying the device token from `pen.token`:

| File on pen | `endpoint` value |
| --- | --- |
| `/userdata/translatepen/ocr.json` | `https://pen.example.com/ocr` |
| `/userdata/translatepen/migaku.json` | `https://pen.example.com/migaku` |

Each file has the same shape, with your private device token:

```json
{"endpoint": "https://pen.example.com/ocr", "token": "YOUR_PRIVATE_DEVICE_TOKEN"}
```

Set both files to mode `0600` and restart the pen application. Keep generated
files in ignored private storage and never include credentials in commands,
screenshots or Git. The pen must have working Internet/DNS access, a correct
clock, and Qt/OpenSSL support plus trusted CA certificates for HTTPS. Verify
certificate validation on the actual device before relying on remote use.

## Available routes and verification

The gateway permits only:

- `POST /ocr`, `GET /ocr/health`
- `POST /migaku/text/analyze`, `POST /migaku/text/translate`, `POST /migaku/ingest`
- `POST /migaku/words/known`, `GET /migaku/health`
- `GET /migaku/jobs/{uuid}`

Other routes, query strings, encoded/traversal paths and wrong methods are
rejected. Image uploads are capped at 2 MB; JSON requests at 64 KB. Upstream
redirects are rejected. The pen's idempotency header is preserved. The gateway
does not log credentials, scan text or request URLs, and returns `no-store`
responses. Its connections and upstream response sizes are bounded.

Run `python3 -m unittest discover -s tests -p 'pen_gateway.py'`. Then verify
missing/invalid tokens return `401` over public HTTPS, authenticated OCR and
Migaku analysis succeed, and an actual scan works on the pen through a phone
hotspot. Check a double-B submission separately in your account; host tests
do not establish physical capture, TLS compatibility or outside-LAN operation.

## Revocation and rollback

The gateway rereads `pen.token` on every request. Atomically replacing it
revokes the old device credential without restarting either backend. Update
both pen JSON files and restart the pen application after issuing a new token.
The Migaku administrator credential remains independent.

To remove remote access, delete the Cloudflare route and disable the gateway
with `systemctl --user disable --now translatepen-gateway.service`. Restore
your previous pen `migaku.json` and native plugin; remove `ocr.json` to return
to the historical LAN OCR default (or configure your LAN endpoint explicitly).
Preserve backups before replacing installed pen files.
