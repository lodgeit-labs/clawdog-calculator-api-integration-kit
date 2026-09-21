"""Exercise both quickstart processes against a local HTTP server."""

import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = {
    "python": [sys.executable, str(ROOT / "examples/python/quickstart.py")],
    "dotnet": [
        "dotnet",
        str(ROOT / "examples/dotnet/bin/Debug/net8.0/ClawDogCalcKit.Quickstart.dll"),
    ],
}


class QuickstartTests(unittest.TestCase):
    def run_quickstarts(self, replies, expected_success):
        for language, command in COMMANDS.items():
            with self.subTest(language=language):
                posts = []

                class Handler(BaseHTTPRequestHandler):
                    def send_body(self, status, body):
                        self.send_response(status)
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)

                    def do_GET(self):
                        self.send_body(200, b"[]")

                    def do_POST(self):
                        posts.append(self.path)
                        status, body = replies[min(len(posts) - 1, len(replies) - 1)]
                        self.send_body(status, body)

                    def log_message(self, *args):
                        pass

                with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        result = subprocess.run(
                            command,
                            cwd=ROOT,
                            env={
                                **os.environ,
                                "CLAWDOG_CALC_API_URL": f"http://127.0.0.1:{server.server_port}",
                                "CLAWDOG_CALC_RETRIES": "1",
                                "CLAWDOG_CALC_TIMEOUT": "2",
                                "PYTHONIOENCODING": "utf-8",
                                "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                                "NO_PROXY": "127.0.0.1",
                                "no_proxy": "127.0.0.1",
                            },
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            timeout=20,
                        )
                    finally:
                        server.shutdown()
                        thread.join(timeout=5)

                output = result.stdout + result.stderr
                self.assertEqual(len(posts), len(replies), output)
                if expected_success:
                    self.assertEqual(result.returncode, 0, output)
                    self.assertIn("=== Done ===", output)
                    self.assertIn("synthetic advisory", output)
                else:
                    self.assertEqual(result.returncode, 1, output)
                    self.assertIn(f"POST returned HTTP {replies[-1][0]}", result.stderr)
                    self.assertNotIn("=== Done ===", output)

    def test_success(self):
        self.run_quickstarts([(200, b'{"result": {}, "advisory": "synthetic advisory"}')], True)

    def test_validation_error(self):
        self.run_quickstarts([(422, b'{"detail": "synthetic validation error"}')], False)

    def test_non_json_error(self):
        self.run_quickstarts([(422, b"not JSON")], False)

    def test_exhausted_server_retries(self):
        self.run_quickstarts([(503, b"unavailable"), (503, b"unavailable")], False)

    def test_server_retry_recovers(self):
        self.run_quickstarts([
            (503, b"unavailable"),
            (200, b'{"result": {}, "advisory": "synthetic advisory"}'),
        ], True)


if __name__ == "__main__":
    unittest.main()
