#!/usr/bin/env python3
"""A bearer-authenticated, restricted HTTP origin for Cloudflare Tunnel.

Only the pen's OCR and Migaku operations are forwarded. The device credential
is independent of the Migaku API credential, and is reread for every request.
"""
import hmac
import http.client
import ipaddress
import json
import os
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def read_token(path):
    path = Path(path)
    if path.stat().st_mode & 0o077:
        raise ValueError("The pen token file must have mode 0600 or stricter")
    token = path.read_bytes().strip()
    if not 32 <= len(token) <= 128 or not re.fullmatch(rb"[A-Za-z0-9_-]+", token):
        raise ValueError("The pen token must contain 32-128 URL-safe characters")
    return token


def origin(address):
    parsed = urlsplit(address)
    if (parsed.scheme != "http" or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Origins must be plain HTTP addresses without paths or credentials")
    host = parsed.hostname
    if host != "localhost" and not ipaddress.ip_address(host).is_private:
        raise ValueError("Origins must be local/private addresses")
    return host, parsed.port or 80


def route(method, path):
    exact = {
        ("GET", "/ocr/health"): ("ocr", "/health", 0),
        ("POST", "/ocr"): ("ocr", "/ocr", 2_000_000),
        ("GET", "/migaku/health"): ("migaku", "/health", 0),
        ("POST", "/migaku/text/analyze"): ("migaku", "/text/analyze", 64_000),
        ("POST", "/migaku/text/translate"): ("migaku", "/text/translate", 16_000),
        ("POST", "/migaku/ingest"): ("migaku", "/ingest", 64_000),
        ("POST", "/migaku/words/known"): ("migaku", "/words/known", 64_000),
    }
    if (method, path) in exact:
        return exact[method, path]
    if method == "GET" and re.fullmatch(r"/migaku/jobs/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", path):
        return "migaku", path[len("/migaku"):], 0
    return None


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, token_file, ocr_origin, migaku_origin, migaku_token):
        read_token(token_file)  # Refuse to start with a missing/insecure credential.
        if not migaku_token or "\n" in migaku_token or "\r" in migaku_token:
            raise ValueError("MIGAKU_API_TOKEN is required")
        self.token_file = Path(token_file)
        self.origins = {"ocr": origin(ocr_origin), "migaku": origin(migaku_origin)}
        self.migaku_token = migaku_token
        self.slots = threading.BoundedSemaphore(12)
        super().__init__(address, GatewayHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PenGateway"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # Never log authorization headers, scanned text or request URLs.

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"error": "request rejected"})

    def reply(self, status, body, content_type="application/json", challenge=False):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if challenge:
            self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(data)
        except OSError:
            pass

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def forward(self):
        try:
            expected = b"Bearer " + read_token(self.server.token_file)
        except (OSError, ValueError):
            self.reply(503, {"error": "device authentication unavailable"})
            return
        credentials = self.headers.get_all("Authorization", [])
        if len(credentials) != 1 or not hmac.compare_digest(credentials[0].encode(), expected):
            self.reply(401, {"error": "a valid pen bearer token is required"}, challenge=True)
            return
        target = route(self.command, self.path)
        if target is None:
            self.reply(404, {"error": "not found"})
            return
        service, path, limit = target
        lengths = self.headers.get_all("Content-Length", [])
        if (self.headers.get("Transfer-Encoding") or self.headers.get("Content-Encoding")
                or len(lengths) > 1 or (lengths and not re.fullmatch(r"[0-9]{1,9}", lengths[0]))):
            self.reply(400, {"error": "unsupported request framing"})
            return
        length = int(lengths[0]) if lengths else 0
        if length > limit or (self.command == "POST" and length == 0):
            self.reply(413, {"error": "request body is outside the allowed size"})
            return
        content_type = "image/bmp" if service == "ocr" else "application/json"
        if self.command == "POST" and self.headers.get("Content-Type", "").split(";")[0].strip() != content_type:
            self.reply(415, {"error": "unsupported content type"})
            return
        try:
            body = self.rfile.read(length) if length else None
        except (OSError, socket.timeout):
            self.reply(408, {"error": "upload timed out"})
            return
        if body is not None and len(body) != length:
            self.reply(400, {"error": "incomplete request body"})
            return
        headers = {"Content-Type": content_type}
        if service == "migaku":
            headers["Authorization"] = "Bearer " + self.server.migaku_token
            keys = self.headers.get_all("Idempotency-Key", [])
            if keys:
                if len(keys) != 1 or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", keys[0]):
                    self.reply(400, {"error": "invalid idempotency key"})
                    return
                headers["Idempotency-Key"] = keys[0]
        connection = http.client.HTTPConnection(*self.server.origins[service], timeout=30)
        try:
            connection.request(self.command, path, body=body, headers=headers)
            result = connection.getresponse()
            data = result.read(4_000_001)
            if len(data) > 4_000_000 or 300 <= result.status < 400:
                self.reply(502, {"error": "invalid upstream response"})
                return
            self.reply(result.status, data, result.getheader("Content-Type", "application/json"))
        except (OSError, http.client.HTTPException):
            self.reply(502, {"error": "home service unavailable"})
        finally:
            connection.close()


def main():
    bind = os.environ.get("TRANSLATEPEN_GATEWAY_BIND", "127.0.0.1")
    if bind not in {"127.0.0.1", "localhost"}:
        raise ValueError("The tunnel gateway must bind to loopback")
    server = GatewayServer(
        (bind, int(os.environ.get("TRANSLATEPEN_GATEWAY_PORT", "8196"))),
        os.environ["TRANSLATEPEN_GATEWAY_TOKEN_FILE"],
        os.environ.get("TRANSLATEPEN_OCR_ORIGIN", "http://127.0.0.1:8193"),
        os.environ.get("TRANSLATEPEN_MIGAKU_ORIGIN", "http://127.0.0.1:8766"),
        os.environ.get("MIGAKU_API_TOKEN", ""))
    print("Pen gateway ready on loopback", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
