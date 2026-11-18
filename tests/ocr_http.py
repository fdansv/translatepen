"""A cancelled Windows client must not turn a completed OCR into a 400 error."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ocr_server


class ReplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recognizer = Mock()
        with patch.object(ocr_server, 'ThreadingHTTPServer') as server:
            ocr_server.serve(recognizer, '127.0.0.1', 0)
            cls.handler = server.call_args.args[1]

    def test_cancelled_headers_and_body_are_closed_without_second_response(self):
        for stage in ('end_headers', 'write'):
            for error in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                with self.subTest(stage=stage, error=error):
                    reply = Mock()
                    target = reply.end_headers if stage == 'end_headers' else reply.wfile.write
                    target.side_effect = error('client cancelled')
                    self.handler.reply(reply, 200, {'text':'test'})
                    reply.send_response.assert_called_once_with(200)
                    self.assertTrue(reply.close_connection)

    def test_successful_json_response_is_unchanged(self):
        reply = Mock()
        reply.wfile = io.BytesIO()
        self.handler.reply(reply, 200, {'text':'test'})
        self.assertEqual(reply.wfile.getvalue(), b'{"text": "test"}')
        self.assertTrue(reply.close_connection)


if __name__ == '__main__':
    unittest.main()
