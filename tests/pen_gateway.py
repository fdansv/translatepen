import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location("gateway", Path(__file__).resolve().parents[1] / "scripts/pen_gateway.py")
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.do_GET()

    def do_GET(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.requests.append((self.command, self.path, dict(self.headers), body))
        data = json.dumps({"path": self.path}).encode()
        self.send_response(self.server.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Location", "https://should-never-be-followed.invalid")
        self.end_headers()
        self.wfile.write(data)


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.token_file = Path(self.directory.name) / "pen.token"
        self.token = "a" * 43
        self.token_file.write_text(self.token)
        self.token_file.chmod(0o600)
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        self.upstream.requests, self.upstream.status = [], 200
        upstream_url = "http://127.0.0.1:" + str(self.upstream.server_port)
        self.server = gateway.GatewayServer(("127.0.0.1", 0), self.token_file, upstream_url, upstream_url, "upstream-only-secret")
        for server in (self.upstream, self.server):
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def tearDown(self):
        for server in (self.server, self.upstream):
            server.shutdown()
            server.server_close()
        self.directory.cleanup()

    def request(self, method="GET", path="/ocr/health", body=None, token=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        request_headers = {"Authorization": "Bearer " + (token or self.token)}
        request_headers.update(headers or {})
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        status, result_headers, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, result_headers, data

    def test_auth_before_body_or_upstream(self):
        for auth in ("", "Bearer wrong", "Basic " + self.token, "Bearer "+"\u00ff"*43):
            status, headers, _ = self.request("POST", "/ocr", headers={"Authorization": auth, "Content-Length": "2000000"})
            self.assertEqual(status, 401)
            self.assertEqual(headers["WWW-Authenticate"], "Bearer")
            self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.upstream.requests, [])

    def test_allowlist_blocks_admin_traversal_queries_and_wrong_methods(self):
        for method, path in [("GET", "/migaku/docs"), ("GET", "/migaku/jobs"),
                             ("GET", "/migaku/worker"), ("POST", "/migaku/cards"),
                             ("GET", "/migaku/../worker"), ("GET", "/migaku/%2e%2e/worker"),
                             ("GET", "/ocr/health?token=x"), ("GET", "/ocr"),
                             ("POST", "/migaku/jobs/123/reconcile")]:
            self.assertEqual(self.request(method, path)[0], 404, path)
        self.assertEqual(self.upstream.requests, [])

    def test_migaku_uses_private_token_and_preserves_idempotency(self):
        status, headers, _ = self.request("POST", "/migaku/ingest", b'{"sentence":"test"}',
                                          headers={"Content-Type": "application/json", "Idempotency-Key": "pen:123"})
        self.assertEqual(status, 200)
        method, path, forwarded, data = self.upstream.requests[-1]
        self.assertEqual((method, path, data), ("POST", "/ingest", b'{"sentence":"test"}'))
        self.assertEqual(forwarded["Authorization"], "Bearer upstream-only-secret")
        self.assertEqual(forwarded["Idempotency-Key"], "pen:123")
        self.assertNotIn("Location", headers)

    def test_ocr_never_receives_device_or_migaku_credentials(self):
        self.assertEqual(self.request("POST", "/ocr", b"BM", headers={"Content-Type": "image/bmp"})[0], 200)
        self.assertNotIn("Authorization", self.upstream.requests[-1][2])

    def test_all_pen_routes_and_job_uuid(self):
        for path in ("/migaku/text/analyze", "/migaku/text/translate", "/migaku/words/known"):
            self.assertEqual(self.request("POST", path, b"{}", headers={"Content-Type": "application/json"})[0], 200)
        for path in ("/ocr/health", "/migaku/health", "/migaku/jobs/01234567-89ab-cdef-0123-456789abcdef"):
            self.assertEqual(self.request(path=path)[0], 200)

    def test_body_size_encoding_and_content_type(self):
        for headers, expected in [({"Content-Length": "2000001"}, 413),
                                  ({"Transfer-Encoding": "chunked"}, 400),
                                  ({"Content-Encoding": "gzip"}, 400),
                                  ({"Content-Length": "invalid"}, 400),
                                  ({"Content-Length": "1" * 100}, 400),
                                  ({"Content-Length": "1", "Content-Type": "text/plain"}, 415)]:
            self.assertEqual(self.request("POST", "/ocr", headers=headers)[0], expected)
        self.assertEqual(self.upstream.requests, [])

    def test_upstream_unavailable_returns_generic_error(self):
        self.server.origins["ocr"] = ("127.0.0.1", 0)
        status, _, data = self.request()
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(data), {"error": "home service unavailable"})

    def test_bounded_connections_return_503_when_full(self):
        for _ in range(12):
            self.server.slots.acquire()
        try:
            self.assertEqual(self.request()[0], 503)
        finally:
            for _ in range(12):
                self.server.slots.release()

    def test_revocation_takes_effect_without_restart_and_fails_closed(self):
        self.assertEqual(self.request()[0], 200)
        self.token_file.write_text("b" * 43)
        self.assertEqual(self.request()[0], 401)
        self.assertEqual(self.request(token="b" * 43)[0], 200)
        self.token_file.unlink()
        self.assertEqual(self.request()[0], 503)

    def test_insecure_token_or_empty_upstream_secret_refuses_startup(self):
        self.token_file.chmod(0o644)
        with self.assertRaises(ValueError):
            gateway.read_token(self.token_file)
        self.token_file.chmod(0o600)
        with self.assertRaises(ValueError):
            gateway.GatewayServer(("127.0.0.1", 0), self.token_file, "http://127.0.0.1", "http://127.0.0.1", "")

    def test_redirects_are_not_followed_and_upstream_errors_pass_through(self):
        self.upstream.status = 302
        self.assertEqual(self.request()[0], 502)
        self.upstream.status = 429
        self.assertEqual(self.request()[0], 429)
        self.assertEqual(len(self.upstream.requests), 2)

    def test_duplicate_auth_and_lengths_rejected(self):
        for header, value, expected in [("Authorization", "Bearer " + self.token, 401), ("Content-Length", "0", 400)]:
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
            connection.putrequest("GET", "/ocr/health")
            connection.putheader("Authorization", "Bearer " + self.token)
            if header == "Content-Length":
                connection.putheader(header, value)
            connection.putheader(header, value)
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, expected)
            response.read()
            connection.close()
        self.assertEqual(self.upstream.requests, [])


if __name__ == "__main__":
    unittest.main()
